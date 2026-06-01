from daralla_backend.services.clash_subscription_service import (
    build_clash_subscription_from_panels,
    is_clash_subscription_client,
    is_valid_panel_clash_body,
    merge_panel_clash_proxies,
    parse_panel_clash_yaml,
    render_clash_subscription_yaml,
)


def test_is_clash_subscription_client_detects_flclash_user_agent():
    assert is_clash_subscription_client("FlClash/0.8.87", "")
    assert is_clash_subscription_client("FiClash/1.0", "")
    assert is_clash_subscription_client("", "mihomo/1.18.0")
    assert not is_clash_subscription_client("V2RayTun/1.0", "")


def test_is_clash_subscription_client_honors_query_format():
    assert is_clash_subscription_client("", "", query={"format": "clash"})
    assert is_clash_subscription_client("", "", query={"clash": "1"})
    assert not is_clash_subscription_client("", "", query={"format": "v2ray"})


def test_is_valid_panel_clash_body_rejects_error():
    assert not is_valid_panel_clash_body("Error!")
    assert not is_valid_panel_clash_body("")
    assert is_valid_panel_clash_body("proxies:\n  - name: n1\n    type: vless\n    server: h\n")


def test_parse_panel_clash_yaml_extracts_proxies_only():
    text = """
proxy-groups:
  - name: g
    type: select
    proxies: []
proxies:
  - name: Finland
    type: vless
    server: 1.2.3.4
    port: 443
    uuid: abc
    network: xhttp
    xhttp-opts:
      path: /
      mode: packet-up
"""
    proxies = parse_panel_clash_yaml(text)
    assert len(proxies) == 1
    assert proxies[0]["name"] == "Finland"
    assert proxies[0]["network"] == "xhttp"
    assert proxies[0]["xhttp-opts"]["mode"] == "packet-up"


def test_parse_panel_clash_yaml_copies_servername_to_sni():
    text = """
proxies:
  - name: TestTrojan
    type: trojan
    server: 1.2.3.4
    port: 443
    password: p
    servername: example.com
"""
    proxies = parse_panel_clash_yaml(text)
    assert len(proxies) == 1
    assert proxies[0]["sni"] == "example.com"
    assert proxies[0]["servername"] == "example.com"


def test_relabel_panel_clash_proxies_uses_display_name():
    from daralla_backend.services.clash_subscription_service import _relabel_panel_clash_proxies

    proxies = [
        {"name": "Finland-1.1-6735703554_abc123,10H⏳", "type": "vless"},
    ]
    renamed = _relabel_panel_clash_proxies(proxies, "Finland")
    assert len(renamed) == 1
    assert renamed[0]["name"] == "Finland"


def test_merge_panel_clash_proxies_dedupes_names():
    merged = merge_panel_clash_proxies(
        [
            [{"name": "Node", "type": "vless"}],
            [{"name": "Node", "type": "trojan"}],
        ]
    )
    names = [p["name"] for p in merged]
    assert names == ["Node", "Node-2"]


def test_simplify_proxy_names_for_long_panel_ids():
    merged = merge_panel_clash_proxies(
        [
            [{"name": "Finland-1.1-6735703554_abcdef12-3456-7890-1234-56789abcdef0,10H⏳"}],
            [{"name": "Finland-2.1-12345678_abcdef12"}],
        ]
    )
    names = [p["name"] for p in merged]
    assert names == ["Finland", "Finland-2"]


def test_build_clash_subscription_from_panels_merges_two_panels():
    panel_a = """
proxies:
  - name: Germany
    type: hysteria2
    server: 1.1.1.1
    port: 443
    password: x
"""
    panel_b = """
proxies:
  - name: Finland
    type: vless
    server: 2.2.2.2
    port: 443
    uuid: u
    network: xhttp
    xhttp-opts:
      path: /
      mode: packet-up
      x-padding-bytes: 100-1000
"""
    yaml_text = build_clash_subscription_from_panels(
        [panel_a, panel_b],
        group_name="Daralla VPN",
    )
    assert "type: hysteria2" in yaml_text
    assert "network: xhttp" in yaml_text
    assert "x-padding-bytes: 100-1000" in yaml_text
    assert "profile-title: Daralla VPN" in yaml_text
    assert "name: PROXY" in yaml_text
    assert "MATCH,PROXY" in yaml_text


def test_render_clash_subscription_yaml_empty_proxies():
    yaml_text = render_clash_subscription_yaml([], group_name="Test VPN")
    assert yaml_text.startswith("# Clash Meta")
    assert "proxies:" in yaml_text
    assert "name: PROXY" in yaml_text
    assert "MATCH,PROXY" in yaml_text

