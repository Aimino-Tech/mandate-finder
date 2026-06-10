from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT, HTTP_503_SERVICE_UNAVAILABLE

from src.config import settings
from src.db.database import get_session
from src.db.models import CRMConnection, CRMSyncLog
from src.middleware.rate_limit import authenticated_api_key
from src.services.crm_service import CRMType, auto_sync, encrypt_token, sync_to_crm

router = APIRouter(prefix="/crm", tags=["CRM"])


class CRMConfigItem(BaseModel):
    crm_type: str
    available: bool
    hint: str


class ConReq(BaseModel):
    crm_type: CRMType
    authorization_code: str | None = None
    api_token: str | None = None
    label: str = ""


class ConnItem(BaseModel):
    id: str
    crm_type: str
    label: str
    auto_sync_enabled: bool
    is_active: bool
    synced_lead_count: int
    created_at: datetime


class ConnDetail(ConnItem):
    field_mapping: dict[str, str]


class FMUpdate(BaseModel):
    field_mapping: dict[str, str]


class ASToggle(BaseModel):
    enabled: bool


class SyncReq(BaseModel):
    lead_ids: list[str]
    connection_id: str | None = None


class SyncResItem(BaseModel):
    lead_id: str
    success: bool
    contact_id: str | None = None
    deal_id: str | None = None
    error: str | None = None


class SyncRes(BaseModel):
    results: list[SyncResItem]


class OAuthURL(BaseModel):
    url: str


class LogEntry(BaseModel):
    id: str
    connection_id: str
    lead_id: str
    success: bool
    contact_id: str | None = None
    deal_id: str | None = None
    error_message: str | None = None
    attempt: int
    created_at: datetime


class HistRes(BaseModel):
    entries: list[LogEntry]
    total: int


async def _get_conn(cid: str, oid: str, s: AsyncSession) -> CRMConnection:
    c = (await s.execute(select(CRMConnection).where(CRMConnection.id == cid, CRMConnection.organization_id == oid))).scalar_one_or_none()
    if c is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="CRM connection not found")
    return c


def _to_item(c: CRMConnection) -> dict:
    return ConnItem(id=c.id, crm_type=c.crm_type, label=c.label, auto_sync_enabled=c.auto_sync_enabled,
                    is_active=c.is_active, synced_lead_count=len(c.synced_lead_ids or []),
                    created_at=c.created_at).model_dump()


@router.get("/config", response_model=list[CRMConfigItem])
async def config():
    return [CRMConfigItem(crm_type="hubspot", available=bool(settings.hubspot_client_id), hint="OAuth2"),
            CRMConfigItem(crm_type="pipedrive", available=True, hint="API token"),
            CRMConfigItem(crm_type="salesforce", available=bool(settings.salesforce_client_id), hint="OAuth2")]


@router.get("/connections", response_model=list[ConnItem])
async def list_all(_ak: Any = Depends(authenticated_api_key), s: AsyncSession = Depends(get_session)):
    return [_to_item(c) for c in (await s.execute(select(CRMConnection).order_by(CRMConnection.created_at.desc()))).scalars().all()]


@router.get("/connections/{cid}", response_model=ConnDetail)
async def get_one(cid: str, _ak: Any = Depends(authenticated_api_key), s: AsyncSession = Depends(get_session)):
    c = await _get_conn(cid, "default", s)
    return ConnDetail(id=c.id, crm_type=c.crm_type, label=c.label,
                      field_mapping={k: v for k, v in (c.field_mapping or {}).items() if isinstance(v, str)},
                      auto_sync_enabled=c.auto_sync_enabled, is_active=c.is_active,
                      synced_lead_count=len(c.synced_lead_ids or []), created_at=c.created_at)


@router.post("/connect", status_code=201, response_model=ConnItem)
async def connect(body: ConReq, _ak: Any = Depends(authenticated_api_key), s: AsyncSession = Depends(get_session)):
    if (await s.execute(select(CRMConnection).where(CRMConnection.organization_id == "default",
                                                     CRMConnection.crm_type == body.crm_type.value,
                                                     CRMConnection.is_active.is_(True)))).scalar_one_or_none():
        raise HTTPException(HTTP_409_CONFLICT, detail=f"Active {body.crm_type.value} connection exists")
    at = rt = iu = None
    if body.crm_type == CRMType.PIPEDRIVE:
        if not body.api_token:
            raise HTTPException(HTTP_400_BAD_REQUEST, detail="API token required")
        at = body.api_token
    elif body.crm_type in (CRMType.HUBSPOT, CRMType.SALESFORCE):
        if not body.authorization_code:
            raise HTTPException(HTTP_400_BAD_REQUEST, detail="Authorization code required")
        d = await _exchange(body.crm_type.value, body.authorization_code)
        at, rt = d["access_token"], d.get("refresh_token")
        if body.crm_type == CRMType.SALESFORCE:
            iu = d.get("instance_url")
    c = CRMConnection(organization_id="default", crm_type=body.crm_type.value,
                      label=body.label or body.crm_type.value.title(),
                      encrypted_access_token=encrypt_token(at or ""),
                      encrypted_refresh_token=encrypt_token(rt or "") if rt else None, instance_url=iu)
    s.add(c)
    await s.commit()
    await s.refresh(c)
    return _to_item(c)


@router.delete("/connections/{cid}", status_code=204)
async def disconnect(cid: str, _ak: Any = Depends(authenticated_api_key), s: AsyncSession = Depends(get_session)):
    c = await _get_conn(cid, "default", s)
    c.is_active = False
    await s.commit()


class ReconnectReq(BaseModel):
    authorization_code: str


@router.post("/connections/{cid}/reconnect")
async def reconnect(cid: str, body: ReconnectReq, _ak: Any = Depends(authenticated_api_key), s: AsyncSession = Depends(get_session)):
    c = await _get_conn(cid, "default", s)
    if c.crm_type == CRMType.PIPEDRIVE.value:
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Pipedrive uses API tokens, not OAuth")
    d = await _exchange(c.crm_type, body.authorization_code)
    c.encrypted_access_token = encrypt_token(d["access_token"])
    if "refresh_token" in d:
        c.encrypted_refresh_token = encrypt_token(d["refresh_token"])
    if c.crm_type == CRMType.SALESFORCE.value and "instance_url" in d:
        c.instance_url = d["instance_url"]
    c.is_active = True
    await s.commit()
    return {"status": "ok", "crm_type": c.crm_type}


@router.put("/connections/{cid}/field-mapping")
async def update_fm(cid: str, body: FMUpdate, _ak: Any = Depends(authenticated_api_key), s: AsyncSession = Depends(get_session)):
    c = await _get_conn(cid, "default", s)
    c.field_mapping = dict(body.field_mapping)
    await s.commit()
    return {"status": "ok"}


@router.put("/connections/{cid}/auto-sync")
async def toggle_as(cid: str, body: ASToggle, _ak: Any = Depends(authenticated_api_key), s: AsyncSession = Depends(get_session)):
    c = await _get_conn(cid, "default", s)
    c.auto_sync_enabled = body.enabled
    await s.commit()
    return {"auto_sync_enabled": body.enabled}


@router.post("/sync", response_model=SyncRes)
async def sync_leads(body: SyncReq, _ak: Any = Depends(authenticated_api_key), s: AsyncSession = Depends(get_session)):
    stmt = select(CRMConnection).where(CRMConnection.organization_id == "default", CRMConnection.is_active.is_(True))
    if body.connection_id:
        stmt = stmt.where(CRMConnection.id == body.connection_id)
    conn = (await s.execute(stmt)).scalar_one_or_none()
    if conn is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="No active CRM connection")
    items = [SyncResItem(lead_id=lid, success=r.success, contact_id=r.contact_id,
                         deal_id=r.deal_id, error=r.error)
             for lid in body.lead_ids
             if (r := await sync_to_crm(s, conn, {"id": lid}, lid))]
    return SyncRes(results=items)


@router.post("/sync/retry", response_model=SyncRes)
async def retry_failed(_ak: Any = Depends(authenticated_api_key), s: AsyncSession = Depends(get_session)):
    items: list[SyncResItem] = []
    for c in (await s.execute(select(CRMConnection).where(CRMConnection.organization_id == "default",
                                                           CRMConnection.is_active.is_(True)))).scalars().all():
        for lid in (c.synced_lead_ids or []):
            r = await sync_to_crm(s, c, {"id": str(lid)}, str(lid))
            items.append(SyncResItem(lead_id=str(lid), success=r.success, contact_id=r.contact_id,
                                     deal_id=r.deal_id, error=r.error))
    return SyncRes(results=items)


@router.get("/sync-history")
async def history(cid: str | None = None, limit: int = 50,
                  _ak: Any = Depends(authenticated_api_key), s: AsyncSession = Depends(get_session)):
    base = select(CRMSyncLog).where(CRMSyncLog.organization_id == "default")
    cnt = select(func.count(CRMSyncLog.id)).where(CRMSyncLog.organization_id == "default")
    if cid:
        base = base.where(CRMSyncLog.connection_id == cid)
        cnt = cnt.where(CRMSyncLog.connection_id == cid)
    total = (await s.execute(cnt)).scalar() or 0
    rows = (await s.execute(base.order_by(CRMSyncLog.created_at.desc()).limit(limit))).scalars().all()
    return HistRes(entries=[LogEntry(id=e.id, connection_id=e.connection_id, lead_id=e.lead_id,
                                     success=e.success, contact_id=e.contact_id, deal_id=e.deal_id,
                                     error_message=e.error_message, attempt=e.attempt,
                                     created_at=e.created_at) for e in rows], total=total)


@router.post("/webhook/lead-matched")
async def wh_lead(payload: dict[str, object], s: AsyncSession = Depends(get_session)):
    lid = str(payload.get("id", ""))
    if not lid:
        raise HTTPException(400, detail="lead_id required")
    res = await auto_sync(s, str(payload.get("organization_id", "default")), payload, lid)
    return {"status": "ok", "processed": str(len(res)), "synced": str(sum(1 for r in res if r.success))}


@router.get("/hubspot/auth-url", response_model=OAuthURL)
async def hs_auth():
    if not settings.hubspot_client_id:
        raise HTTPException(HTTP_503_SERVICE_UNAVAILABLE, detail="HubSpot not configured")
    return OAuthURL(url=f"https://app.hubspot.com/oauth/authorize?client_id={settings.hubspot_client_id}"
                        f"&redirect_uri={settings.hubspot_redirect_uri}&scope=contacts%20crm.objects.deals%20oauth"
                        f"&state={secrets.token_urlsafe(32)}")


@router.get("/salesforce/auth-url", response_model=OAuthURL)
async def sf_auth():
    if not settings.salesforce_client_id:
        raise HTTPException(HTTP_503_SERVICE_UNAVAILABLE, detail="Salesforce not configured")
    return OAuthURL(url=f"https://login.salesforce.com/services/oauth2/authorize?response_type=code"
                        f"&client_id={settings.salesforce_client_id}&redirect_uri={settings.salesforce_redirect_uri}"
                        f"&state={secrets.token_urlsafe(32)}")


@router.get("/hubspot/callback")
async def hs_cb(code: str = Query(...), _s: str | None = Query(None)):
    return RedirectResponse(url=f"{settings.crm_frontend_url}/admin/crm?code={code}&provider=hubspot")


@router.get("/salesforce/callback")
async def sf_cb(code: str = Query(...), _s: str | None = Query(None)):
    return RedirectResponse(url=f"{settings.crm_frontend_url}/admin/crm?code={code}&provider=salesforce")


async def _exchange(provider: str, code: str) -> dict[str, Any]:
    cfg = {"hubspot": ("https://api.hubapi.com/oauth/v1/token", settings.hubspot_client_id,
                       settings.hubspot_client_secret, settings.hubspot_redirect_uri),
           "salesforce": ("https://login.salesforce.com/services/oauth2/token", settings.salesforce_client_id,
                          settings.salesforce_client_secret, settings.salesforce_redirect_uri)}
    url, cid, sec, redir = cfg[provider]
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(url, data={"grant_type": "authorization_code", "client_id": cid,
                                    "client_secret": sec, "redirect_uri": redir, "code": code})
        r.raise_for_status()
        return r.json()
