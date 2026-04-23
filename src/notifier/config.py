"""環境変数の読込とバリデーション。"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """設定不足などの構成エラー。"""


@dataclass(frozen=True)
class Config:
    """ワークフロー実行に必要な設定値。"""

    github_pat: str
    gemini_api_key: str
    discord_webhook_url: str
    target_repo: str = "anthropics/claude-code"
    state_path: str = "state.json"
    dry_run: bool = False

    @classmethod
    def from_env(cls) -> Config:
        missing: list[str] = []

        def _require(name: str) -> str:
            value = os.environ.get(name, "").strip()
            if not value:
                missing.append(name)
            return value

        github_pat = _require("GITHUB_PAT")
        gemini_api_key = _require("GEMINI_API_KEY")
        discord_webhook_url = _require("DISCORD_WEBHOOK_URL")

        if missing:
            raise ConfigError(
                "必須環境変数が未設定です: " + ", ".join(missing)
            )

        return cls(
            github_pat=github_pat,
            gemini_api_key=gemini_api_key,
            discord_webhook_url=discord_webhook_url,
            target_repo=os.environ.get("TARGET_REPO", "anthropics/claude-code"),
            state_path=os.environ.get("STATE_PATH", "state.json"),
            dry_run=os.environ.get("DRY_RUN", "").lower() in {"1", "true", "yes"},
        )
