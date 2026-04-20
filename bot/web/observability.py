"""Request correlation and lightweight in-process metrics."""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections import Counter
from typing import Dict

from quart import g, request


REQUEST_ID_HEADER = "X-Request-ID"
_metrics_lock = threading.Lock()
_metrics_counter: Counter[str] = Counter()


def inc_metric(name: str, **labels: str) -> None:
    key = name
    if labels:
        labels_str = ",".join(f"{k}={labels[k]}" for k in sorted(labels.keys()))
        key = f"{name}|{labels_str}"
    with _metrics_lock:
        _metrics_counter[key] += 1


def get_metrics_snapshot() -> Dict[str, int]:
    with _metrics_lock:
        return dict(_metrics_counter)


def _request_id_from_headers() -> str:
    incoming = request.headers.get(REQUEST_ID_HEADER)
    if incoming:
        return incoming.strip()
    return uuid.uuid4().hex


def install_observability_hooks(app, logger) -> None:
    @app.before_request
    async def _before_request() -> None:
        g.request_id = _request_id_from_headers()
        g.request_started = time.perf_counter()
        inc_metric("http_requests_total", method=request.method, path=request.path)

    @app.after_request
    async def _after_request(response):
        request_id = getattr(g, "request_id", "")
        started = getattr(g, "request_started", None)
        elapsed_ms = 0.0
        if started:
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        status = response.status_code
        inc_metric("http_responses_total", method=request.method, path=request.path, status=str(status))
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "method": request.method,
                    "path": request.path,
                    "status": status,
                    "elapsed_ms": elapsed_ms,
                    "request_id": request_id,
                },
                ensure_ascii=False,
            )
        )
        return response
