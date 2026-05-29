"""state.json の読み書き。"""

from __future__ import annotations

import json
from pathlib import Path

from .models import State


def load_state(path: str | Path) -> State:
    """state.json を読み込む。未存在または空の場合は空の State を返す。"""
    p = Path(path)
    if not p.exists():
        return State()
    raw = p.read_text(encoding="utf-8").strip()
    if not raw:
        return State()
    data = json.loads(raw)
    return State.model_validate(data)


def save_state(path: str | Path, state: State) -> None:
    """state.json に書き込む（改行付き・末尾に NL）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = state.model_dump(mode="json", exclude_none=False)
    p.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
