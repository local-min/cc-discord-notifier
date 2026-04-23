"""毎時ワークフローのエントリポイント。"""

from __future__ import annotations

import logging
import sys

from . import discord_client
from .config import Config, ConfigError
from .github_client import fetch_releases
from .models import GitHubRelease, ParsedRelease, State
from .parser import parse_release_body
from .state import load_state, save_state
from .summarizer import translate_release_items

logger = logging.getLogger("notifier")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _build_translations(
    gemini_client,
    parsed: ParsedRelease,
) -> tuple[list[str], list[str]]:
    """Added/Breaking をバッチで一括翻訳し、分割して返す。"""
    combined = parsed.added + parsed.breaking
    if not combined:
        return [], []
    translated = translate_release_items(gemini_client, combined)
    added_ja = translated[: len(parsed.added)]
    breaking_ja = translated[len(parsed.added) :]
    return added_ja, breaking_ja


def _process_release(
    release: GitHubRelease,
    config: Config,
    gemini_client,
) -> None:
    """1 リリース分の配信処理。失敗時は例外を送出する。"""
    logger.info("処理開始: %s (id=%d)", release.tag_name, release.id)
    parsed = parse_release_body(release.body)
    logger.info(
        "パース結果: Added=%d, Breaking=%d, Other=%d",
        len(parsed.added),
        len(parsed.breaking),
        parsed.other_total,
    )

    if parsed.added or parsed.breaking:
        added_ja, breaking_ja = _build_translations(gemini_client, parsed)
    else:
        added_ja, breaking_ja = [], []

    embed = discord_client.build_embed(release, parsed, added_ja, breaking_ja)
    if config.dry_run:
        logger.info("DRY_RUN: Discord 投稿をスキップ (embed=%s)", embed)
    else:
        discord_client.post_embed(config.discord_webhook_url, embed)
    logger.info("配信完了: %s", release.tag_name)


def run() -> int:
    _configure_logging()
    try:
        config = Config.from_env()
    except ConfigError as e:
        logger.error("設定エラー: %s", e)
        return 2

    state = load_state(config.state_path)
    logger.info("現在の state: %s", state.model_dump(mode="json"))

    releases = fetch_releases(
        config.target_repo,
        config.github_pat,
        since_id=state.last_release_id,
    )
    logger.info("新規リリース: %d 件", len(releases))
    if not releases:
        return 0

    # 初回実行時（state が空）は、直近 1 件のみを処理対象としてマークするだけで配信はスキップする。
    # 過去分の遡及配信を避ける仕様（spec 4.2）。
    if state.last_release_id is None:
        latest = releases[-1]
        logger.info(
            "初回実行のため配信はスキップし、最新 %s を処理済としてマーク",
            latest.tag_name,
        )
        _commit_state(config, latest)
        return 0

    from google import genai

    gemini_client = genai.Client(api_key=config.gemini_api_key)

    for release in releases:
        try:
            _process_release(release, config, gemini_client)
        except Exception as e:
            logger.exception("リリース処理に失敗: %s", e)
            return 1
        _commit_state(config, release)

    return 0


def _commit_state(config: Config, release: GitHubRelease) -> None:
    new_state = State(
        last_release_id=release.id,
        last_tag_name=release.tag_name,
        last_published_at=release.published_at,
    )
    save_state(config.state_path, new_state)
    logger.info("state 更新: last_release_id=%d tag=%s", release.id, release.tag_name)


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
