# cc-discord-notifier

Anthropic の [Claude Code](https://github.com/anthropics/claude-code) の新リリースを GitHub Actions で毎時監視し、新機能と Breaking Change のみを Gemini 2.5 Flash で日本語化して Discord チャンネルへ配信するワークフロー。

詳細な設計は [`doc/claude-code-discord-notifier-spec.md`](doc/claude-code-discord-notifier-spec.md) を参照。

## 動作概要

- 毎時 0 分 (UTC) に GitHub Actions が `notifier.main` を実行
- `anthropics/claude-code` の Releases API を `state.json` の `last_release_id` より新しいものに限定して取得
- 本文を行単位の正規表現でパースし、`Added` と `Breaking`/`Removed`/`Deprecated` を抽出、その他は件数のみ集計
- Gemini 2.5 Flash に対し `thinking_budget=0` / 構造化出力で項目をバッチ翻訳
- Discord Webhook へ Embed 形式で投稿 (Breaking: 赤、新機能のみ: 緑、それ以外: 灰)
- 配信成功したリリースごとに `state.json` を更新し `git commit && git push`
- 週次 `keepalive` ワークフローで 60 日非アクティブ停止を防止

## ローカルセットアップ

```bash
uv sync
uv run pytest
uv run ruff check .
```

## 必要な GitHub Actions Secrets

| 名前 | 内容 |
| --- | --- |
| `CC_GITHUB_PAT` | `anthropics/claude-code` の Releases 読取用 Fine-grained PAT (Public Repositories read-only) |
| `GEMINI_API_KEY` | Google AI Studio で発行した Gemini API キー |
| `DISCORD_WEBHOOK_URL` | 配信先 Discord チャンネルの Webhook URL |

> 備考: Secrets 名に `GITHUB_` プレフィックスは予約語のため使用できないので、PAT 側を `CC_GITHUB_PAT` として登録する。アプリ側は `GITHUB_PAT` 環境変数で受ける。

## 運用

- 初回実行 (`state.json` が空) は遡及配信を避けるため最新 1 件のみを処理済としてマーク
- 失敗時は `state.json` を更新せず、次回実行で同じリリースを再処理
- 1 リリース成功 → 即 state 更新 → commit のリリース単位トランザクション
