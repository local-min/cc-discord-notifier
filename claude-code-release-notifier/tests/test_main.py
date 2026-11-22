"""main.run のプレビューモードのテスト。外部 API はすべて差し替える。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from notifier import main, summarizer
from notifier.models import GitHubRelease

RELEASE = GitHubRelease(
    id=999,
    tag_name="v9.9.9",
    html_url="https://github.com/anthropics/claude-code/releases/tag/v9.9.9",
    body="- Added new thing\n- Fixed old thing\n",
    published_at=datetime(2026, 11, 22, tzinfo=UTC),
)


def test_preview_processes_latest_without_touching_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state_path = tmp_path / "state.json"
    for key, value in {
        "GITHUB_PAT": "pat",
        "ANTHROPIC_API_KEY": "key",
        "DISCORD_WEBHOOK_URL": "https://discord.invalid/webhook",
        "STATE_PATH": str(state_path),
        "DRY_RUN": "true",
        "PREVIEW": "true",
    }.items():
        monkeypatch.setenv(key, value)

    since_ids: list[int | None] = []

    def fake_fetch(repo, token, since_id):
        since_ids.append(since_id)
        return [RELEASE]

    translated: list[list[str]] = []
    monkeypatch.setattr(main, "fetch_releases", fake_fetch)
    monkeypatch.setattr(summarizer, "new_client", lambda api_key: object())
    monkeypatch.setattr(
        main,
        "translate_release_items",
        lambda client, items: translated.append(items) or [f"訳 {i}" for i in items],
    )

    assert main.run() == 0
    assert since_ids == [None]  # 既読に関係なく最新を取りに行く
    assert translated == [["Added new thing"]]
    assert not state_path.exists()  # state は書かない
