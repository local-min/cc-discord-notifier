"""定期実行ワークフローのエントリポイント。"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from . import discord_client
from .config import Config, ConfigError
from .http import new_client
from .models import Article, ArticleTranslation, SourceState, State
from .sources import Source, SourceError, all_sources
from .state import load_state, save_state

logger = logging.getLogger("articles_notifier")

# 1 回で見つかった未知の記事がこれを超えたら、サイト構成の変更（URL の一斉変更など）とみなし
# 通知せずに既読扱いにする。大量の誤通知を防ぐための安全弁。
MAX_NEW_PER_RUN = 20

Translate = Callable[[Article], ArticleTranslation]
Post = Callable[[dict], None]
Persist = Callable[[], None]


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _deliver(source: Source, article: Article, translate: Translate, post: Post) -> None:
    translation = translate(article)
    embed = discord_client.build_embed(
        article,
        translation,
        source_label=source.label,
        source_url=source.home_url,
        color=source.color,
    )
    post(embed)
    logger.info("%s: 配信完了 %s", source.label, article.url)


def process_source(
    source: Source,
    http: httpx.Client,
    state: State,
    *,
    max_age_days: int,
    preview: bool,
    translate: Translate,
    post: Post,
    persist: Persist,
    now: datetime,
) -> bool:
    """1 配信元分の処理。すべて成功したら True を返す。

    記事 1 件ごとに「翻訳 → 投稿 → 既読に追加 → state 保存」を行う。途中で失敗しても、
    投稿済みの記事は既読として保存されているため、次回は未投稿の記事だけが再処理される。
    """
    urls = source.discover(http)
    if not urls:
        # サイト構成が変わって 1 件も取れなくなった可能性が高い。黙って成功扱いにせず失敗させる。
        raise SourceError(f"{source.label}: 記事 URL を 1 件も取得できなかった")
    logger.info("%s: 公開中 %d 件", source.label, len(urls))

    if preview:
        logger.info("%s: プレビューとして先頭 1 件を処理（state は更新しない）", source.label)
        _deliver(source, source.load(http, urls[0]), translate, post)
        return True

    current = state.sources.get(source.key)
    if current is None:
        # 初回は過去記事の遡及配信を避け、現在の全件を既読にするだけ
        state.sources[source.key] = SourceState(seen=list(urls))
        persist()
        logger.info("%s: 初回のため %d 件を既読として登録（配信なし）", source.label, len(urls))
        return True

    seen = set(current.seen)
    new_urls = [u for u in urls if u not in seen]
    logger.info("%s: 未知の記事 %d 件", source.label, len(new_urls))
    if not new_urls:
        return True

    if len(new_urls) > MAX_NEW_PER_RUN:
        logger.warning(
            "%s: 未知の記事が %d 件（上限 %d）。URL の一斉変更とみなし、通知せず既読にする",
            source.label,
            len(new_urls),
            MAX_NEW_PER_RUN,
        )
        current.seen.extend(new_urls)
        persist()
        return True

    ok = True
    articles: list[Article] = []
    for url in new_urls:
        try:
            articles.append(source.load(http, url))
        except Exception as e:
            # 既読にはしないので次回また試す。他の新着記事の配信は続ける
            logger.error("%s: 記事情報の取得に失敗 %s: %s", source.label, url, e)
            ok = False

    cutoff = now - timedelta(days=max_age_days)
    fresh: list[Article] = []
    stale: list[Article] = []
    for a in articles:
        (stale if a.published_at and a.published_at < cutoff else fresh).append(a)
    if stale:
        for a in stale:
            logger.info(
                "%s: 公開日が %d 日より前のため通知せず既読にする %s (%s)",
                source.label,
                max_age_days,
                a.url,
                a.published_at.date() if a.published_at else "-",
            )
        current.seen.extend(a.url for a in stale)
        persist()

    # 古い記事から順に投稿する
    fresh.sort(key=lambda a: a.published_at or now)
    for article in fresh:
        try:
            _deliver(source, article, translate, post)
        except Exception as e:
            logger.exception("%s: 配信に失敗 %s: %s", source.label, article.url, e)
            return False
        current.seen.append(article.url)
        persist()
    return ok


def run() -> int:
    _configure_logging()
    try:
        config = Config.from_env()
    except ConfigError as e:
        logger.error("設定エラー: %s", e)
        return 2

    state = load_state(config.state_path)
    for key, src in state.sources.items():
        logger.info("state: %s 既読 %d 件", key, len(src.seen))

    gemini_client = None

    def translate(article: Article) -> ArticleTranslation:
        nonlocal gemini_client
        from .summarizer import new_client, translate_article

        if gemini_client is None:
            gemini_client = new_client(config.gemini_api_key)
        return translate_article(gemini_client, article)

    def post(embed: dict) -> None:
        if config.dry_run:
            logger.info("DRY_RUN: Discord 投稿をスキップ (embed=%s)", embed)
        else:
            discord_client.post_embed(config.discord_webhook_url, embed)

    def persist() -> None:
        if config.dry_run:
            logger.info("DRY_RUN: state の保存をスキップ")
        else:
            save_state(config.state_path, state)

    now = datetime.now(UTC)
    failed = False
    with new_client() as http:
        for source in all_sources():
            try:
                ok = process_source(
                    source,
                    http,
                    state,
                    max_age_days=config.max_age_days,
                    preview=config.preview,
                    translate=translate,
                    post=post,
                    persist=persist,
                    now=now,
                )
            except Exception as e:
                # 1 つの配信元の失敗で他の配信元を止めない
                logger.exception("%s: 処理に失敗: %s", source.label, e)
                ok = False
            failed = failed or not ok

    return 1 if failed else 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
