"""discord_client のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from articles_notifier import discord_client
from articles_notifier.discord_client import build_embed, post_embed
from articles_notifier.models import Article, ArticleTranslation

WEBHOOK = "https://discord.com/api/webhooks/123/secret-token"


def _embed(**overrides) -> dict:
    article = Article(
        url="https://claude.dev/blog/post/",
        title="English title",
        published_at=datetime(2026, 11, 17, 12, 0, tzinfo=UTC),
        author="Jane Doe",
        category="Engineering",
        **overrides,
    )
    translation = ArticleTranslation(title_ja="日本語タイトル", summary_ja="日本語の概要")
    return build_embed(
        article,
        translation,
        source_label="claude.dev Blog",
        source_url="https://claude.dev/",
        color=0xD97757,
    )


def test_build_embed_structure() -> None:
    embed = _embed()
    assert embed["author"] == {"name": "claude.dev Blog", "url": "https://claude.dev/"}
    assert embed["title"] == "日本語タイトル"
    assert embed["url"] == "https://claude.dev/blog/post/"
    assert embed["description"] == "日本語の概要"
    assert embed["fields"] == [{"name": "原題", "value": "English title", "inline": False}]
    assert embed["footer"]["text"] == "Engineering · Jane Doe · 2026-11-17"
    assert "thumbnail" not in embed


def test_build_embed_with_image_and_without_summary() -> None:
    article = Article(url="https://x/r", title="T", image_url="https://img/x.jpg")
    embed = build_embed(
        article,
        ArticleTranslation(title_ja="訳", summary_ja=""),
        source_label="L",
        source_url="https://x/",
        color=1,
    )
    assert embed["thumbnail"] == {"url": "https://img/x.jpg"}
    assert "description" not in embed
    assert "footer" not in embed


def test_build_embed_truncates_long_title() -> None:
    article = Article(url="https://x/r", title="T")
    embed = build_embed(
        article,
        ArticleTranslation(title_ja="あ" * 300, summary_ja=""),
        source_label="L",
        source_url="https://x/",
        color=1,
    )
    assert len(embed["title"]) == 256
    assert embed["title"].endswith("…")


def _client(statuses: list[int]) -> tuple[httpx.Client, list[int]]:
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = statuses[len(seen)]
        seen.append(status)
        return httpx.Response(status, headers={"Retry-After": "0"})

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_post_embed_retries_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discord_client.time, "sleep", lambda _: None)
    client, seen = _client([500, 204])
    post_embed(WEBHOOK, {"title": "x"}, client=client)
    assert seen == [500, 204]


def test_post_embed_4xx_error_does_not_leak_webhook_url() -> None:
    client, _ = _client([404])
    with pytest.raises(RuntimeError) as exc_info:
        post_embed(WEBHOOK, {"title": "x"}, client=client)
    assert "secret-token" not in str(exc_info.value)
