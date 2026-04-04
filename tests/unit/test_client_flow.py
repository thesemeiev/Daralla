import pytest

from bot.client_flow import ALLOWED_CLIENT_FLOW_VALUES, normalize_client_flow_for_storage


def test_allowed_set():
    assert "xtls-rprx-vision" in ALLOWED_CLIENT_FLOW_VALUES
    assert "xtls-rprx-vision-udp443" in ALLOWED_CLIENT_FLOW_VALUES
    assert len(ALLOWED_CLIENT_FLOW_VALUES) == 2


@pytest.mark.parametrize(
    "raw,expected_stored",
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("xtls-rprx-vision", "xtls-rprx-vision"),
        ("xtls-rprx-vision-udp443", "xtls-rprx-vision-udp443"),
    ],
)
def test_normalize_ok(raw, expected_stored):
    stored, err = normalize_client_flow_for_storage(raw)
    assert err is None
    assert stored == expected_stored


def test_normalize_rejects_unknown():
    stored, err = normalize_client_flow_for_storage("xtls-rprx-visionx")
    assert stored is None
    assert err is not None


def test_normalize_rejects_non_string():
    stored, err = normalize_client_flow_for_storage(123)
    assert stored is None
    assert "string" in (err or "").lower()
