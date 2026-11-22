"""環境変数の読込とバリデーション。"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """設定不足などの構成エラー。"""


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Config:
    """ワークフロー実行に必要な設定値。"""

    gemini_api_key: str
    discord_webhook_url: str
    state_path: str = "state.json"
    # 公開日がこの日数より古い未知の記事は、通知せず既読扱いにする
    # （URL 変更や過去記事の再掲で誤通知しないため）。
    max_age_days: int = 14
    dry_run: bool = False
    # 既読かどうかに関係なく各配信元の一覧の先頭 1 件（claude.dev は最新記事、Research は
    # 最近更新された記事）を処理し、state は更新しない（動作確認用）。
    preview: bool = False

    @classmethod
    def from_env(cls) -> Config:
        dry_run = _flag("DRY_RUN")
        preview = _flag("PREVIEW")

        missing: list[str] = []

        def _require(name: str, *, required: bool = True) -> str:
            value = os.environ.get(name, "").strip()
            if not value and required:
                missing.append(name)
            return value

        gemini_api_key = _require("GEMINI_API_KEY")
        # dry run では投稿しないため Webhook URL は任意
        discord_webhook_url = _require("DISCORD_WEBHOOK_URL", required=not dry_run)

        if missing:
            raise ConfigError("必須環境変数が未設定です: " + ", ".join(missing))

        try:
            max_age_days = int(os.environ.get("MAX_AGE_DAYS", "14"))
        except ValueError as e:
            raise ConfigError("MAX_AGE_DAYS は整数で指定してください") from e

        return cls(
            gemini_api_key=gemini_api_key,
            discord_webhook_url=discord_webhook_url,
            state_path=os.environ.get("STATE_PATH", "state.json"),
            max_age_days=max_age_days,
            dry_run=dry_run,
            preview=preview,
        )
