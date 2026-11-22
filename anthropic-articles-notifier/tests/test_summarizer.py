"""summarizer のテスト。Gemini SDK はフェイクで差し替える。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from articles_notifier.models import Article, ArticleTranslation
from articles_notifier.summarizer import TranslationError, new_client, translate_article

ARTICLE = Article(url="https://x/a", title="How we build agents", summary="A short summary.")


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


def _response(title_ja: str, summary_ja: str, finish: str = "STOP") -> SimpleNamespace:
    return SimpleNamespace(
        parsed=ArticleTranslation(title_ja=title_ja, summary_ja=summary_ja),
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
    )


def test_translate_ok() -> None:
    client = _FakeClient(_response(" agent の作り方 ", "短い概要。"))
    result = translate_article(client, ARTICLE)
    assert result == ArticleTranslation(title_ja="agent の作り方", summary_ja="短い概要。")
    prompt = client.models.calls[0]["contents"]
    assert "How we build agents" in prompt
    assert "A short summary." in prompt


def test_translate_allows_empty_summary_when_source_has_none() -> None:
    article = Article(url="https://x/b", title="Title only")
    result = translate_article(_FakeClient(_response("タイトルのみ", "")), article)
    assert result.summary_ja == ""


@pytest.mark.parametrize(
    ("title_ja", "summary_ja", "finish"),
    [
        ("", "概要", "STOP"),  # タイトルが空
        ("タイトル", "", "STOP"),  # 概要があるのに訳が空
        ("タイトル", "概要", "MAX_TOKENS"),  # 途中で打ち切られた
        ("`flag の説明", "概要", "STOP"),  # 閉じていないバッククォート
    ],
)
def test_translate_rejects_bad_output(title_ja: str, summary_ja: str, finish: str) -> None:
    with pytest.raises(TranslationError):
        translate_article(_FakeClient(_response(title_ja, summary_ja, finish)), ARTICLE)


def test_new_client_uses_v1beta(monkeypatch: pytest.MonkeyPatch) -> None:
    # v1 では system_instruction が拒否されるため、v1beta を明示していることを確認する
    from google import genai

    captured: dict = {}
    monkeypatch.setattr(genai, "Client", lambda **kwargs: captured.update(kwargs))
    new_client("dummy-key")
    assert captured["api_key"] == "dummy-key"
    assert captured["http_options"].api_version == "v1beta"


def test_translate_parse_failure() -> None:
    response = SimpleNamespace(parsed=None, candidates=[])
    with pytest.raises(TranslationError):
        translate_article(_FakeClient(response), ARTICLE)
