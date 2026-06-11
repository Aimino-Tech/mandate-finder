import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx

BA_BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche/v1"
BA_API_KEY_HEADER = "X-API-Key"

XML_NS = {
    "job": "http://www.arbeitsagentur.de/jobboerse/jobsuche/v1/schema",
}

DAILY_LIMIT = 1000


class BundesagenturClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = BA_BASE_URL,
        daily_limit: int = DAILY_LIMIT,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._daily_limit = daily_limit
        self._daily_count = 0
        self._client = httpx.AsyncClient(
            headers={BA_API_KEY_HEADER: api_key, "Accept": "application/xml"},
            timeout=30.0,
        )

    async def search_jobs(
        self,
        keywords: str,
        location: str | None = None,
        page: int = 0,
        radius: int = 50,
        occupation_code: str | None = None,
    ) -> list[dict[str, Any]]:
        if self._daily_count >= self._daily_limit:
            raise RuntimeError(f"Daily API limit of {self._daily_limit} reached")

        params: dict[str, str | int] = {
            "suchbegriff": keywords,
            "seite": page,
            "raeumlich": radius,
            "size": 100,
        }
        if location:
            params["ort"] = location
        if occupation_code:
            params["berufsfeld"] = occupation_code

        response = await self._client.get(f"{self._base_url}/jobsuche", params=params)
        response.raise_for_status()
        self._daily_count += 1

        return self.parse_job_response(response.text)

    @staticmethod
    def parse_job_response(xml: str) -> list[dict[str, Any]]:
        root = ET.fromstring(xml)
        jobs: list[dict[str, Any]] = []

        for item in root.iterfind(".//job:job", XML_NS):
            job = BundesagenturClient._parse_job_item(item)
            if job:
                jobs.append(job)

        return jobs

    @staticmethod
    def _parse_job_item(item: ET.Element) -> dict[str, Any] | None:
        ref = item.get("ref", "")
        if not ref:
            return None

        def text(tag: str) -> str | None:
            el = item.find(f"job:{tag}", XML_NS)
            return el.text.strip() if el is not None and el.text else None

        def parse_dt(val: str | None) -> datetime | None:
            if not val:
                return None
            try:
                return datetime.fromisoformat(val).replace(tzinfo=timezone.utc)
            except ValueError:
                return None

        location_raw = text("ort")
        location_city = None
        location_state = None
        if location_raw and "," in location_raw:
            parts = location_raw.split(",", 1)
            location_city = parts[0].strip()
            location_state = parts[1].strip()
        elif location_raw:
            location_city = location_raw

        return {
            "ba_job_id": ref,
            "title": text("titel") or "",
            "company_name": text("arbeitgeber") or "",
            "location_city": location_city,
            "location_state": location_state,
            "description": text("kurzbeschreibung") or text("beschreibung"),
            "occupation_code": text("berufsgattung"),
            "employment_type": BundesagenturClient._map_employment_type(text("beschaeftigungsart")),
            "source_url": text("bewerbungsURL"),
            "posted_at": parse_dt(text("veroeffentlichungsdatum")),
            "last_modified": (
                parse_dt(text("aenderungsdatum"))
                or parse_dt(text("veroeffentlichungsdatum"))
                or datetime.now(timezone.utc)
            ),
        }

    @staticmethod
    def _map_employment_type(raw: str | None) -> str:
        if not raw:
            return "other"
        mapping = {
            "Vollzeit": "full_time",
            "Teilzeit": "part_time",
            "Befristet": "temporary",
            "Praktikum": "internship",
            "Minijob": "mini_job",
            "Ausbildung": "trainee",
        }
        return mapping.get(raw, "other")

    async def close(self) -> None:
        await self._client.aclose()
