from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import CRMConnection, CRMSyncLog

logger = logging.getLogger(__name__)

RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 5


class CRMType(StrEnum):
    HUBSPOT = "hubspot"
    PIPEDRIVE = "pipedrive"
    SALESFORCE = "salesforce"


class SyncResult:
    def __init__(self, success: bool, contact_id: str | None = None,
                 deal_id: str | None = None, error: str | None = None) -> None:
        self.success = success
        self.contact_id = contact_id
        self.deal_id = deal_id
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {"success": self.success, "contact_id": self.contact_id,
                "deal_id": self.deal_id, "error": self.error}


_KEY_CACHE: bytes | None = None


def _derive_key() -> bytes:
    global _KEY_CACHE
    if _KEY_CACHE is not None:
        return _KEY_CACHE
    raw = settings.crm_encryption_key.strip() or settings.app_name
    _KEY_CACHE = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
    return _KEY_CACHE


def _cipher() -> Fernet:
    return Fernet(_derive_key())


def encrypt_token(plaintext: str) -> str:
    if not plaintext:
        return ""
    try:
        return _cipher().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


def decrypt_token(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _cipher().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


class BaseCRMIntegration(ABC):
    def __init__(self, connection: dict[str, Any]) -> None:
        self.connection = connection
        self.field_mapping: dict[str, str] = connection.get("field_mapping", {}) or {}
        self.access_token = connection["encrypted_access_token"]
        self.refresh_token = connection.get("encrypted_refresh_token")

    @abstractmethod
    async def create_contact(self, lead_data: dict[str, Any]) -> SyncResult: ...
    @abstractmethod
    async def create_deal(self, lead_data: dict[str, Any]) -> SyncResult: ...
    @abstractmethod
    async def sync_status(self) -> dict[str, Any]: ...

    async def sync_lead(self, lead_data: dict[str, Any]) -> SyncResult:
        c = await self.create_contact(lead_data)
        if not c.success:
            return c
        d = await self.create_deal(lead_data)
        return SyncResult(success=d.success, contact_id=c.contact_id,
                          deal_id=d.deal_id, error=d.error)

    def _map_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self.field_mapping:
            return data
        ks = set(self.field_mapping.keys())
        m: dict[str, Any] = {}
        for k, v in self.field_mapping.items():
            if k in data:
                m[v] = data[k]
        for k, v in data.items():
            if k not in ks:
                m[k] = v
        return m


class HubSpotIntegration(BaseCRMIntegration):
    BASE_URL = "https://api.hubapi.com"

    async def _req(self, method: str, path: str, json: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.request(method, f"{self.BASE_URL}{path}",
                                headers={"Authorization": f"Bearer {self.access_token}",
                                         "Content-Type": "application/json"}, json=json)
            if r.status_code == 401 and self.refresh_token:
                raise TokenExpiredError("token expired")
            r.raise_for_status()
            return r.json() if r.content else {}

    async def create_contact(self, data: dict) -> SyncResult:
        try:
            m = self._map_fields(data)
            p: dict[str, str] = {}
            for src, dst in (("email", "email"), ("company", "company"),
                             ("first_name", "firstname"), ("last_name", "lastname"),
                             ("phone", "phone"), ("job_title", "jobtitle")):
                if src in m:
                    p[dst] = m[src]
            resp = await self._req("POST", "/crm/v3/objects/contacts", json={"properties": p})
            return SyncResult(success=True, contact_id=resp.get("id"))
        except Exception as e:
            return SyncResult(success=False, error=str(e))

    async def create_deal(self, data: dict) -> SyncResult:
        try:
            m = self._map_fields(data)
            p: dict[str, str] = {"dealname": m.get("company", "Lead"),
                                 "dealstage": m.get("deal_stage", "appointmentscheduled"),
                                 "amount": m.get("estimated_value", "0")}
            if "pipeline" in m:
                p["pipeline"] = m["pipeline"]
            d = await self._req("POST", "/crm/v3/objects/deals", json={"properties": p})
            return SyncResult(success=True, deal_id=d.get("id"))
        except Exception as e:
            return SyncResult(success=False, error=str(e))

    async def sync_status(self) -> dict:
        try:
            d = await self._req("GET", "/crm/v3/objects/contacts")
            return {"connected": True, "total_contacts": d.get("total", 0)}
        except Exception as e:
            return {"connected": False, "error": str(e)}


class PipedriveIntegration(BaseCRMIntegration):
    BASE_URL = "https://api.pipedrive.com/v1"

    async def _req(self, method: str, path: str, json: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.request(method, f"{self.BASE_URL}{path}",
                                headers={"Authorization": f"Bearer {self.access_token}",
                                         "Content-Type": "application/json"}, json=json)
            if r.status_code == 401 and self.refresh_token:
                raise TokenExpiredError("token expired")
            r.raise_for_status()
            raw: dict = r.json()
            res: dict = raw.get("data", raw)
            return res

    async def create_contact(self, data: dict) -> SyncResult:
        try:
            m = self._map_fields(data)
            p: dict[str, Any] = {"name": m.get("name", m.get("company", "Lead"))}
            for k in ("email", "phone", "job_title"):
                if k in m:
                    p[k] = m[k]
            d = await self._req("POST", "/persons", json=p)
            return SyncResult(success=True, contact_id=str(d.get("id", "")))
        except Exception as e:
            return SyncResult(success=False, error=str(e))

    async def create_deal(self, data: dict) -> SyncResult:
        try:
            m = self._map_fields(data)
            d: dict[str, Any] = {"title": m.get("company", "Lead"),
                                 "value": m.get("estimated_value", "0"),
                                 "currency": m.get("currency", "EUR")}
            if "deal_stage" in m:
                d["stage_id"] = m["deal_stage"]
            r = await self._req("POST", "/deals", json=d)
            return SyncResult(success=True, deal_id=str(r.get("id", "")))
        except Exception as e:
            return SyncResult(success=False, error=str(e))

    async def sync_status(self) -> dict:
        try:
            d = await self._req("GET", "/persons")
            return {"connected": True, "total_contacts": len(d) if isinstance(d, list) else 0}
        except Exception as e:
            return {"connected": False, "error": str(e)}


class SalesforceIntegration(BaseCRMIntegration):
    def _instance_url(self) -> str:
        u: str = self.connection.get("instance_url", "https://login.salesforce.com") or "https://login.salesforce.com"
        return u

    async def _req(self, method: str, path: str, json: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.request(method, f"{self._instance_url()}{path}",
                                headers={"Authorization": f"Bearer {self.access_token}",
                                         "Content-Type": "application/json"}, json=json)
            if r.status_code == 401 and self.refresh_token:
                raise TokenExpiredError("token expired")
            r.raise_for_status()
            return r.json()

    async def create_contact(self, data: dict) -> SyncResult:
        try:
            m = self._map_fields(data)
            c: dict[str, str] = {"LastName": m.get("last_name", m.get("company", "Lead"))}
            for s, d in [("email", "Email"), ("first_name", "FirstName"),
                         ("phone", "Phone"), ("job_title", "Title")]:
                if s in m:
                    c[d] = m[s]
            r = await self._req("POST", "/services/data/v60.0/sobjects/Contact", json=c)
            return SyncResult(success=True, contact_id=r.get("id", ""))
        except Exception as e:
            return SyncResult(success=False, error=str(e))

    async def create_deal(self, data: dict) -> SyncResult:
        try:
            m = self._map_fields(data)
            o: dict[str, str] = {"Name": m.get("company", "Lead"),
                                 "StageName": m.get("deal_stage", "Prospecting"),
                                 "Amount": m.get("estimated_value", "0"),
                                 "CloseDate": m.get("close_date", "2026-12-31")}
            r = await self._req("POST", "/services/data/v60.0/sobjects/Opportunity", json=o)
            return SyncResult(success=True, deal_id=r.get("id", ""))
        except Exception as e:
            return SyncResult(success=False, error=str(e))

    async def sync_status(self) -> dict:
        try:
            from urllib.parse import quote
            d = await self._req("GET", f"/services/data/v60.0/query?q={quote('SELECT COUNT() FROM Contact')}")
            recs = d.get("records", [])
            return {"connected": True, "total_contacts": recs[0].get("expr0", 0) if recs else 0}
        except Exception as e:
            return {"connected": False, "error": str(e)}


class TokenExpiredError(Exception):
    pass


CRM_CLASSES: dict[CRMType, type[BaseCRMIntegration]] = {
    CRMType.HUBSPOT: HubSpotIntegration,
    CRMType.PIPEDRIVE: PipedriveIntegration,
    CRMType.SALESFORCE: SalesforceIntegration,
}


async def sync_to_crm(db: AsyncSession, conn: CRMConnection, lead_data: dict[str, object], lead_id: str) -> SyncResult:
    ct = CRMType(conn.crm_type)
    cls = CRM_CLASSES.get(ct)
    if cls is None:
        return SyncResult(success=False, error=f"Unsupported CRM: {ct}")
    cd: dict[str, object] = {"encrypted_access_token": decrypt_token(conn.encrypted_access_token),
                             "encrypted_refresh_token": decrypt_token(conn.encrypted_refresh_token or ""),
                             "field_mapping": conn.field_mapping, "instance_url": conn.instance_url or ""}
    integration = cls(cd)
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            result = await integration.sync_lead(lead_data)
            await _log(db, conn, lead_id, result, attempt, lead_data)
            if result.success:
                _synced(db, conn, lead_id)
                return result
            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)
            else:
                return result
        except TokenExpiredError:
            if await _refresh(db, conn, ct):
                cd["encrypted_access_token"] = decrypt_token(conn.encrypted_access_token)
                cd["encrypted_refresh_token"] = decrypt_token(conn.encrypted_refresh_token or "")
                integration = cls(cd)
                continue
            r = SyncResult(success=False, error=f"Token refresh failed for {ct.value}")
            await _log(db, conn, lead_id, r, attempt, lead_data)
            return r
        except Exception as e:
            r = SyncResult(success=False, error=str(e))
            await _log(db, conn, lead_id, r, attempt, lead_data)
            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)
            else:
                return r
    r = SyncResult(success=False, error="Sync failed after retries")
    await _log(db, conn, lead_id, r, RETRY_ATTEMPTS, lead_data)
    return r


async def auto_sync(db: AsyncSession, org: str, data: dict[str, object], lid: str) -> list[SyncResult]:
    q = await db.execute(select(CRMConnection).where(CRMConnection.organization_id == org,
                                                      CRMConnection.is_active.is_(True),
                                                      CRMConnection.auto_sync_enabled.is_(True)))
    return [await sync_to_crm(db, c, data, lid) for c in q.scalars().all()]


async def _log(db: AsyncSession, conn: CRMConnection, lid: str, r: SyncResult, attempt: int, data: dict | None = None) -> None:
    db.add(CRMSyncLog(connection_id=conn.id, organization_id=conn.organization_id, lead_id=lid,
                      success=r.success, contact_id=r.contact_id, deal_id=r.deal_id,
                      error_message=r.error, attempt=attempt, lead_snapshot=data))
    await db.commit()


def _synced(_db: AsyncSession, conn: CRMConnection, lid: str) -> None:
    existing = list(conn.synced_lead_ids)
    if lid not in existing:
        existing.append(lid)
        conn.synced_lead_ids = existing


async def _refresh(db: AsyncSession, conn: CRMConnection, ct: CRMType) -> bool:
    if ct == CRMType.PIPEDRIVE:
        return False
    return await (_refresh_hubspot(db, conn) if ct == CRMType.HUBSPOT else _refresh_sf(db, conn))


async def _refresh_hubspot(db: AsyncSession, conn: CRMConnection) -> bool:
    raw = decrypt_token(conn.encrypted_refresh_token or "")
    if not raw:
        return False
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post("https://api.hubapi.com/oauth/v1/token", data={
                "grant_type": "refresh_token", "client_id": settings.hubspot_client_id,
                "client_secret": settings.hubspot_client_secret, "refresh_token": raw})
            r.raise_for_status()
            d = r.json()
            conn.encrypted_access_token = encrypt_token(d["access_token"])
            if "refresh_token" in d:
                conn.encrypted_refresh_token = encrypt_token(d["refresh_token"])
            await db.commit()
            return True
    except Exception as e:
        logger.error("HubSpot refresh failed: %s", e)
        return False


async def _refresh_sf(db: AsyncSession, conn: CRMConnection) -> bool:
    raw = decrypt_token(conn.encrypted_refresh_token or "")
    if not raw:
        return False
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post("https://login.salesforce.com/services/oauth2/token", data={
                "grant_type": "refresh_token", "client_id": settings.salesforce_client_id,
                "client_secret": settings.salesforce_client_secret, "refresh_token": raw})
            r.raise_for_status()
            d = r.json()
            conn.encrypted_access_token = encrypt_token(d["access_token"])
            if "instance_url" in d:
                conn.instance_url = d["instance_url"]
            await db.commit()
            return True
    except Exception as e:
        logger.error("Salesforce refresh failed: %s", e)
        return False
