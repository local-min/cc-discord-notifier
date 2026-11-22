# anthropic-articles-notifier

[claude.dev](https://claude.dev/) のブログと [Anthropic Research](https://www.anthropic.com/research) の新着記事を GitHub Actions で毎時チェックし、タイトルと概要を Claude Haiku 5.5（`claude-haiku-5-5`）で日本語にして Discord チャンネルへ配信するワークフロー。

> このサブプロジェクトは GitHub Actions（`.github/workflows/articles.yml`、リポジトリ直下）から
> `anthropic-articles-notifier/` を作業ディレクトリとして実行される。

## 配信元

| key | 配信元 | 取得方法 |
| --- | --- | --- |
| `claude_dev` | claude.dev Blog | RSS（`https://claude.dev/rss.xml`）。タイトル・概要・公開日・著者・カテゴリを RSS からそのまま使う |
| `anthropic_research` | Anthropic Research | RSS が無いため `https://www.anthropic.com/sitemap.xml` から `/research/<slug>` を列挙し、未知の記事だけ記事ページの `og:title` / `og:description` / `article:published_time` / `og:image` を読む |

Anthropic Research で一覧ページ（`/research`）を使わないのは、一部の記事しか表示されないため。sitemap の `lastmod` は記事の編集でも更新されるので、公開日には使わない。

## 動作概要

- 毎時 37 分 (UTC) に `articles_notifier.main` を実行（毎時 0 分は GitHub 側の高負荷帯で schedule が欠落しやすいため回避）
- 配信元ごとに現在公開中の記事 URL を取得し、`state.json` の既読 URL と比べて未知のものを新着とする
- 新着は公開日の古い順に、タイトルと概要を日本語に訳して Discord へ Embed で投稿（原題・著者・公開日・サムネイル付き）
- 1 記事投稿するごとに `state.json` を更新し、ワークフローが commit / push する

### 誤通知を防ぐ仕組み

| 状況 | 挙動 |
| --- | --- |
| 配信元を初めて処理するとき | 現在の全記事を既読にするだけで配信しない（過去記事の遡及配信を避ける） |
| 公開日が 14 日（`MAX_AGE_DAYS`）より古い未知の記事 | 通知せず既読にする（URL 変更や過去記事の再掲への対策） |
| 1 回で未知の記事が 20 件を超えた | サイト構成の変更とみなし、通知せず既読にする |
| 記事 URL が 1 件も取れない | 失敗として終了する（サイト構成の変更に気づけるように） |

### 失敗時の挙動

- 投稿済みの記事は既読として保存されるため、次回は未投稿の記事だけが再処理される
- 記事ページの取得に失敗した記事は既読にせず、次回また試す（同じ配信元の他の記事は配信を続ける）
- 1 つの配信元が失敗しても、他の配信元の処理は続ける。失敗があればワークフローは失敗で終わる

## 必要な GitHub Actions Secrets

| 名前 | 内容 |
| --- | --- |
| `ANTHROPIC_API_KEY` | Claude API キー（Claude Console で発行）。翻訳に使う |
| `DISCORD_WEBHOOK_URL` | 配信先 Discord チャンネルの Webhook URL（リリース通知と共用） |

## 手動実行

Actions タブの `articles` ワークフローから `workflow_dispatch` で実行できる。

| 入力 | 内容 |
| --- | --- |
| `dry_run` | Discord に投稿せず、`state.json` も保存しない。ログに Embed を出す |
| `preview` | 既読かどうかに関係なく、各配信元の先頭 1 件（claude.dev は最新記事、Research は最近更新された記事）を処理する。`state.json` は更新しない。`dry_run` と組み合わせると翻訳結果の確認だけができ、外すと実際に投稿して見た目を確認できる |

PR では `pytest` と、`dry_run` + `preview` での実行が自動で走る。配信元サイトの構成変更や Claude API の応答形式の変化に、マージ前に気づくため。

## ローカルセットアップ

```bash
uv sync
uv run pytest
uv run ruff check .

# 実データでの確認（投稿なし・state 保存なし）
ANTHROPIC_API_KEY=... DRY_RUN=true PREVIEW=true uv run python -m articles_notifier.main
```

## 配信元の追加

`src/articles_notifier/sources/` に `Source` を継承したクラスを作り、`sources/__init__.py` の `all_sources()` に追加する。

- `discover()`: 現在公開中の記事 URL の一覧を返す
- `load(url)`: 1 記事分の詳細（タイトル・概要・公開日など）を返す
- `key` は `state.json` のキーになるので、一度決めたら変えない（変えると初回扱いになる）

新しい配信元は初回実行時に全記事が既読として登録されるだけなので、追加した直後に過去記事が大量に流れることはない。
