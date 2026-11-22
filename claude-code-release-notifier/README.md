# claude-code-release-notifier

Anthropic の [Claude Code](https://github.com/anthropics/claude-code) の新リリースを GitHub Actions で毎時監視し、新機能と Breaking Change のみを Claude Haiku 5.5（`claude-haiku-5-5`）で日本語化して Discord チャンネルへ配信するワークフロー。

詳細な設計は [`doc/claude-code-discord-notifier-spec.md`](doc/claude-code-discord-notifier-spec.md) を参照。

> このサブプロジェクトは GitHub Actions（`.github/workflows/notify.yml`、リポジトリ直下）から
> `claude-code-release-notifier/` を作業ディレクトリとして実行される。

## 動作概要

- 毎時 23 分 (UTC) に GitHub Actions（`ubuntu-slim` ランナー）が `notifier.main` を実行（毎時 0 分は高負荷で schedule が欠落しやすいため回避）
- `anthropics/claude-code` の Releases API を `state.json` の `last_release_id` より新しいものに限定して取得
- 本文を行単位の正規表現でパースし、`Added` と `Breaking`/`Removed`/`Deprecated` を抽出、その他は件数のみ集計
- Claude Haiku 5.5 に構造化出力（effort `medium`）で項目をバッチ翻訳
- Discord Webhook へ Embed 形式で投稿 (Breaking: 赤、新機能のみ: 緑、それ以外: 灰)
- 配信成功したリリースごとに `state.json` を更新し `git commit && git push`
- 週次 `keepalive` ワークフローで 60 日非アクティブ停止を防止（直近 45 日コミットがない場合のみ空コミット）

## 手動実行

Actions タブの `notify` ワークフローから `workflow_dispatch` で実行できる。

| 入力 | 内容 |
| --- | --- |
| `dry_run` | Discord に投稿しない（ログに Embed を出す） |
| `preview` | 既読に関係なく最新リリースを 1 件処理する。`state.json` は更新しない。`dry_run` と組み合わせると翻訳結果の確認だけができ、外すと実際に投稿して見た目を確認できる |

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
| `ANTHROPIC_API_KEY` | Claude API キー（Claude Console で発行）。翻訳に使う |
| `DISCORD_WEBHOOK_URL` | 配信先 Discord チャンネルの Webhook URL |

> 備考: Secrets 名に `GITHUB_` プレフィックスは予約語のため使用できないので、PAT 側を `CC_GITHUB_PAT` として登録する。アプリ側は `GITHUB_PAT` 環境変数で受ける。

## 運用

- 初回実行 (`state.json` が空) は遡及配信を避けるため最新 1 件のみを処理済としてマーク
- 失敗時は `state.json` を更新せず、次回実行で同じリリースを再処理
- 1 リリース成功 → 即 state 更新 → commit のリリース単位トランザクション
