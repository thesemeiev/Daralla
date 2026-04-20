from daralla_backend.web.routes.api_user_helpers import cryptocloud_extract_address, normalize_map_lat_lng


def test_cryptocloud_extract_address_from_top_level():
    payload = {"address": "  0xabc123  "}
    assert cryptocloud_extract_address(payload) == "0xabc123"


def test_cryptocloud_extract_address_from_nested():
    payload = {"wallet": {"payment_address": "TON-ADDR"}}
    assert cryptocloud_extract_address(payload) == "TON-ADDR"


def test_cryptocloud_extract_address_empty_returns_empty_string():
    assert cryptocloud_extract_address({"address": ""}) == ""


def test_normalize_map_lat_lng_valid_coordinates():
    lat, lng = normalize_map_lat_lng("55.75", "37.62")
    assert lat == 55.75
    assert lng == 37.62


def test_normalize_map_lat_lng_invalid_out_of_range():
    lat, lng = normalize_map_lat_lng(1000, 3000)
    assert lat is None
    assert lng is None
