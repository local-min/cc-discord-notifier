"""state.py のユニットテスト。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from notifier.models import State
from notifier.state import load_state, save_state


def test_load_missing(tmp_path: Path) -> None:
    state = load_state(tmp_path / "state.json")
    assert state.last_release_id is None
    assert state.last_tag_name is None


def test_load_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    p.write_text("", encoding="utf-8")
    state = load_state(p)
    assert state.last_release_id is None


def test_save_then_load(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    original = State(
        last_release_id=12345,
        last_tag_name="v2.1.81",
        last_published_at=datetime(2026, 4, 23, 12, 34, 56, tzinfo=UTC),
    )
    save_state(p, original)
    loaded = load_state(p)
    assert loaded.last_release_id == 12345
    assert loaded.last_tag_name == "v2.1.81"
    assert loaded.last_published_at == original.last_published_at
