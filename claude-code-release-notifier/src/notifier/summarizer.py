"""Gemini 2.5 Flash による翻訳処理。"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from .models import TranslationResponse

if TYPE_CHECKING:
    from google import genai

logger = logging.getLogger(__name__)


SYSTEM_INSTRUCTION = """\
あなたは Anthropic 社の AI コーディングエージェント「Claude Code」のリリースノートを日本語に翻訳する専門翻訳者です。与えられた英語の箇条書き項目を、日本の開発者向けの簡潔な日本語に翻訳してください。

## 役割
- 入力: Claude Code リリースノートの箇条書き項目（英語）の配列
- 出力: 各項目に対応する日本語訳の配列（入力と同じ件数・同じ順序）

## 翻訳ルール

### R1. 意味保存
- 原文の意味を変えない。推測による情報追加・脚色・例示の拡張・補足説明の付与はいずれも禁止する。
- 原文に書かれていない効果や用途を訳文に含めない。

### R2. 先頭ラベルの保持
- 項目の先頭にある分類ラベル（Added / Fixed / Improved / Changed / Removed / Deprecated / Breaking など）は英語のまま残し、その後に半角スペースを挟んで日本語訳を続ける。
- 例: "Added support for X" → "Added X に対応"

### R3. 製品固有用語の保持（以下のリストに含まれる語は翻訳せず英語のまま残す）
MCP, subagent, hook, skill, sandbox, permission rule, plugin, slash command, tool, artifact, agent, SDK, CLI, API, SSE, OAuth, prompt, context, token, session, workflow, Claude, Claude Code, Anthropic, GitHub, VSCode, IDE, terminal, shell, bash, zsh, fish, thinking, reasoning, tool use, streaming, tokenizer, extended thinking, system prompt, Bedrock, Vertex AI

上記以外でも、明らかにコマンド名・フラグ名・ファイル名・環境変数名・関数名・設定キー・HTTP ステータス・ライブラリ名である語は、無理に日本語化せず原文のまま保持する。

### R4. コードスパンの保持
- Markdown のバッククォート（`）で囲まれた部分は、内容・記号ともに原文のまま変更しない。
- 例: `--output-format` → `--output-format`

### R5. 文字数制限
- 1 項目あたり、ラベル部分を除いた日本語本文は概ね 80 文字以内に収める。
- 原文が長大な場合は、"we've"、"now you can"、"as part of our effort to" などの導入表現を省いて本質的な変更内容のみを訳す。

### R6. 文体
- 常体（だ・である調）ではなく、体言止めまたは「〜に対応」「〜を改善」「〜を削除」などの名詞句または簡潔な動詞句で締める。
- 敬体（です・ます調）は用いない。

### R7. 判断不能時の挙動
- 訳語が明らかに存在せず、カタカナ化も不自然な語は原文のまま残す。
- 文脈が不明瞭な場合は、推測を交えず原文に最も忠実な直訳を選ぶ。

## 翻訳例

### 例 1
入力: "Added support for MCP resources with mime type image/png in conversations."
出力: "Added 会話内で MIME タイプ image/png の MCP resources に対応"

### 例 2
入力: "Breaking: Removed the deprecated --legacy flag. Use --output-format instead."
出力: "Breaking 非推奨の `--legacy` フラグを削除。代わりに `--output-format` を使用"

### 例 3
入力: "Added /compact slash command now preserves pinned system prompts across compactions."
出力: "Added `/compact` slash command が compaction をまたいで pinned system prompt を保持"

## 出力形式
JSON オブジェクトを返す。キーは `translations` のみで、値は入力と同じ長さ・同じ順序の日本語訳文字列の配列とする。余計なキーや説明文・コードフェンスは一切付けないこと。
"""


class TranslationError(RuntimeError):
    """翻訳処理の失敗（件数不整合、truncation 等）。"""


def _looks_truncated(text: str) -> bool:
    """出力末尾が不自然に途切れていないかの簡易検査。

    通常の日本語文は句点や記号、英数字、右括弧系で終わることが多い。
    末尾が半角開き括弧やバッククォートのまま閉じられていない場合などを truncation と見做す。
    """
    if not text:
        return True
    stripped = text.rstrip()
    if not stripped:
        return True
    # 開きバッククォート数が奇数なら閉じていない
    return stripped.count("`") % 2 != 0


def translate_release_items(
    client: genai.Client,
    items: list[str],
) -> list[str]:
    """抽出済み英語項目リストを日本語訳リストに変換する。"""
    from google.genai import types

    if not items:
        raise ValueError("items は 1 件以上である必要がある")

    user_prompt = (
        "以下の項目を、上記ルールに従って日本語に翻訳してください。\n\n"
        f"入力項目（英語、{len(items)} 件）:\n"
        f"{json.dumps(items, ensure_ascii=False, indent=2)}\n\n"
        "出力: 同じ順序・同じ件数の日本語訳を `translations` 配列で返してください。"
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=TranslationResponse,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            temperature=0.2,
            max_output_tokens=8192,
            candidate_count=1,
        ),
    )

    parsed: TranslationResponse | None = response.parsed
    if parsed is None:
        raise TranslationError("Gemini レスポンスのパースに失敗した")

    if len(parsed.translations) != len(items):
        raise TranslationError(
            f"出力件数不整合: 入力 {len(items)} 件 / 出力 {len(parsed.translations)} 件"
        )

    finish_reason = response.candidates[0].finish_reason
    finish_name = getattr(finish_reason, "name", str(finish_reason))
    if finish_name != "STOP":
        raise TranslationError(f"異常な finish_reason: {finish_name}")

    for idx, text in enumerate(parsed.translations):
        if _looks_truncated(text):
            raise TranslationError(
                f"項目 {idx} の出力が truncation の疑い: {text!r}"
            )
        if len(text) > 200:
            logger.warning(
                "項目 %d の訳文が 200 文字を超えた (length=%d)", idx, len(text)
            )

    return parsed.translations
