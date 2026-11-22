"""state の読み書きテスト。"""

from __future__ import annotations

import json
from pathlib import Path

from articles_notifier.models import SourceState, State
from articles_notifier.state import load_state, save_state


def test_load_missing_or_empty(tmp_path: Path) -> None:
    assert load_state(tmp_path / "none.json") == State()
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    assert load_state(empty) == State()


def test_save_sorts_and_dedupes(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = State(
        sources={
            "z_source": SourceState(seen=["https://b", "https://a", "https://b"]),
            "a_source": SourceState(seen=[]),
        }
    )
    save_state(path, state)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert list(data["sources"]) == ["a_source", "z_source"]
    assert data["sources"]["z_source"]["seen"] == ["https://a", "https://b"]
    assert load_state(path).sources["z_source"].seen == ["https://a", "https://b"]
