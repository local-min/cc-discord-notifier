"""pydantic モデル定義。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Article(BaseModel):
    """通知対象の記事 1 件。URL を記事の識別子として扱う。"""

    url: str
    title: str
    summary: str | None = None
    published_at: datetime | None = None
    author: str | None = None
    category: str | None = None
    image_url: str | None = None


class SourceState(BaseModel):
    """配信元ごとの状態。既に把握済みの記事 URL を保持する。"""

    seen: list[str] = Field(default_factory=list)


class State(BaseModel):
    """state.json の構造。キーは配信元の key（例: "claude_dev"）。"""

    sources: dict[str, SourceState] = Field(default_factory=dict)


class ArticleTranslation(BaseModel):
    """Claude から構造化出力で受け取る翻訳結果。"""

    title_ja: str = Field(description="記事タイトルの日本語訳")
    summary_ja: str = Field(description="概要の日本語訳。入力の概要が空の場合は空文字")
