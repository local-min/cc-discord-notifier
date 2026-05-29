import json
from urllib.parse import urlparse

from transform import build_discord_payload
from workers import Response, WorkerEntrypoint, fetch


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # --- 1. メソッド・パスのシークレット検証 ---
        if request.method != "POST":
            return Response("Method Not Allowed", status=405)

        # 期待パス: /sp/<RELAY_SECRET>
        path = urlparse(request.url).path
        expected = f"/sp/{self.env.RELAY_SECRET}"
        if path != expected:
            return Response("Forbidden", status=403)

        # --- 2. JSON解析（JS Proxy → Python dict） ---
        try:
            js_body = await request.json()
            # ランタイムにより request.json() は dict を返すことも JsProxy を返すこともある。
            # JsProxy のときだけ .to_py() で Python dict に変換する。
            event = js_body.to_py() if hasattr(js_body, "to_py") else js_body
        except Exception:
            # 解析不能でも200を返し、Statuspageのリトライ嵐を避ける
            return Response("Bad payload", status=200)

        # --- 3. Discordペイロードへ変換 ---
        critical_role_id = getattr(self.env, "CRITICAL_ROLE_ID", None) or None
        min_impact = getattr(self.env, "MIN_IMPACT", "none") or "none"
        forward_components = (getattr(self.env, "FORWARD_COMPONENTS", "true") or "true").lower() != "false"

        payload = build_discord_payload(
            event,
            critical_role_id=critical_role_id,
            min_impact=min_impact,
            forward_components=forward_components,
        )
        if payload is None:
            return Response("Filtered", status=200)  # 対象外イベント

        # --- 4. Discord Webhookへ転送 ---
        try:
            resp = await fetch(
                self.env.DISCORD_WEBHOOK_URL,
                method="POST",
                headers={"Content-Type": "application/json"},
                body=json.dumps(payload),
            )
            if resp.status >= 300:
                # Discord側エラーはログのみ。Statuspageには200を返す
                print(f"Discord webhook failed: status={resp.status}")
        except Exception as e:
            # 例外内容には秘匿URLが混ざりうるため型名のみログ
            print(f"Discord webhook exception: {type(e).__name__}")

        return Response("OK", status=200)
