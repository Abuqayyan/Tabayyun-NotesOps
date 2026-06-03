"""Observability: per-request metrics, error/denial capture, and a request-id header.

A lightweight middleware records aggregate metrics per route (count, latency, errors,
permission denials) into Mongo `api_metrics`, captures 5xx into `api_errors`, and stamps
every response with X-Request-ID. All recording is best-effort and never affects the
response. Designed for the single-VPS / <50-user deployment; cardinality stays low because
metrics are keyed on the route TEMPLATE, not the concrete path.
"""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

from app.core.db_mongo import db
from app.core.utils import now_iso

log = logging.getLogger("opscore.observability")

_ERROR_CAP = 1000  # keep the most recent N api_errors


def _route_template(request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None) or request.url.path
    return path


async def record_request(method: str, route: str, status: int, duration_ms: float, request_id: str) -> None:
    try:
        is_error = status >= 500
        is_denial = status == 403
        await db.api_metrics.update_one(
            {"id": f"{method} {route}"},
            {"$inc": {"count": 1, "total_ms": duration_ms,
                      "errors": 1 if is_error else 0, "denials": 1 if is_denial else 0},
             "$max": {"max_ms": duration_ms},
             "$set": {"method": method, "route": route, "last_at": now_iso()},
             "$setOnInsert": {"id": f"{method} {route}", "created_at": now_iso()}},
            upsert=True,
        )
        if is_error:
            await db.api_errors.insert_one({
                "id": str(uuid.uuid4()), "method": method, "route": route, "status": status,
                "request_id": request_id, "created_at": now_iso(),
            })
    except Exception as exc:  # noqa: BLE001 - observability must never break a request
        log.debug(f"record_request failed: {exc}")


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
            path = request.url.path
            if path.startswith("/api"):
                await record_request(request.method, _route_template(request), status, duration_ms, request_id)
        return response


async def metrics_summary(limit: int = 200) -> dict:
    rows = await db.api_metrics.find({}, {"_id": 0}).to_list(limit)
    for r in rows:
        r["avg_ms"] = round(r.get("total_ms", 0) / r["count"], 2) if r.get("count") else 0
    total_requests = sum(r.get("count", 0) for r in rows)
    total_errors = sum(r.get("errors", 0) for r in rows)
    total_denials = sum(r.get("denials", 0) for r in rows)
    slowest = sorted(rows, key=lambda r: -r.get("max_ms", 0))[:10]
    busiest = sorted(rows, key=lambda r: -r.get("count", 0))[:10]
    return {
        "total_requests": total_requests, "total_errors": total_errors, "total_denials": total_denials,
        "error_rate": round(total_errors * 100 / total_requests, 2) if total_requests else 0,
        "slowest_routes": [{"route": r["id"], "max_ms": r.get("max_ms"), "avg_ms": r["avg_ms"], "count": r["count"]} for r in slowest],
        "busiest_routes": [{"route": r["id"], "count": r["count"], "avg_ms": r["avg_ms"]} for r in busiest],
    }
