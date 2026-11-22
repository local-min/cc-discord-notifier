"""配信元（RSS / sitemap / 記事ページ）の解析テスト。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from articles_notifier.sources import SourceError
from articles_notifier.sources.anthropic_research import extract_article_urls, parse_article
from articles_notifier.sources.claude_dev import parse_feed

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- claude.dev (RSS) ---


def test_parse_feed_extracts_items() -> None:
    articles = parse_feed(_read("claude_dev_rss.xml"))
    # link を欠く item は除外される
    assert [a.url for a in articles] == [
        "https://claude.dev/blog/newest-post/",
        "https://claude.dev/blog/older-post/",
    ]
    first = articles[0]
    assert first.title == 'Newest post about "agents"'
    assert first.summary == "An HTML summary & more."  # タグ除去と実体参照の復元
    assert first.published_at == datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    assert first.author == "Jane Doe"
    assert first.category == "Engineering"
    assert articles[1].author is None
    assert articles[1].category is None


def test_parse_feed_invalid_xml() -> None:
    with pytest.raises(SourceError):
        parse_feed("<rss><channel>")


def test_parse_feed_rejects_entity_expansion() -> None:
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>'
        "<rss><channel><item><title>&b;</title><link>https://x/</link></item></channel></rss>"
    )
    with pytest.raises(SourceError):
        parse_feed(bomb)


# --- anthropic.com/research (sitemap + 記事ページ) ---


def test_extract_article_urls_filters_and_sorts() -> None:
    urls = extract_article_urls(_read("anthropic_sitemap.xml"))
    # /research 一覧・/research/team/*・/news/*・他ホストは除外、末尾スラッシュは同一視、
    # lastmod の新しい順、URL の大文字小文字は保持
    assert urls == [
        "https://www.anthropic.com/research/Newer-Paper",
        "https://www.anthropic.com/research/older-paper",
    ]


def test_extract_article_urls_invalid_xml() -> None:
    with pytest.raises(SourceError):
        extract_article_urls("not xml")


def test_parse_article_reads_meta() -> None:
    url = "https://www.anthropic.com/research/sample"
    article = parse_article(url, _read("anthropic_article.html"))
    assert article.url == url
    assert article.title == "A sample research title"
    assert article.summary == "Claude did something & found results."  # og:description を優先
    assert article.published_at == datetime(2026, 11, 18, tzinfo=UTC)
    assert article.image_url == "https://assets.example.com/image.jpg"


def test_parse_article_falls_back_to_title_and_json_ld() -> None:
    article = parse_article("https://x/research/m", _read("anthropic_article_minimal.html"))
    assert article.title == "Minimal page title"  # " \\ Anthropic" を除去
    assert article.summary is None
    assert article.published_at == datetime(2026, 11, 10, tzinfo=UTC)
    assert article.image_url is None


def test_parse_article_date_without_timezone_is_utc() -> None:
    html = (
        '<html><head><meta property="og:title" content="T"/>'
        '<meta property="article:published_time" content="2026-11-18"/></head></html>'
    )
    article = parse_article("https://x/research/d", html)
    assert article.published_at == datetime(2026, 11, 18, tzinfo=UTC)


def test_parse_article_without_title_raises() -> None:
    with pytest.raises(SourceError):
        parse_article("https://x/research/empty", "<html><head></head></html>")
