# cc-discord-notifier

Claude 関連の通知を Discord チャンネルへ日本語で配信するためのリポジトリ。
目的・配信元・デプロイ先の異なる **3 つのサブプロジェクト** を同居させている。
各サブプロジェクトの詳細は、それぞれの README を参照。

## サブプロジェクト

| サブプロジェクト | 配信元 | 方式 / デプロイ先 | README |
| --- | --- | --- | --- |
| **claude-code-release-notifier** | `anthropics/claude-code` の GitHub Releases | ポーリング（GitHub Actions・毎時 cron） | [README](claude-code-release-notifier/README.md) |
| **claude-status-discord** | `status.claude.com`（Statuspage）の障害・メンテナンス | Webhook プッシュ（Cloudflare Python Workers） | [README](claude-status-discord/README.md) |
| **anthropic-articles-notifier** | `claude.dev` のブログ / `anthropic.com/research` の新着記事 | ポーリング（GitHub Actions・毎時 cron） | [README](anthropic-articles-notifier/README.md) |

各サブプロジェクトは独立しており、相互に依存しない。
anthropic-articles-notifier は 2 サイトを 1 つにまとめている。違うのは新着の取り方（RSS か sitemap か）だけで、
差分検出・日本語化・Discord 投稿・スケジュールは共通のため。配信元を足すときは取得部分を 1 つ追加する。

## ディレクトリ構成

```
cc-discord-notifier/
├── README.md                       # 本ファイル（リポジトリ全体の入口）
├── .github/workflows/              # GitHub Actions（仕様上リポジトリ直下に固定）
│   ├── notify.yml                  # claude-code-release-notifier を毎時実行
│   ├── articles.yml                # anthropic-articles-notifier を毎時実行（PR ではテスト）
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
├── claude-status-discord/          # サブプロジェクト2: Statuspage 転送（Cloudflare Worker）
│   ├── README.md
│   ├── wrangler.jsonc
│   ├── doc/claude-status-to-discord-guide.md
│   ├── src/                        # entry.py / transform.py
│   └── tests/
│
└── anthropic-articles-notifier/    # サブプロジェクト3: 記事配信（Python / GitHub Actions）
    ├── README.md
    ├── pyproject.toml
    ├── state.json                  # 配信元ごとの既読記事 URL
    ├── src/articles_notifier/
    │   └── sources/                # 配信元ごとの取得処理（claude_dev / anthropic_research）
    └── tests/
```

> 補足: GitHub Actions のワークフローはリポジトリ直下の `.github/workflows/` に置く必要があるため、
> `notify.yml` / `articles.yml` はそれぞれのサブプロジェクトを作業ディレクトリとして実行する設定にしている。
