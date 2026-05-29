from daralla_backend.services.clash_subscription_service import (
    build_clash_subscription_yaml,
    is_clash_subscription_client,
    uri_to_clash_proxy,
)


def test_is_clash_subscription_client_detects_flclash_user_agent():
    assert is_clash_subscription_client("FlClash/0.8.87", "")
    assert is_clash_subscription_client("", "mihomo/1.18.0")
    assert not is_clash_subscription_client("V2RayTun/1.0", "")


def test_is_clash_subscription_client_honors_query_format():
    assert is_clash_subscription_client("", "", query={"format": "clash"})
    assert is_clash_subscription_client("", "", query={"clash": "1"})
    assert not is_clash_subscription_client("", "", query={"format": "v2ray"})


def test_vless_reality_uri_to_clash_proxy():
    uri = (
        "vless://11111111-2222-3333-4444-555555555555@edge.example.net:443"
        "?encryption=none&flow=xtls-rprx-vision&security=reality"
        "&sni=www.nvidia.com&fp=firefox&pbk=PublicKeyExample&sid=76f3e39bb4a74296&type=tcp"
        "#Germany-1"
    )
    proxy = uri_to_clash_proxy(uri)
    assert proxy is not None
    assert proxy["type"] == "vless"
    assert proxy["server"] == "edge.example.net"
    assert proxy["port"] == 443
    assert proxy["uuid"] == "11111111-2222-3333-4444-555555555555"
    assert proxy["flow"] == "xtls-rprx-vision"
    assert proxy["servername"] == "www.nvidia.com"
    assert proxy["client-fingerprint"] == "firefox"
    assert proxy["reality-opts"]["public-key"] == "PublicKeyExample"
    assert proxy["reality-opts"]["short-id"] == "76f3e39bb4a74296"
    assert proxy["name"] == "Germany-1"


def test_build_clash_subscription_yaml_from_links():
    links = [
        "vless://11111111-2222-3333-4444-555555555555@edge.example.net:443"
        "?security=reality&sni=www.nvidia.com&pbk=key&sid=abc&type=tcp#Node-A",
        "trojan://secret@tr.example:443?sni=tr.example#Node-B",
    ]
    yaml_text = build_clash_subscription_yaml(links, group_name="Daralla VPN")
    assert "type: vless" in yaml_text
    assert "type: trojan" in yaml_text
    assert "Daralla VPN" in yaml_text
    assert "name: AUTO" in yaml_text
    assert "MATCH,Daralla VPN" in yaml_text


def test_build_clash_subscription_yaml_is_plaintext_not_base64():
    links = [
        "vless://uuid@host:443?encryption=none&security=tls&sni=host#Test",
    ]
    yaml_text = build_clash_subscription_yaml(links, group_name="Test VPN")
    assert yaml_text.startswith("# Clash Meta")
    assert "proxies:" in yaml_text
    assert "vless://" not in yaml_text
