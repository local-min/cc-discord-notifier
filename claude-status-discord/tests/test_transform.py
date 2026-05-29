"""transform.py の単体テスト（ランタイム非依存・ネットワーク不要）。"""
from __future__ import annotations

from transform import (
    IMPACT_COLOR,
    MAINTENANCE_COLOR,
    RESOLVED_COLOR,
    build_discord_payload,
)


def _incident_event(**overrides) -> dict:
    inc = {
        "name": "Elevated errors on the API",
        "status": "investigating",
        "impact": "major",
        "created_at": "2026-05-29T00:00:00Z",
        "updated_at": "2026-05-29T00:05:00Z",
        "resolved_at": None,
        "scheduled_for": None,
        "scheduled_until": None,
        "shortlink": "http://stspg.io/abc",
        "incident_updates": [
            {"body": "調査を開始しました", "status": "investigating", "created_at": "2026-05-29T00:00:00Z"}
        ],
    }
    inc.update(overrides)
    return {
        "page": {"id": "tymt9n04zgry", "status_indicator": "major",
                 "status_description": "Partial System Outage"},
        "incident": inc,
    }


def _component_event(old: str, new: str) -> dict:
    return {
        "page": {"id": "tymt9n04zgry", "status_indicator": "major",
                 "status_description": "Partial System Outage"},
        "component_update": {"old_status": old, "new_status": new,
                             "created_at": "2026-05-29T00:00:00Z"},
        "component": {"name": "API", "status": new},
    }


def _fields(payload: dict) -> dict[str, str]:
    return {f["name"]: f["value"] for f in payload["embeds"][0]["fields"]}


def test_incident_investigating_major():
    payload = build_discord_payload(_incident_event())
    embed = payload["embeds"][0]
    assert embed["title"].startswith("[インシデント/調査中]")
    assert embed["color"] == IMPACT_COLOR["major"]
    fields = _fields(payload)
    assert fields["影響度"] == "重大"
    assert fields["状態"] == "調査中"
    assert "発生" in fields
    assert embed["description"] == "調査を開始しました"
    # 既定ではメンションなし
    assert payload["content"] == ""
    assert payload["allowed_mentions"] == {"parse": []}


def test_incident_resolved_is_green():
    payload = build_discord_payload(
        _incident_event(status="resolved", resolved_at="2026-05-29T01:00:00Z")
    )
    embed = payload["embeds"][0]
    assert embed["title"].startswith("[インシデント/解決済み]")
    assert embed["color"] == RESOLVED_COLOR
    assert "解決" in _fields(payload)


def test_maintenance_is_blue_without_impact_field():
    payload = build_discord_payload(
        _incident_event(status="scheduled", impact="maintenance",
                        scheduled_for="2026-06-01T10:00:00Z",
                        scheduled_until="2026-06-01T12:00:00Z")
    )
    embed = payload["embeds"][0]
    assert embed["title"].startswith("[メンテナンス/メンテナンス予定]")
    assert embed["color"] == MAINTENANCE_COLOR
    fields = _fields(payload)
    assert "影響度" not in fields  # メンテナンスでは影響度フィールドを出さない
    assert fields["予定開始"].endswith("JST")


def test_component_update():
    payload = build_discord_payload(_component_event("operational", "major_outage"))
    embed = payload["embeds"][0]
    assert embed["title"] == "[コンポーネント変更] API"
    assert embed["description"] == "**正常稼働** → **重大障害**"
    assert embed["color"] == IMPACT_COLOR["major"]


def test_component_back_to_operational_is_green():
    payload = build_discord_payload(_component_event("major_outage", "operational"))
    assert payload["embeds"][0]["color"] == RESOLVED_COLOR


def test_min_impact_filters_minor():
    assert build_discord_payload(_incident_event(impact="minor"), min_impact="major") is None
    # major は通過する
    assert build_discord_payload(_incident_event(impact="major"), min_impact="major") is not None


def test_forward_components_false_drops_component_update():
    event = _component_event("operational", "major_outage")
    assert build_discord_payload(event, forward_components=False) is None


def test_critical_role_mention():
    payload = build_discord_payload(
        _incident_event(impact="critical"), critical_role_id="123456789012345678"
    )
    assert payload["content"] == "<@&123456789012345678>"
    assert payload["allowed_mentions"] == {"parse": [], "roles": ["123456789012345678"]}


def test_critical_mention_skipped_for_maintenance():
    payload = build_discord_payload(
        _incident_event(status="scheduled", impact="critical",
                        scheduled_for="2026-06-01T10:00:00Z"),
        critical_role_id="123456789012345678",
    )
    # メンテナンス扱いではメンションしない
    assert payload["content"] == ""
