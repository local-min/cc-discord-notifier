"""main.process_source の新着判定・state 更新のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from articles_notifier.main import MAX_NEW_PER_RUN, process_source
from articles_notifier.models import Article, ArticleTranslation, SourceState, State
from articles_notifier.sources import Source, SourceError

NOW = datetime(2026, 11, 22, 0, 0, tzinfo=UTC)


class FakeSource(Source):
    key = "fake"
    label = "Fake Blog"
    home_url = "https://fake.example/"
    color = 0x123456

    def __init__(self, articles: list[Article], *, broken: set[str] | None = None) -> None:
        self._articles = {a.url: a for a in articles}
        self._broken = broken or set()
        self.loaded: list[str] = []

    def discover(self, client) -> list[str]:
        return list(self._articles)

    def load(self, client, url: str) -> Article:
        self.loaded.append(url)
        if url in self._broken:
            raise RuntimeError("boom")
        return self._articles[url]


def _article(slug: str, days_ago: int | None = 1) -> Article:
    published = None if days_ago is None else NOW - timedelta(days=days_ago)
    url = f"https://fake.example/{slug}"
    return Article(url=url, title=f"Title {slug}", published_at=published)


class Recorder:
    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.posted: list[str] = []
        self.persist_count = 0
        self._fail_on = fail_on or set()

    def translate(self, article: Article) -> ArticleTranslation:
        if article.url in self._fail_on:
            raise RuntimeError("translation failed")
        return ArticleTranslation(title_ja=f"訳 {article.title}", summary_ja="")

    def post(self, embed: dict) -> None:
        self.posted.append(embed["url"])

    def persist(self) -> None:
        self.persist_count += 1


def _run(source: Source, state: State, rec: Recorder, *, preview: bool = False) -> bool:
    return process_source(
        source,
        None,  # FakeSource は HTTP クライアントを使わない
        state,
        max_age_days=14,
        preview=preview,
        translate=rec.translate,
        post=rec.post,
        persist=rec.persist,
        now=NOW,
    )


def test_first_run_seeds_without_posting() -> None:
    source = FakeSource([_article("a"), _article("b")])
    state, rec = State(), Recorder()
    assert _run(source, state, rec)
    assert rec.posted == []
    assert sorted(state.sources["fake"].seen) == [
        "https://fake.example/a",
        "https://fake.example/b",
    ]
    assert rec.persist_count == 1
    assert source.loaded == []  # 初回は記事ページを取りに行かない


def test_posts_only_unknown_articles_oldest_first() -> None:
    source = FakeSource([_article("new2", days_ago=1), _article("old"), _article("new1", 3)])
    state = State(sources={"fake": SourceState(seen=["https://fake.example/old"])})
    rec = Recorder()
    assert _run(source, state, rec)
    assert rec.posted == ["https://fake.example/new1", "https://fake.example/new2"]
    assert source.loaded == ["https://fake.example/new2", "https://fake.example/new1"]
    assert set(state.sources["fake"].seen) == {
        "https://fake.example/old",
        "https://fake.example/new1",
        "https://fake.example/new2",
    }
    assert rec.persist_count == 2  # 1 件投稿するごとに保存


def test_stale_articles_are_marked_seen_without_posting() -> None:
    source = FakeSource([_article("ancient", days_ago=30), _article("undated", days_ago=None)])
    state = State(sources={"fake": SourceState(seen=[])})
    rec = Recorder()
    assert _run(source, state, rec)
    # 公開日が 14 日より前の記事は通知しない。公開日が不明な記事は新着として扱う
    assert rec.posted == ["https://fake.example/undated"]
    assert "https://fake.example/ancient" in state.sources["fake"].seen


def test_too_many_unknown_articles_are_marked_seen() -> None:
    articles = [_article(f"p{i}") for i in range(MAX_NEW_PER_RUN + 1)]
    source = FakeSource(articles)
    state = State(sources={"fake": SourceState(seen=[])})
    rec = Recorder()
    assert _run(source, state, rec)
    assert rec.posted == []
    assert source.loaded == []
    assert len(state.sources["fake"].seen) == MAX_NEW_PER_RUN + 1


def test_load_failure_skips_only_that_article() -> None:
    source = FakeSource([_article("bad"), _article("good")], broken={"https://fake.example/bad"})
    state = State(sources={"fake": SourceState(seen=[])})
    rec = Recorder()
    assert _run(source, state, rec) is False
    assert rec.posted == ["https://fake.example/good"]
    # 取得に失敗した記事は既読にせず、次回また試す
    assert state.sources["fake"].seen == ["https://fake.example/good"]


def test_delivery_failure_stops_and_keeps_unposted_unseen() -> None:
    source = FakeSource([_article("first", 3), _article("second", 2), _article("third", 1)])
    state = State(sources={"fake": SourceState(seen=[])})
    rec = Recorder(fail_on={"https://fake.example/second"})
    assert _run(source, state, rec) is False
    assert rec.posted == ["https://fake.example/first"]
    assert state.sources["fake"].seen == ["https://fake.example/first"]


def test_empty_discovery_raises() -> None:
    with pytest.raises(SourceError):
        _run(FakeSource([]), State(), Recorder())


def test_preview_processes_first_article_without_touching_state() -> None:
    source = FakeSource([_article("latest"), _article("other")])
    state = State(sources={"fake": SourceState(seen=["https://fake.example/latest"])})
    rec = Recorder()
    assert _run(source, state, rec, preview=True)
    assert rec.posted == ["https://fake.example/latest"]
    assert state.sources["fake"].seen == ["https://fake.example/latest"]
    assert rec.persist_count == 0
