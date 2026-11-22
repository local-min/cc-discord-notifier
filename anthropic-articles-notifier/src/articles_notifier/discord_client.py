"""Discord Webhook クライアント。"""

from __future__ import annotations

import logging
import time
from datetime import UTC

import httpx

from .models import Article, ArticleTranslation

logger = logging.getLogger(__name__)

_TITLE_MAX = 256
_DESC_MAX = 4096
_FIELD_VALUE_MAX = 1024
_FOOTER_MAX = 2048
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _footer(article: Article) -> str:
    parts: list[str] = []
    if article.category:
        parts.append(article.category)
    if article.author:
        parts.append(article.author)
    if article.published_at:
        # 配信元の公開日時は日付だけが意味を持つ（時刻は 00:00 / 12:00 固定）ため日付のみ表示
        dt = article.published_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        parts.append(dt.astimezone(UTC).strftime("%Y-%m-%d"))
    return " · ".join(parts)


def build_embed(
    article: Article,
    translation: ArticleTranslation,
    *,
    source_label: str,
    source_url: str,
    color: int,
) -> dict:
    """Discord Embed ペイロードを組み立てる。"""
    embed: dict = {
        "author": {"name": source_label, "url": source_url},
        "title": _truncate(translation.title_ja, _TITLE_MAX),
        "url": article.url,
        "color": color,
        "fields": [
            {"name": "原題", "value": _truncate(article.title, _FIELD_VALUE_MAX), "inline": False}
        ],
    }
    if translation.summary_ja:
        embed["description"] = _truncate(translation.summary_ja, _DESC_MAX)
    footer = _footer(article)
    if footer:
        embed["footer"] = {"text": _truncate(footer, _FOOTER_MAX)}
    if article.image_url:
        embed["thumbnail"] = {"url": article.image_url}
    return embed


def post_embed(
    webhook_url: str,
    embed: dict,
    *,
    client: httpx.Client | None = None,
) -> None:
    """Webhook へ Embed を POST する。失敗時は指数バックオフで最大 3 回リトライ。"""
    payload = {"embeds": [embed]}

    owns = client is None
    if owns:
        client = httpx.Client(timeout=30.0)
    try:
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = client.post(webhook_url, json=payload)
            except httpx.HTTPError as e:
                last_exc = e
                # 例外は URL を含み得るためクラス名だけ出す。Webhook URL はパスにトークンを含み、
                # Public リポジトリの Actions ログに出ると投稿権限を奪われるため。
                logger.warning("Discord Webhook 失敗 (attempt %d): %s", attempt, type(e).__name__)
            else:
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", "1") or 1)
                    logger.warning("Discord 429: Retry-After=%s sec で再試行", retry_after)
                    time.sleep(min(retry_after, 30.0))
                    continue
                if 200 <= resp.status_code < 300:
                    return
                if resp.status_code >= 500:
                    logger.warning("Discord が %d を返した (attempt %d)", resp.status_code, attempt)
                    last_exc = httpx.HTTPStatusError(
                        f"{resp.status_code}", request=resp.request, response=resp
                    )
                else:
                    # raise_for_status() の例外メッセージは URL を含むため使わない
                    raise RuntimeError(f"Discord Webhook が {resp.status_code} を返した")
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE**attempt)
        raise RuntimeError("Discord Webhook 投稿が失敗した") from last_exc
    finally:
        if owns:
            client.close()
