from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.compliance.data_governance import DataGovernance, DataType
from src.db.database import async_session_factory

COMPLIANCE_ENDPOINTS = {
    "/api/v1/compliance/export": "data_portability",
    "/api/v1/compliance/deletion-request": "deletion_request",
    "/api/v1/compliance/deletion-status": "deletion_status",
    "/api/v1/compliance/consent": "consent_access",
    "/api/v1/compliance/opt-out": "opt_out_access",
}


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        matched = self._match_endpoint(request.url.path)
        if matched and response.status_code < 400:
            await self._log_access(request, matched)
        return response

    def _match_endpoint(self, path: str) -> str | None:
        for prefix, action in COMPLIANCE_ENDPOINTS.items():
            if path.startswith(prefix):
                return action
        return None

    async def _log_access(self, request: Request, action: str) -> None:
        try:
            gov = DataGovernance()
            api_key_id = request.state.api_key_id if hasattr(request.state, "api_key_id") else "anonymous"
            async with async_session_factory() as session:
                await gov.log_retention_action(
                    session=session,
                    data_type=DataType.LOG,
                    record_id=api_key_id,
                    action=action,
                    reason=f"PII access logged for compliance: {request.method} {request.url.path}",
                    triggered_by=api_key_id,
                )
        except Exception:
            pass


class PublicOptOutRateLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = {}

    async def check(self, ip: str, limit: int = 10, window: int = 3600) -> bool:
        now = time.time()
        cutoff = now - window
        timestamps = [t for t in self._attempts.get(ip, []) if t > cutoff]
        if len(timestamps) >= limit:
            return False
        timestamps.append(now)
        self._attempts[ip] = timestamps
        return True


_opt_out_limiter = PublicOptOutRateLimiter()


async def check_opt_out_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    allowed = await _opt_out_limiter.check(client_ip)
    if not allowed:
        from fastapi import HTTPException
        from starlette.status import HTTP_429_TOO_MANY_REQUESTS
        raise HTTPException(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many opt-out registration attempts. Try again later.",
        )
