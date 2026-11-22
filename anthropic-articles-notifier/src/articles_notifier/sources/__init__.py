"""配信元の一覧。新しい配信元はここに追加する。"""

from __future__ import annotations

from .anthropic_research import AnthropicResearchSource
from .base import Source, SourceError
from .claude_dev import ClaudeDevSource

__all__ = ["Source", "SourceError", "all_sources"]


def all_sources() -> list[Source]:
    return [ClaudeDevSource(), AnthropicResearchSource()]
