"""リリース本文の行単位パース。"""

from __future__ import annotations

import re

from .models import ParsedRelease

_BULLET_RE = re.compile(r"^\s*[-*+]\s+(?P<body>.+?)\s*$")
_PREFIX_RE = re.compile(r"^(?:\[[^\]]+\]\s*)+")
_LABEL_RE = re.compile(
    r"^(?P<label>Added|Fixed|Improved|Changed|Removed|Deprecated|Breaking|Security|"
    r"Performance|Enhanced|Updated)\b[:\s]",
    re.IGNORECASE,
)

_ADDED_LABELS = {"added"}
_BREAKING_LABELS = {"breaking", "removed", "deprecated"}


def _normalize_label(raw: str) -> str:
    """表記ゆれを正規化。"""
    return raw.strip().lower()


def _canonical_label(normalized: str) -> str:
    """分類後に使う表示用ラベル（先頭大文字）。"""
    return normalized.capitalize()


def parse_release_body(body: str | None) -> ParsedRelease:
    """リリース本文から Added/Breaking 項目と他カテゴリ件数を抽出する。

    ラベルが識別できない行や、コードブロック内の行、ネストされたサブ箇条書きは
    保守的に集計から除外する（other にも数えない）。
    """
    result = ParsedRelease()
    if not body:
        return result

    in_code_fence = False
    for raw_line in body.splitlines():
        stripped = raw_line.lstrip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue

        # ネスト（先頭が 2 スペース以上インデントされた箇条書き）はスキップ
        leading_ws = len(raw_line) - len(stripped)
        if leading_ws >= 2:
            continue

        m = _BULLET_RE.match(raw_line)
        if not m:
            continue

        body_text = m.group("body")
        # 先頭の [VSCode] 等のプレフィックスを剥がす
        body_text_no_prefix = _PREFIX_RE.sub("", body_text).strip()
        label_match = _LABEL_RE.match(body_text_no_prefix)
        if not label_match:
            continue

        normalized = _normalize_label(label_match.group("label"))
        # 元の bullet 行から先頭の "- " 等を除いた文字列を保持（プレフィックス付き）
        item_text = body_text.strip()

        if normalized in _ADDED_LABELS:
            result.added.append(item_text)
        elif normalized in _BREAKING_LABELS:
            result.breaking.append(item_text)
        else:
            canonical = _canonical_label(normalized)
            result.other_counts[canonical] = result.other_counts.get(canonical, 0) + 1

    return result
