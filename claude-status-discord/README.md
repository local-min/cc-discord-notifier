# claude-status-discord

`status.claude.com`（Atlassian Statuspage）の Webhook を Cloudflare Python Workers で受け取り、
日本語のリッチ Embed に変換して Discord チャンネルへ転送するリレー。

Statuspage の Webhook ペイロードは Discord 形式と非互換なため、間に変換リレーを挟む。
詳細な設計・背景は [`doc/claude-status-to-discord-guide.md`](doc/claude-status-to-discord-guide.md) を参照。

> 本サブプロジェクトは、同リポジトリの `claude-code-release-notifier/`（GitHub Actions による
> Claude Code リリース配信）とは独立した別系統。デプロイ先も別（Cloudflare Workers）。

## 構成

```
claude-status-discord/
├── pyproject.toml          # ローカルテスト用（pytest）
├── wrangler.jsonc          # Worker 設定
├── .dev.vars.example       # ローカル開発用シークレットのひな型
├── src/
│   ├── entry.py            # Worker エントリ（受信・パスシークレット検証・転送）
│   └── transform.py        # ペイロード変換（純 Python・ランタイム非依存）
└── tests/
    └── test_transform.py   # transform.py の単体テスト
```

## 設定値

| 変数 | 区分 | 既定 | 説明 |
| --- | --- | --- | --- |
| `DISCORD_WEBHOOK_URL` | シークレット | （必須） | 配信先 Discord チャンネルの Webhook URL |
| `RELAY_SECRET` | シークレット | （必須） | エンドポイント保護用のランダム文字列（`/sp/<RELAY_SECRET>`） |
| `MIN_IMPACT` | vars | `none` | 転送する最小影響度（`none`/`minor`/`major`/`critical`） |
| `FORWARD_COMPONENTS` | vars | `true` | コンポーネント変更通知を転送するか |
| `CRITICAL_ROLE_ID` | vars（任意） | 未設定 | critical インシデント時にメンションするロール ID |

`DISCORD_WEBHOOK_URL` と `RELAY_SECRET` は `vars` に書かず `wrangler secret put` で登録する。

## ローカルでの単体テスト（ネットワーク不要）

```bash
cd claude-status-discord
uv run --with pytest pytest tests/
```

## ローカル Worker 起動

```bash
cd claude-status-discord
cp .dev.vars.example .dev.vars   # 値を埋める
uvx workers-py dev
```

疎通テスト（別ターミナル）:

```bash
SECRET="<.dev.vars に設定した RELAY_SECRET>"
URL="http://localhost:8787/sp/${SECRET}"
curl -X POST "$URL" -H "Content-Type: application/json" -d '{
  "page": {"id":"tymt9n04zgry","status_indicator":"major","status_description":"Partial System Outage"},
  "incident": {
    "name":"テスト通知","status":"investigating","impact":"major",
    "created_at":"2026-05-29T00:00:00Z","updated_at":"2026-05-29T00:00:00Z",
    "shortlink":"https://status.claude.com",
    "incident_updates":[{"body":"これはテストです","status":"investigating","created_at":"2026-05-29T00:00:00Z"}]
  }
}'
```

Discord に Embed が届けば成功。シークレットを誤った URL では 403 が返る。

## デプロイ

```bash
uvx workers-py secret put DISCORD_WEBHOOK_URL
uvx workers-py secret put RELAY_SECRET        # 例: openssl rand -hex 24
uvx workers-py deploy
```

> `compatibility_date` はデプロイ時点の日付に更新する（未来日にしない）。

デプロイ後の購読 URL は次の形式:

```
https://claude-status-discord.<account>.workers.dev/sp/<RELAY_SECRET>
```

## Statuspage 側で購読

1. `https://status.claude.com` を開き、購読（ベルアイコン）から **Webhook** を選ぶ。
2. 送信先 URL に上記のシークレット付き URL を入力して購読する。
3. 以降、インシデントの作成・更新・解決、メンテナンス、コンポーネント変更が Discord へ流れる。

## 留意点

- **ステートレス設計**: 1 インシデントの更新ごとに別メッセージが届く。
- **Discord 転送失敗時も Statuspage には 200 を返す**（5xx による再送嵐・重複投稿を防ぐ）。
- Python Workers はオープンベータ。`workers-py`/`pywrangler` のコマンドは Cloudflare の最新ドキュメントを確認。
