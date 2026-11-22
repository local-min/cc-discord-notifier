"""テキスト整形の小物。"""

from __future__ import annotations

import html
import re

_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def clean_text(value: str | None) -> str:
    """HTML タグを除き、実体参照を戻し、連続空白を 1 つにまとめる。"""
    if not value:
        return ""
    text = html.unescape(_TAG.sub(" ", value))
    return _SPACES.sub(" ", text).strip()
