"""Anthropic Research（www.anthropic.com/research）。

RSS が無いため sitemap.xml から記事 URL を列挙し、未知の記事だけ記事ページのメタ情報を読む。
- /research の一覧ページは一部の記事しか表示しないため使わない。
- sitemap の lastmod は記事の編集でも更新されるため、公開日には使わない（記事ページの
  article:published_time を使う）。
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from ..http import get_text
from ..models import Article
from ..text import clean_text
from .base import Source, SourceError

SITEMAP_URL = "https://www.anthropic.com/sitemap.xml"
_HOST = "www.anthropic.com"
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
# /research/<slug> のみ。/research（一覧）や /research/team/<name>（チーム紹介）は除く
_ARTICLE_PATH = re.compile(r"^/research/[^/]+$")
_EXCLUDED_PATHS = {"/research/team"}
_TITLE_SUFFIX = re.compile(r"\s*\\\s*Anthropic\s*$")


def extract_article_urls(xml_text: str) -> list[str]:
    """sitemap から研究記事の URL を重複なしで返す。

    並びは lastmod の新しい順（プレビューで最近の記事を選ぶため）。新着判定は URL の集合差で
    行うので、並び順は判定に影響しない。
    """
    try:
        # 外部サイトの XML なので、エンティティ展開攻撃などを防ぐ defusedxml で解析する
        root = SafeET.fromstring(xml_text)
    except (SafeET.ParseError, DefusedXmlException) as e:
        raise SourceError(f"anthropic.com の sitemap を解析できない: {e}") from e

    entries: dict[str, str] = {}
    for node in root.iter(f"{_SITEMAP_NS}url"):
        parts = urlsplit((node.findtext(f"{_SITEMAP_NS}loc") or "").strip())
        path = parts.path.rstrip("/")
        if parts.netloc != _HOST or path in _EXCLUDED_PATHS or not _ARTICLE_PATH.match(path):
            continue
        entries.setdefault(f"https://{_HOST}{path}", node.findtext(f"{_SITEMAP_NS}lastmod") or "")
    return sorted(entries, key=lambda url: entries[url], reverse=True)


class _MetaParser(HTMLParser):
    """<meta>・<title>・JSON-LD を集める。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self.ld_json: list[str] = []
        self._in_title = False
        self._in_ld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and "content" in a and key not in self.meta:
                self.meta[key] = a["content"]
        elif tag == "title":
            self._in_title = True
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_ld = True
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_ld:
            self.ld_json.append("".join(self._buf))
            self._in_ld = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif self._in_ld:
            self._buf.append(data)


def _ld_date_published(blocks: list[str]) -> str | None:
    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for node in data if isinstance(data, list) else [data]:
            if isinstance(node, dict) and node.get("datePublished"):
                return str(node["datePublished"])
    return None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    # タイムゾーンの無い日付（例: "2026-11-18"）は UTC とみなす。naive のままだと
    # 新着判定での日時比較が TypeError になるため
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_article(url: str, html_text: str) -> Article:
    """記事ページの HTML からタイトル・概要・公開日・画像を取り出す。"""
    parser = _MetaParser()
    parser.feed(html_text)
    meta = parser.meta

    title = clean_text(
        meta.get("og:title") or meta.get("twitter:title") or _TITLE_SUFFIX.sub("", parser.title)
    )
    if not title:
        raise SourceError(f"記事タイトルを取得できない: {url}")

    published = meta.get("article:published_time") or _ld_date_published(parser.ld_json)
    return Article(
        url=url,
        title=title,
        summary=clean_text(meta.get("og:description") or meta.get("description")) or None,
        published_at=_parse_iso(published),
        image_url=meta.get("og:image") or None,
    )


class AnthropicResearchSource(Source):
    key = "anthropic_research"
    label = "Anthropic Research"
    home_url = "https://www.anthropic.com/research"
    color = 0x6A9BCC

    def discover(self, client: httpx.Client) -> list[str]:
        return extract_article_urls(get_text(client, SITEMAP_URL))

    def load(self, client: httpx.Client, url: str) -> Article:
        return parse_article(url, get_text(client, url))
