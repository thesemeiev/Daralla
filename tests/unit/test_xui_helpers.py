from daralla_backend.services.xui_helpers import (
    client_to_api_dict,
    clients_from_inbound_row,
    panel_client_settings_dict,
    panel_snapshot_matches_desired,
    parse_inbound_settings,
    v3_client_wire_payload,
)


def test_client_to_api_dict_maps_snake_case_fields():
    data = {
        "expiry_time": 111,
        "limit_ip": 2,
        "sub_id": "sub",
        "tg_id": "tg",
        "total_gb": 100,
    }
    out = client_to_api_dict(data)
    assert out["expiryTime"] == 111
    assert out["limitIp"] == 2
    assert out["subId"] == "sub"
    assert out["tgId"] == "tg"
    assert out["totalGB"] == 100


def test_panel_client_settings_dict_sets_flow_override():
    client = {"email": "u_1"}
    out = panel_client_settings_dict(client, flow_override="xtls-rprx-vision")
    assert out["flow"] == "xtls-rprx-vision"


def test_panel_client_settings_dict_drops_flow_for_non_vless():
    client = {"email": "u_1", "protocol": "hysteria2", "flow": "xtls-rprx-vision"}
    out = panel_client_settings_dict(client, flow_override="xtls-rprx-vision")
    assert "flow" not in out


def test_parse_inbound_settings_accepts_dict_or_json_string():
    assert parse_inbound_settings({"clients": [{"email": "a"}]}) == {"clients": [{"email": "a"}]}
    assert parse_inbound_settings('{"clients":[]}') == {"clients": []}
    assert parse_inbound_settings("") == {}


def test_clients_from_inbound_row_merges_settings_and_client_stats():
    inbound = {
        "settings": {"clients": [{"email": "a", "expiryTime": 0}]},
        "clientStats": [
            {"email": "a", "expiryTime": 0},
            {"email": "b", "expiryTime": 0},
        ],
    }
    emails = {c["email"] for c in clients_from_inbound_row(inbound)}
    assert emails == {"a", "b"}


def test_clients_from_inbound_row_v3_dict_settings_with_client_stats_only():
    inbound = {
        "settings": {},
        "clientStats": [{"email": "usr_x", "expiryTime": 9999999999999, "enable": True}],
    }
    rows = clients_from_inbound_row(inbound)
    assert len(rows) == 1
    assert rows[0]["email"] == "usr_x"


def test_v3_client_wire_payload_maps_uuid_to_id():
    rec = {
        "id": 99,
        "uuid": "550e8400-e29b-41d4-a716-446655440000",
        "email": "u@test",
        "tgId": "123",
    }
    out = v3_client_wire_payload(rec)
    assert out["id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert out["tgId"] == 123
    assert out["security"] == "auto"


def test_panel_snapshot_matches_desired_true_on_equal_snapshot():
    snapshot = {"on_panel": True, "expiry_sec": 1000, "limit_ip": 3, "flow": "xtls-rprx-vision"}
    assert panel_snapshot_matches_desired(snapshot, 1000, 3, "xtls-rprx-vision") is True


def test_panel_snapshot_matches_desired_false_when_not_on_panel():
    snapshot = {"on_panel": False}
    assert panel_snapshot_matches_desired(snapshot, 1000, 3, "") is False
