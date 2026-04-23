"""summarizer.py のユニットテスト。Gemini SDK はフェイクで差し替える。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from notifier.models import TranslationResponse
from notifier.summarizer import TranslationError, translate_release_items


class _FakeModels:
    def __init__(self, response) -> None:
        self._response = response
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response) -> None:
        self.models = _FakeModels(response)


def _make_response(translations: list[str], finish: str = "STOP") -> SimpleNamespace:
    return SimpleNamespace(
        parsed=TranslationResponse(translations=translations),
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
    )


def test_translate_ok() -> None:
    response = _make_response(["Added A の訳", "Breaking B の訳"])
    client = _FakeClient(response)
    result = translate_release_items(client, ["Added A", "Breaking B"])
    assert result == ["Added A の訳", "Breaking B の訳"]


def test_translate_empty_items_raises() -> None:
    response = _make_response([])
    client = _FakeClient(response)
    with pytest.raises(ValueError):
        translate_release_items(client, [])


def test_translate_count_mismatch() -> None:
    response = _make_response(["only one"])
    client = _FakeClient(response)
    with pytest.raises(TranslationError):
        translate_release_items(client, ["Added A", "Added B"])


def test_translate_bad_finish_reason() -> None:
    response = _make_response(["Added A の訳"], finish="MAX_TOKENS")
    client = _FakeClient(response)
    with pytest.raises(TranslationError):
        translate_release_items(client, ["Added A"])


def test_translate_detects_truncation_via_backtick() -> None:
    # バッククォートが奇数で閉じていない（truncation 疑い）
    response = _make_response(["Added `--flag を使用"])
    client = _FakeClient(response)
    with pytest.raises(TranslationError):
        translate_release_items(client, ["Added use --flag"])
