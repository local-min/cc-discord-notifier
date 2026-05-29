"""parser.py のユニットテスト。"""

from __future__ import annotations

import json
from pathlib import Path

from notifier.parser import parse_release_body

FIXTURE = Path(__file__).parent / "fixtures" / "release_v2_1_81.json"


def _load_body() -> str:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data["body"]


def test_parse_added_items() -> None:
    result = parse_release_body(_load_body())
    assert len(result.added) == 3
    assert any("MCP resources" in item for item in result.added)
    assert any("/compact" in item for item in result.added)
    assert any(item.startswith("[VSCode]") for item in result.added)


def test_parse_breaking_items() -> None:
    result = parse_release_body(_load_body())
    # "Breaking: ..." と "Removed ..." の 2 件
    assert len(result.breaking) == 2
    assert any(item.startswith("Breaking") for item in result.breaking)
    assert any(item.startswith("Removed") for item in result.breaking)


def test_parse_other_counts() -> None:
    result = parse_release_body(_load_body())
    assert result.other_counts.get("Fixed") == 2
    assert result.other_counts.get("Improved") == 2
    assert result.other_counts.get("Changed") == 1
    assert result.other_total == 5


def test_parse_ignores_code_fence() -> None:
    body = "```\n- Added this must be ignored\n```\n- Added keep me\n"
    result = parse_release_body(body)
    assert len(result.added) == 1
    assert "keep me" in result.added[0]


def test_parse_empty_body() -> None:
    result = parse_release_body(None)
    assert result.added == []
    assert result.breaking == []
    assert result.other_counts == {}


def test_parse_nested_bullets_skipped() -> None:
    body = "- Added top level\n  - Added nested must skip\n- Fixed detail\n"
    result = parse_release_body(body)
    assert len(result.added) == 1
    assert result.other_counts.get("Fixed") == 1
