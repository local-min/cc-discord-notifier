"""Gemini 2.5 Flash による記事タイトル・概要の日本語訳。"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from .models import Article, ArticleTranslation

if TYPE_CHECKING:
    from google import genai

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = """\
あなたは Anthropic 社のブログ記事・研究記事のタイトルと概要を日本語に翻訳する専門翻訳者です。日本の開発者・研究者が Discord の通知で一目で内容をつかめる、簡潔で自然な日本語にしてください。

## 入力
- title: 記事タイトル（英語）
- summary: 記事の概要（英語）。空のこともある

## 翻訳ルール

### R1. 意味保存
- 原文の意味を変えない。推測による情報追加・脚色・補足説明は禁止する。

### R2. 用語の保持（翻訳せず英語のまま残す）
Claude, Claude Code, Anthropic, Fable, Opus, Sonnet, Haiku, MCP, agent, subagent, multi-agent, skill, hook, plugin, SDK, API, CLI, prompt, prompt caching, context, context engineering, token, eval, harness, workflow, artifact, sandbox, Constitutional AI, RLHF, interpretability, alignment
- モデル名とバージョン（例: Opus 5.5, Sonnet 5.5, Fable 5.2）は原文表記のまま残す。
- 製品名・機能名・ライブラリ名・コマンド名・論文やデータセットの固有名は無理に日本語化しない。

### R3. タイトル
- 日本語の見出しとして自然な形にする。概ね 60 文字以内。
- 原文が疑問形・コロン区切りなどの場合も、意味が伝わる範囲で自然な見出しにしてよい。

### R4. 概要
- 概ね 200 文字以内。原文が長い場合は導入表現を省き、要点を残す。
- 常体（だ・である調）または体言止めで書き、敬体（です・ます調）は用いない。
- summary が空なら summary_ja は空文字にする。

### R5. コードスパンの保持
- バッククォート（`）で囲まれた部分は原文のまま変更しない。

## 出力形式
JSON オブジェクトを返す。キーは `title_ja` と `summary_ja` のみ。余計なキーや説明文・コードフェンスは付けないこと。
"""


class TranslationError(RuntimeError):
    """翻訳処理の失敗（空出力、truncation 等）。"""


def _looks_truncated(text: str) -> bool:
    """閉じていないバッククォートが残っていれば途中切れとみなす。"""
    return text.count("`") % 2 != 0


def translate_article(client: genai.Client, article: Article) -> ArticleTranslation:
    """記事のタイトルと概要を日本語にする。"""
    from google.genai import types

    payload = {"title": article.title, "summary": article.summary or ""}
    user_prompt = (
        "以下の記事のタイトルと概要を、上記ルールに従って日本語に翻訳してください。\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

    response = client.models.generate_content(
        model=MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=ArticleTranslation,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            temperature=0.2,
            max_output_tokens=2048,
            candidate_count=1,
        ),
    )

    parsed: ArticleTranslation | None = response.parsed
    if parsed is None:
        raise TranslationError("Gemini レスポンスのパースに失敗した")

    finish_reason = response.candidates[0].finish_reason
    finish_name = getattr(finish_reason, "name", str(finish_reason))
    if finish_name != "STOP":
        raise TranslationError(f"異常な finish_reason: {finish_name}")

    title_ja = parsed.title_ja.strip()
    summary_ja = parsed.summary_ja.strip()
    if not title_ja:
        raise TranslationError("タイトルの訳が空")
    if article.summary and not summary_ja:
        raise TranslationError("概要の訳が空")
    for name, text in (("title_ja", title_ja), ("summary_ja", summary_ja)):
        if _looks_truncated(text):
            raise TranslationError(f"{name} が truncation の疑い: {text!r}")
    if len(summary_ja) > 400:
        logger.warning("概要の訳が 400 文字を超えた (length=%d)", len(summary_ja))

    return ArticleTranslation(title_ja=title_ja, summary_ja=summary_ja)
