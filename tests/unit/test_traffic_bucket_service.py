import pytest

from daralla_backend.services import traffic_bucket_service as tbs


@pytest.mark.asyncio
async def test_delivery_policy_keeps_exhausted_servers_in_subscription(monkeypatch):
    """Исчерпанный bucket: нода остаётся в /sub; суффикс used/limit + метка [лимит]."""
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    svc = tbs.TrafficBucketService()

    async def _sub(_sid):
        return {"id": 1}

    async def _ensure(_sid):
        return None

    async def _mapping(_sid):
        return {
            "de-1": {"id": 10, "is_unlimited": 0, "limit_bytes": 100},
            "fr-1": {"id": 11, "is_unlimited": 1, "limit_bytes": 0},
        }

    async def _states(_sid):
        return {
            10: {
                "is_exhausted": True,
                "is_unlimited": False,
                "used_bytes": 100,
                "remaining_bytes": 0,
                "limit_bytes": 100,
            },
            11: {
                "is_exhausted": False,
                "is_unlimited": True,
                "used_bytes": 0,
                "remaining_bytes": 0,
                "limit_bytes": 0,
            },
        }

    monkeypatch.setattr(tbs, "get_subscription_by_id_only", _sub)
    monkeypatch.setattr(svc, "ensure_default_mapping", _ensure)
    monkeypatch.setattr(tbs, "get_buckets_for_subscription_servers", _mapping)
    monkeypatch.setattr(svc, "compute_bucket_states", _states)

    policy = await svc.get_subscription_delivery_policy(1)
    assert policy["enabled"] is True
    assert "de-1" in policy["allowed_servers"]
    assert "fr-1" in policy["allowed_servers"]
    assert policy["name_suffix_by_server"]["fr-1"] == "[Unlimited]"
    assert policy["name_suffix_by_server"]["de-1"] == "[100B/100B] [лимит]"


@pytest.mark.asyncio
async def test_sync_usage_for_subscription_accumulates_delta(monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    svc = tbs.TrafficBucketService()

    class _Xui:
        async def get_client_traffic(self, _email):
            return {"upload": 200, "download": 300}

    class _Manager:
        def find_server_by_name(self, _name):
            return _Xui(), "srv-1"

    calls = {"delta": 0, "snapshots": 0}

    async def _ensure(_sid):
        return None

    async def _servers(_sid):
        return [{"server_name": "srv-1", "client_email": "u_1"}]

    async def _map(_sid):
        return {"srv-1": {"id": 5}}

    async def _snap(_sid, _srv, _email):
        return {"last_up": 120, "last_down": 180}

    async def _add_delta(_bid, delta):
        calls["delta"] += delta

    async def _upsert(*_args, **_kwargs):
        calls["snapshots"] += 1

    async def _enqueue(_sid):
        return 2

    monkeypatch.setattr(svc, "ensure_default_mapping", _ensure)
    monkeypatch.setattr(tbs, "get_subscription_servers", _servers)
    monkeypatch.setattr(tbs, "get_buckets_for_subscription_servers", _map)
    monkeypatch.setattr(tbs, "get_subscription_traffic_snapshot", _snap)
    monkeypatch.setattr(tbs, "add_bucket_usage_delta", _add_delta)
    monkeypatch.setattr(tbs, "upsert_subscription_traffic_snapshot", _upsert)
    monkeypatch.setattr(svc, "enqueue_enforcement_if_needed", _enqueue)

    summary = await svc.sync_usage_for_subscription(1, server_manager=_Manager())
    assert summary["delta_bytes"] == 200
    assert calls["delta"] == 200
    assert calls["snapshots"] == 1
    assert summary["enforcement_jobs"] == 2


@pytest.mark.asyncio
async def test_get_servers_with_exhausted_bucket(monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    svc = tbs.TrafficBucketService()

    async def _ensure(_sid):
        return None

    async def _mapping(_sid):
        return {
            "de-1": {"id": 10, "is_unlimited": 0, "limit_bytes": 100},
            "fr-1": {"id": 11, "is_unlimited": 1, "limit_bytes": 0},
        }

    async def _states(_sid):
        return {
            10: {"is_exhausted": True, "is_unlimited": False},
            11: {"is_exhausted": False, "is_unlimited": True},
        }

    monkeypatch.setattr(svc, "ensure_default_mapping", _ensure)
    monkeypatch.setattr(tbs, "get_buckets_for_subscription_servers", _mapping)
    monkeypatch.setattr(svc, "compute_bucket_states", _states)

    exhausted = await svc.get_servers_with_exhausted_bucket(1)
    assert exhausted == {"de-1"}
