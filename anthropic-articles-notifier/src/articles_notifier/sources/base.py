"""配信元の共通インターフェース。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

import httpx

from ..models import Article


class SourceError(RuntimeError):
    """配信元からの取得・解析の失敗。"""


class Source(ABC):
    """新着記事の取得元。

    discover() で現在公開中の記事 URL を列挙し、未知の URL についてだけ load() で詳細を取る。
    一覧取得が軽く、詳細取得が重い（記事ページを 1 件ずつ取る）配信元でも、
    無駄な取得をしないための分割。
    """

    key: ClassVar[str]
    """state.json のキー。変更すると既読情報を失うので固定する。"""
    label: ClassVar[str]
    """Discord に表示する配信元名。"""
    home_url: ClassVar[str]
    color: ClassVar[int]

    @abstractmethod
    def discover(self, client: httpx.Client) -> list[str]:
        """現在公開されている記事 URL の一覧を返す。"""

    @abstractmethod
    def load(self, client: httpx.Client, url: str) -> Article:
        """URL 1 件分の記事情報を返す。"""
