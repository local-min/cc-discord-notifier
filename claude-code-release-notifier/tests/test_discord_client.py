"""discord_client.py のユニットテスト。"""

from __future__ import annotations

from datetime import UTC, datetime

from notifier.discord_client import (
    COLOR_ADDED,
    COLOR_BREAKING,
    COLOR_NEUTRAL,
    build_embed,
)
from notifier.models import GitHubRelease, ParsedRelease


def _make_release() -> GitHubRelease:
    return GitHubRelease(
        id=1,
        tag_name="v2.1.81",
        name="v2.1.81",
        html_url="https://github.com/anthropics/claude-code/releases/tag/v2.1.81",
        body="",
        published_at=datetime(2026, 4, 23, 3, 0, 0, tzinfo=UTC),
    )


def test_color_breaking() -> None:
    parsed = ParsedRelease(added=["Added X"], breaking=["Breaking Y"])
    embed = build_embed(_make_release(), parsed, ["Added X 訳"], ["Breaking Y 訳"])
    assert embed["color"] == COLOR_BREAKING


def test_color_added() -> None:
    parsed = ParsedRelease(added=["Added X"])
    embed = build_embed(_make_release(), parsed, ["Added X 訳"], [])
    assert embed["color"] == COLOR_ADDED
    assert len(embed["fields"]) == 1
    assert embed["fields"][0]["name"] == "新機能"


def test_color_neutral_and_other_counts() -> None:
    parsed = ParsedRelease(other_counts={"Fixed": 3, "Improved": 2})
    embed = build_embed(_make_release(), parsed, [], [])
    assert embed["color"] == COLOR_NEUTRAL
    assert "その他 5 件" in embed["description"]
    assert embed["fields"] == []


def test_footer_is_jst() -> None:
    parsed = ParsedRelease(added=["Added X"])
    embed = build_embed(_make_release(), parsed, ["Added X 訳"], [])
    # UTC 03:00 → JST 12:00
    assert "12:00 JST" in embed["footer"]["text"]


def test_truncates_to_five_items() -> None:
    added = [f"Added item {i}" for i in range(8)]
    parsed = ParsedRelease(added=added)
    added_ja = [f"Added 項目 {i}" for i in range(8)]
    embed = build_embed(_make_release(), parsed, added_ja, [])
    value = embed["fields"][0]["value"]
    assert "他 3 件" in value
    assert value.count("・") == 5
