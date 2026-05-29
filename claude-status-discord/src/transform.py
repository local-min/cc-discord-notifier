"""Statuspage webhook payload -> Discord webhook payload (純Python・ランタイム非依存)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

IMPACT_COLOR = {"none": 0x95A5A6, "minor": 0xF1C40F, "major": 0xE67E22, "critical": 0xE74C3C}
RESOLVED_COLOR = 0x2ECC71
MAINTENANCE_COLOR = 0x3498DB

STATUS_JA = {
    "investigating": "調査中", "identified": "原因特定", "monitoring": "経過観測中",
    "resolved": "解決済み", "postmortem": "事後分析",
    "scheduled": "メンテナンス予定", "in_progress": "メンテナンス進行中",
    "verifying": "確認中", "completed": "メンテナンス完了",
}
IMPACT_JA = {"none": "なし", "minor": "軽微", "major": "重大", "critical": "致命的", "maintenance": "メンテナンス"}
COMPONENT_STATUS_JA = {
    "operational": "正常稼働", "degraded_performance": "性能低下",
    "partial_outage": "一部障害", "major_outage": "重大障害", "under_maintenance": "メンテナンス中",
}
IMPACT_ORDER = {"none": 0, "minor": 1, "major": 2, "critical": 3}
MAINTENANCE_STATUSES = {"scheduled", "in_progress", "verifying", "completed"}
STATUS_PAGE_BASE = "https://status.claude.com"


def _fmt_jst(iso: str | None) -> str | None:
    if not iso:
        return None
    s = iso.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M JST")


def _is_maintenance(incident: dict) -> bool:
    return incident.get("status") in MAINTENANCE_STATUSES or bool(incident.get("scheduled_for"))


def _latest_update_body(incident: dict) -> str | None:
    for u in (incident.get("incident_updates") or []):
        if u.get("body"):
            return u["body"]
    return None


def _mention(role_id: str | None):
    if role_id:
        return f"<@&{role_id}>", {"parse": [], "roles": [role_id]}
    return "", {"parse": []}


def build_incident_embed(event: dict, critical_role_id: str | None = None) -> dict:
    inc, page = event["incident"], event.get("page", {})
    is_maint = _is_maintenance(inc)
    status, impact = inc.get("status", ""), inc.get("impact", "none")

    if is_maint:
        color, kind = MAINTENANCE_COLOR, "メンテナンス"
    elif status == "resolved":
        color, kind = RESOLVED_COLOR, "インシデント"
    else:
        color, kind = IMPACT_COLOR.get(impact, IMPACT_COLOR["none"]), "インシデント"

    status_ja = STATUS_JA.get(status, status)
    fields = []
    if not is_maint:
        fields.append({"name": "影響度", "value": IMPACT_JA.get(impact, impact), "inline": True})
    fields.append({"name": "状態", "value": status_ja, "inline": True})
    if page.get("status_description"):
        fields.append({"name": "全体ステータス", "value": page["status_description"], "inline": True})
    for label, key in (("発生", "created_at"), ("更新", "updated_at"),
                       ("予定開始", "scheduled_for"), ("予定終了", "scheduled_until"), ("解決", "resolved_at")):
        v = _fmt_jst(inc.get(key))
        if v:
            fields.append({"name": label, "value": v, "inline": True})

    embed = {
        "title": f"[{kind}/{status_ja}] {inc.get('name', '(no title)')}"[:256],
        "url": inc.get("shortlink") or STATUS_PAGE_BASE,
        "color": color,
        "fields": fields[:25],
        "footer": {"text": "Claude Status"},
        "timestamp": (inc.get("updated_at") or inc.get("created_at") or "").replace("Z", "+00:00") or None,
    }
    body = _latest_update_body(inc)
    if body:
        embed["description"] = body[:4096]

    content, allowed = _mention(critical_role_id if (impact == "critical" and not is_maint) else None)
    return {"username": "Claude Status", "content": content, "allowed_mentions": allowed, "embeds": [embed]}


def build_component_embed(event: dict) -> dict:
    comp, cu, page = event.get("component", {}), event.get("component_update", {}), event.get("page", {})
    old = COMPONENT_STATUS_JA.get(cu.get("old_status"), cu.get("old_status"))
    new = COMPONENT_STATUS_JA.get(cu.get("new_status"), cu.get("new_status"))
    color = RESOLVED_COLOR if cu.get("new_status") == "operational" else IMPACT_COLOR["major"]
    embed = {
        "title": f"[コンポーネント変更] {comp.get('name', '(unknown)')}",
        "url": STATUS_PAGE_BASE, "color": color,
        "description": f"**{old}** → **{new}**", "fields": [],
        "footer": {"text": "Claude Status"},
        "timestamp": (cu.get("created_at") or "").replace("Z", "+00:00") or None,
    }
    if page.get("status_description"):
        embed["fields"].append({"name": "全体ステータス", "value": page["status_description"], "inline": True})
    return {"username": "Claude Status", "content": "", "allowed_mentions": {"parse": []}, "embeds": [embed]}


def build_discord_payload(event: dict, *, critical_role_id: str | None = None,
                          min_impact: str = "none", forward_components: bool = True) -> dict | None:
    """Discord Webhookペイロードを返す。フィルタで除外する場合はNone。"""
    if "incident" in event:
        impact = event["incident"].get("impact", "none")
        if impact in IMPACT_ORDER and IMPACT_ORDER[impact] < IMPACT_ORDER.get(min_impact, 0):
            return None
        return build_incident_embed(event, critical_role_id=critical_role_id)
    if "component_update" in event:
        return build_component_embed(event) if forward_components else None
    return None
