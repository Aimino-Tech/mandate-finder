from __future__ import annotations

import threading
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, generate_latest, start_http_server

_jobs_total = Counter("worker_jobs_total", "Total jobs processed", ["worker", "status"])
_jobs_duration = Histogram("worker_job_duration_seconds", "Job duration in seconds", ["worker"])
_workers_up = Gauge("worker_up", "Worker availability (1=up, 0=down)", ["worker"])

_health_status: dict[str, Any] = {}


def start_metrics_server(port: int = 9090) -> None:
    threading.Thread(target=start_http_server, args=(port,), daemon=True).start()


def record_job(worker: str, duration: float, status: str = "ok") -> None:
    _jobs_total.labels(worker=worker, status=status).inc()
    _jobs_duration.labels(worker=worker).observe(duration)


def set_health(worker: str, status: dict[str, Any]) -> None:
    _health_status[worker] = status
    is_up = 1 if status.get("status") == "ok" else 0
    _workers_up.labels(worker=worker).set(is_up)


def get_health() -> dict[str, Any]:
    if not _health_status:
        return {"status": "ok", "workers": {}}
    all_ok = all(s.get("status") == "ok" for s in _health_status.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "workers": _health_status,
    }


def get_metrics() -> bytes:
    return generate_latest()
