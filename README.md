# cc-discord-notifier

Claude 関連の通知を Discord チャンネルへ日本語で配信するためのリポジトリ。
目的・配信元・デプロイ先の異なる **2 つのサブプロジェクト** を同居させている。
各サブプロジェクトの詳細は、それぞれの README を参照。

## サブプロジェクト

| サブプロジェクト | 配信元 | 方式 / デプロイ先 | README |
| --- | --- | --- | --- |
| **claude-code-release-notifier** | `anthropics/claude-code` の GitHub Releases | ポーリング（GitHub Actions・毎時 cron） | [README](claude-code-release-notifier/README.md) |
| **claude-status-discord** | `status.claude.com`（Statuspage）の障害・メンテナンス | Webhook プッシュ（Cloudflare Python Workers） | [README](claude-status-discord/README.md) |

両者はアーキテクチャもデプロイ先も独立しており、相互に依存しない。

## ディレクトリ構成

```
cc-discord-notifier/
├── README.md                       # 本ファイル（リポジトリ全体の入口）
├── .github/workflows/              # GitHub Actions（仕様上リポジトリ直下に固定）
│   ├── notify.yml                  # claude-code-release-notifier を毎時実行
│   └── keepalive.yml               # 60 日非アクティブ停止の回避
│
├── claude-code-release-notifier/   # サブプロジェクト1: リリース配信（Python / GitHub Actions）
│   ├── README.md
│   ├── pyproject.toml
│   ├── state.json                  # 処理済みリリースの状態
│   ├── doc/claude-code-discord-notifier-spec.md
│   ├── src/notifier/
│   └── tests/
│
└── claude-status-discord/          # サブプロジェクト2: Statuspage 転送（Cloudflare Worker）
    ├── README.md
    ├── wrangler.jsonc
    ├── doc/claude-status-to-discord-guide.md
    ├── src/                        # entry.py / transform.py
    └── tests/
```

> 補足: GitHub Actions のワークフローはリポジトリ直下の `.github/workflows/` に置く必要があるため、
> `notify.yml` は `claude-code-release-notifier/` を作業ディレクトリとして実行する設定にしている。
