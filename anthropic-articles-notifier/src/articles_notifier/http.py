"""配信元サイトへの HTTP GET（リトライ付き）。"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; articles-notifier/0.1)"
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0


def new_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
        follow_redirects=True,
    )


def get_text(client: httpx.Client, url: str) -> str:
    """URL の本文を返す。ネットワーク失敗・429・5xx は指数バックオフで最大 3 回試す。"""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = client.get(url)
        except httpx.HTTPError as e:
            last_exc = e
            logger.warning("GET 失敗 (attempt %d): %s %s", attempt, url, type(e).__name__)
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning("GET %s が %d を返した (attempt %d)", url, resp.status_code, attempt)
                last_exc = httpx.HTTPStatusError(
                    f"{resp.status_code}", request=resp.request, response=resp
                )
            else:
                resp.raise_for_status()
                return resp.text
        if attempt < _MAX_RETRIES:
            time.sleep(_BACKOFF_BASE**attempt)
    raise RuntimeError(f"GET {url} が失敗した") from last_exc
