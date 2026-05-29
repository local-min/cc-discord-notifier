"""GitHub Releases API クライアント。"""

from __future__ import annotations

import logging
import time

import httpx

from .models import GitHubRelease

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0
_PER_PAGE = 30
_HARD_PAGE_LIMIT = 10


def _request_with_retry(client: httpx.Client, url: str, params: dict) -> httpx.Response:
    """5xx/ネットワーク失敗時に指数バックオフで最大3回リトライする。"""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = client.get(url, params=params)
        except httpx.HTTPError as e:
            last_exc = e
            logger.warning(
                "GitHub API リクエスト失敗 (attempt %d): %s", attempt, type(e).__name__
            )
        else:
            if resp.status_code < 500:
                resp.raise_for_status()
                return resp
            logger.warning(
                "GitHub API が %d を返した (attempt %d)", resp.status_code, attempt
            )
            last_exc = httpx.HTTPStatusError(
                f"{resp.status_code}", request=resp.request, response=resp
            )
        if attempt < _MAX_RETRIES:
            time.sleep(_BACKOFF_BASE ** attempt)
    raise RuntimeError("GitHub API への問い合わせが失敗した") from last_exc


def fetch_releases(
    repo: str,
    token: str,
    since_id: int | None,
    *,
    client: httpx.Client | None = None,
) -> list[GitHubRelease]:
    """対象リポジトリから since_id 以降のリリースを公開日時昇順で返す。

    since_id が None（初回相当）の場合は、全件ではなく最新 1 件のみ返す。
    ページネーションは since_id が見つかるか HARD_PAGE_LIMIT に到達するまで行う。
    """
    base_url = f"https://api.github.com/repos/{repo}/releases"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
        "User-Agent": "cc-discord-notifier",
    }

    owns_client = client is None
    if owns_client:
        client = httpx.Client(headers=headers, timeout=30.0)
    else:
        client.headers.update(headers)

    try:
        collected: list[GitHubRelease] = []
        for page in range(1, _HARD_PAGE_LIMIT + 1):
            resp = _request_with_retry(
                client,
                base_url,
                {"per_page": _PER_PAGE, "page": page},
            )
            payload = resp.json()
            if not payload:
                break
            for item in payload:
                rel = GitHubRelease.model_validate(item)
                if rel.draft or rel.prerelease:
                    continue
                if since_id is not None and rel.id <= since_id:
                    collected.sort(key=lambda r: r.published_at)
                    return collected
                collected.append(rel)
            if len(payload) < _PER_PAGE:
                break
    finally:
        if owns_client:
            client.close()

    collected.sort(key=lambda r: r.published_at)
    if since_id is None:
        return collected[-1:] if collected else []
    return collected
