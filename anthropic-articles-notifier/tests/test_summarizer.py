"""summarizer のテスト。Anthropic SDK はフェイクで差し替える。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from articles_notifier.models import Article, ArticleTranslation
from articles_notifier.summarizer import (
    EFFORT,
    MODEL,
    TranslationError,
    new_client,
    translate_article,
)

ARTICLE = Article(url="https://x/a", title="How we build agents", summary="A short summary.")


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


def _response(
    title_ja: str | None,
    summary_ja: str = "",
    stop_reason: str = "end_turn",
    category: str | None = None,
) -> SimpleNamespace:
    parsed = (
        None if title_ja is None else ArticleTranslation(title_ja=title_ja, summary_ja=summary_ja)
    )
    stop_details = SimpleNamespace(category=category) if stop_reason == "refusal" else None
    return SimpleNamespace(
        parsed_output=parsed,
        stop_reason=stop_reason,
        stop_details=stop_details,
        _request_id="req_test",
    )


def test_translate_ok_and_request_shape() -> None:
    client = _FakeClient(_response(" agent の作り方 ", "短い概要。"))
    result = translate_article(client, ARTICLE)
    assert result == ArticleTranslation(title_ja="agent の作り方", summary_ja="短い概要。")

    call = client.messages.calls[0]
    assert call["model"] == MODEL == "claude-haiku-5-5"
    assert call["output_format"] is ArticleTranslation
    assert call["output_config"] == {"effort": EFFORT}
    # Haiku 5.5 はサンプリング指定で 400 になるため送らない
    assert not {"temperature", "top_p", "top_k"} & call.keys()
    assert "How we build agents" in call["messages"][0]["content"]
    assert "A short summary." in call["messages"][0]["content"]


def test_translate_allows_empty_summary_when_source_has_none() -> None:
    article = Article(url="https://x/b", title="Title only")
    result = translate_article(_FakeClient(_response("タイトルのみ", "")), article)
    assert result.summary_ja == ""


def test_translate_refusal_raises_with_category() -> None:
    client = _FakeClient(_response(None, stop_reason="refusal", category="cyber"))
    with pytest.raises(TranslationError, match="category=cyber"):
        translate_article(client, ARTICLE)


@pytest.mark.parametrize(
    ("response"),
    [
        _response("タイトル", "概要", stop_reason="max_tokens"),  # 出力上限で打ち切り
        _response(None),  # 構造化出力が取れない
        _response("", "概要"),  # タイトルが空
        _response("タイトル", ""),  # 概要があるのに訳が空
        _response("`flag の説明", "概要"),  # 閉じていないバッククォート
    ],
)
def test_translate_rejects_bad_output(response: SimpleNamespace) -> None:
    with pytest.raises(TranslationError):
        translate_article(_FakeClient(response), ARTICLE)


def test_new_client_passes_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import anthropic

    captured: dict = {}
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: captured.update(kwargs))
    new_client("dummy-key")
    assert captured == {"api_key": "dummy-key"}
