"""Unit tests for managed inbound scope (server_inbound_scope)."""
import json

import pytest

from daralla_backend.server_inbound_scope import (
    inbound_in_scope,
    normalize_managed_inbound_ids_for_storage,
    parse_managed_inbound_ids,
    primary_managed_inbound_id,
    serialize_managed_inbound_ids,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        ("", None),
        ("1", {1}),
        ("1, 3", {1, 3}),
        ("[2, 1]", {1, 2}),
        ([4, 5], {4, 5}),
    ],
)
def test_parse_managed_inbound_ids(raw, expected):
    assert parse_managed_inbound_ids(raw) == expected


def test_parse_managed_inbound_ids_invalid_json_array():
    assert parse_managed_inbound_ids("[bad") is None


def test_normalize_managed_inbound_ids_for_storage():
    stored, err = normalize_managed_inbound_ids_for_storage("1, 3")
    assert err is None
    assert stored == json.dumps([1, 3])

    stored_empty, err_empty = normalize_managed_inbound_ids_for_storage("")
    assert err_empty is None
    assert stored_empty is None

    _, err_bad = normalize_managed_inbound_ids_for_storage("abc")
    assert err_bad is not None


def test_inbound_in_scope():
    assert inbound_in_scope(1, None) is True
    assert inbound_in_scope(2, {1, 3}) is False
    assert inbound_in_scope(3, {1, 3}) is True


def test_primary_managed_inbound_id():
    assert primary_managed_inbound_id(None) is None
    assert primary_managed_inbound_id({3, 1}) == 1


def test_serialize_managed_inbound_ids():
    assert serialize_managed_inbound_ids([3, 1]) == "[1, 3]"
