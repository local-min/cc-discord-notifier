"""pydantic モデル定義。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GitHubRelease(BaseModel):
    """GitHub Releases API のレスポンス要素。"""

    id: int
    tag_name: str
    name: str | None = None
    html_url: str
    body: str | None = None
    published_at: datetime
    draft: bool = False
    prerelease: bool = False


class ParsedRelease(BaseModel):
    """リリース本文のパース結果。"""

    added: list[str] = Field(default_factory=list)
    breaking: list[str] = Field(default_factory=list)
    other_counts: dict[str, int] = Field(default_factory=dict)

    @property
    def other_total(self) -> int:
        return sum(self.other_counts.values())


class State(BaseModel):
    """state.json の構造。"""

    last_release_id: int | None = None
    last_tag_name: str | None = None
    last_published_at: datetime | None = None


class TranslationResponse(BaseModel):
    """Gemini から受領する翻訳結果の構造。"""

    translations: list[str] = Field(
        description=(
            "入力された英語原文と同じ長さ・同じ順序の日本語訳配列。"
            "各要素はラベル + 半角スペース + 日本語本文（80 文字以内）の形式。"
        ),
    )
