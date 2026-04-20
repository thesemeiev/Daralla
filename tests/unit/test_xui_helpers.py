from bot.services.xui_helpers import (
    client_to_api_dict,
    panel_client_settings_dict,
    panel_snapshot_matches_desired,
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


def test_panel_snapshot_matches_desired_true_on_equal_snapshot():
    snapshot = {"on_panel": True, "expiry_sec": 1000, "limit_ip": 3, "flow": "xtls-rprx-vision"}
    assert panel_snapshot_matches_desired(snapshot, 1000, 3, "xtls-rprx-vision") is True


def test_panel_snapshot_matches_desired_false_when_not_on_panel():
    snapshot = {"on_panel": False}
    assert panel_snapshot_matches_desired(snapshot, 1000, 3, "") is False
