"""summarizer.py のユニットテスト。Anthropic SDK はフェイクで差し替える。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from notifier.models import TranslationResponse
from notifier.summarizer import (
    EFFORT,
    MODEL,
    TranslationError,
    new_client,
    translate_release_items,
)


class _FakeMessages:
    def __init__(self, response) -> None:
        self._response = response
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response) -> None:
        self.messages = _FakeMessages(response)


def _make_response(
    translations: list[str] | None,
    stop_reason: str = "end_turn",
    category: str | None = None,
) -> SimpleNamespace:
    parsed = None if translations is None else TranslationResponse(translations=translations)
    stop_details = SimpleNamespace(category=category) if stop_reason == "refusal" else None
    return SimpleNamespace(
        parsed_output=parsed,
        stop_reason=stop_reason,
        stop_details=stop_details,
        _request_id="req_test",
    )


def test_translate_ok() -> None:
    response = _make_response(["Added A の訳", "Breaking B の訳"])
    client = _FakeClient(response)
    result = translate_release_items(client, ["Added A", "Breaking B"])
    assert result == ["Added A の訳", "Breaking B の訳"]


def test_translate_request_shape() -> None:
    client = _FakeClient(_make_response(["Added A の訳"]))
    translate_release_items(client, ["Added A"])
    call = client.messages.calls[0]
    assert call["model"] == MODEL == "claude-haiku-5-5"
    assert call["output_format"] is TranslationResponse
    assert call["output_config"] == {"effort": EFFORT}
    # Haiku 5.5 はサンプリング指定で 400 になるため送らない
    assert not {"temperature", "top_p", "top_k"} & call.keys()
    assert "Added A" in call["messages"][0]["content"]


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


def test_translate_max_tokens() -> None:
    response = _make_response(["Added A の訳"], stop_reason="max_tokens")
    client = _FakeClient(response)
    with pytest.raises(TranslationError):
        translate_release_items(client, ["Added A"])


def test_translate_refusal() -> None:
    response = _make_response(None, stop_reason="refusal", category="cyber")
    client = _FakeClient(response)
    with pytest.raises(TranslationError, match="category=cyber"):
        translate_release_items(client, ["Added A"])


def test_translate_missing_parsed_output() -> None:
    client = _FakeClient(_make_response(None))
    with pytest.raises(TranslationError):
        translate_release_items(client, ["Added A"])


def test_translate_detects_truncation_via_backtick() -> None:
    # バッククォートが奇数で閉じていない（truncation 疑い）
    response = _make_response(["Added `--flag を使用"])
    client = _FakeClient(response)
    with pytest.raises(TranslationError):
        translate_release_items(client, ["Added use --flag"])


def test_new_client_passes_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import anthropic

    captured: dict = {}
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: captured.update(kwargs))
    new_client("dummy-key")
    assert captured == {"api_key": "dummy-key"}
