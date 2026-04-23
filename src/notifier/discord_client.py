"""Discord Webhook クライアント。"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx

from .models import GitHubRelease, ParsedRelease

logger = logging.getLogger(__name__)

COLOR_BREAKING = 0xE74C3C
COLOR_ADDED = 0x2ECC71
COLOR_NEUTRAL = 0x95A5A6

_DESC_MAX = 4096
_FIELD_VALUE_MAX = 1024
_EMBED_TOTAL_MAX = 6000
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0
_MAX_FIELD_ITEMS = 5


def _pick_color(parsed: ParsedRelease) -> int:
    if parsed.breaking:
        return COLOR_BREAKING
    if parsed.added:
        return COLOR_ADDED
    return COLOR_NEUTRAL


def _format_bullets(items: list[str], max_items: int = _MAX_FIELD_ITEMS) -> str:
    """Discord field.value 用の箇条書き文字列を組み立てる。

    1,024 字上限と 5 項目上限の双方で切り詰め、残件は "他 N 件" と付記する。
    """
    if not items:
        return ""
    lines: list[str] = []
    remainder = 0
    for i, item in enumerate(items):
        if i >= max_items:
            remainder = len(items) - i
            break
        lines.append(f"・{item}")

    while lines:
        rendered = "\n".join(lines)
        if remainder > 0:
            rendered += f"\n…他 {remainder} 件"
        if len(rendered) <= _FIELD_VALUE_MAX:
            return rendered
        dropped = lines.pop()
        remainder += 1
        logger.info("field.value の上限超過により 1 項目を省略: %s", dropped[:40])

    return f"…他 {remainder} 件"


def _format_description(parsed: ParsedRelease) -> str:
    parts = [
        f"新機能 {len(parsed.added)} 件",
        f"Breaking {len(parsed.breaking)} 件",
    ]
    if parsed.other_total:
        details = "、".join(f"{k} {v}" for k, v in parsed.other_counts.items())
        parts.append(f"その他 {parsed.other_total} 件（{details}）")
    else:
        parts.append("その他 0 件")
    return "、".join(parts)


def _format_footer_date(published_at: datetime) -> str:
    jst = ZoneInfo("Asia/Tokyo")
    dt = published_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(jst).strftime("%Y-%m-%d %H:%M JST")


def build_embed(
    release: GitHubRelease,
    parsed: ParsedRelease,
    added_ja: list[str],
    breaking_ja: list[str],
) -> dict:
    """Discord Embed ペイロードを構築する。"""
    title = f"Claude Code {release.tag_name}"
    description = _format_description(parsed)[:_DESC_MAX]
    color = _pick_color(parsed)

    fields: list[dict] = []
    if added_ja:
        value = _format_bullets(added_ja)
        if value:
            fields.append({"name": "新機能", "value": value, "inline": False})
    if breaking_ja:
        value = _format_bullets(breaking_ja)
        if value:
            fields.append({"name": "Breaking Changes", "value": value, "inline": False})

    embed = {
        "title": title,
        "url": release.html_url,
        "description": description,
        "color": color,
        "fields": fields,
        "footer": {"text": _format_footer_date(release.published_at)},
    }
    _enforce_total_limit(embed)
    return embed


def _enforce_total_limit(embed: dict) -> None:
    """Embed 全体 6,000 字制限への保険。超過時は fields を末尾から削る。"""
    while _embed_total_length(embed) > _EMBED_TOTAL_MAX and embed["fields"]:
        dropped = embed["fields"].pop()
        logger.warning("embed 6,000 字上限超過のため field を削除: %s", dropped.get("name"))


def _embed_total_length(embed: dict) -> int:
    total = len(embed.get("title", "")) + len(embed.get("description", ""))
    total += len(embed.get("footer", {}).get("text", ""))
    for f in embed.get("fields", []):
        total += len(f.get("name", "")) + len(f.get("value", ""))
    return total


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
                logger.warning("Discord Webhook 失敗 (attempt %d): %s", attempt, e)
            else:
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", "1") or 1)
                    logger.warning(
                        "Discord 429: Retry-After=%s sec で再試行", retry_after
                    )
                    time.sleep(min(retry_after, 30.0))
                    continue
                if 200 <= resp.status_code < 300:
                    return
                if resp.status_code >= 500:
                    logger.warning(
                        "Discord が %d を返した (attempt %d)",
                        resp.status_code,
                        attempt,
                    )
                    last_exc = httpx.HTTPStatusError(
                        f"{resp.status_code}", request=resp.request, response=resp
                    )
                else:
                    resp.raise_for_status()
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE ** attempt)
        raise RuntimeError("Discord Webhook 投稿が失敗した") from last_exc
    finally:
        if owns:
            client.close()
