"""claude.dev Blog（RSS 2.0）。"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from ..http import get_text
from ..models import Article
from ..text import clean_text
from .base import Source, SourceError

FEED_URL = "https://claude.dev/rss.xml"
_DC = "{http://purl.org/dc/elements/1.1/}"


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_feed(xml_text: str) -> list[Article]:
    """RSS 本文から記事一覧を取り出す。リンクかタイトルを欠く item は無視する。"""
    try:
        # 外部サイトの XML なので、エンティティ展開攻撃などを防ぐ defusedxml で解析する
        root = SafeET.fromstring(xml_text)
    except (SafeET.ParseError, DefusedXmlException) as e:
        raise SourceError(f"claude.dev の RSS を解析できない: {e}") from e

    articles: list[Article] = []
    for item in root.iter("item"):
        url = (item.findtext("link") or item.findtext("guid") or "").strip()
        title = clean_text(item.findtext("title"))
        if not url or not title:
            continue
        articles.append(
            Article(
                url=url,
                title=title,
                summary=clean_text(item.findtext("description")) or None,
                published_at=_parse_date(item.findtext("pubDate")),
                author=clean_text(item.findtext(f"{_DC}creator")) or None,
                category=clean_text(item.findtext("category")) or None,
            )
        )
    return articles


class ClaudeDevSource(Source):
    key = "claude_dev"
    label = "claude.dev Blog"
    home_url = "https://claude.dev/"
    color = 0xD97757

    def __init__(self) -> None:
        self._articles: dict[str, Article] = {}

    def discover(self, client: httpx.Client) -> list[str]:
        self._articles = {a.url: a for a in parse_feed(get_text(client, FEED_URL))}
        return list(self._articles)

    def load(self, client: httpx.Client, url: str) -> Article:
        # RSS に詳細まで含まれるため追加の取得は不要
        try:
            return self._articles[url]
        except KeyError:
            raise SourceError(f"RSS に含まれない URL: {url}") from None
