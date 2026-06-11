"""Parser for Bundesagentur für Arbeit API responses.

Handles both JSON and XML response formats, normalizing fields
into the JobPosting schema.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# Mapping of BA employment type codes to human-readable values
EMPLOYMENT_TYPE_MAP: dict[str, str] = {
    "1": "full_time",
    "2": "part_time",
    "3": "mini_job",
    "4": "internship",
    "5": "training",
    "6": "contractor",
    "7": "seasonal",
    "8": "remote",
}

# Mapping of BA occupation codes to broad industry categories (simplified)
INDUSTRY_MAP: dict[str, str] = {
    "1": "agriculture",
    "2": "manufacturing",
    "3": "construction",
    "4": "trade",
    "5": "hospitality",
    "6": "transport",
    "7": "finance",
    "8": "technology",
    "9": "education",
    "10": "healthcare",
    "11": "public_service",
}


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse a BA API date string into a datetime object."""
    if not date_str:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d",
        "%d.%m.%Y",
    ):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    logger.debug("Could not parse date: %s", date_str)
    return None


def _parse_salary(salary_info: dict[str, Any] | None) -> dict[str, Any]:
    """Extract salary info from BA API response fragment."""
    if not salary_info:
        return {"salary_min": None, "salary_max": None, "salary_currency": None}

    result: dict[str, Any] = {
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "EUR",
    }

    min_val = salary_info.get("minValue") or salary_info.get("von")
    max_val = salary_info.get("maxValue") or salary_info.get("bis")

    if min_val:
        try:
            result["salary_min"] = float(min_val)
        except (ValueError, TypeError):
            pass
    if max_val:
        try:
            result["salary_max"] = float(max_val)
        except (ValueError, TypeError):
            pass
    if salary_info.get("currency"):
        result["salary_currency"] = salary_info["currency"]

    return result


def _extract_location(location_data: dict[str, Any] | None) -> dict[str, Any]:
    """Extract location info from BA API response fragment."""
    result: dict[str, Any] = {
        "location_city": None,
        "location_state": None,
        "location": None,
    }

    if not location_data:
        return result

    city = (
        location_data.get("ort") or location_data.get("city") or location_data.get("cityName") or ""
    )
    region = (
        location_data.get("region") or location_data.get("bundesland") or location_data.get("state") or ""
    )
    full = location_data.get("ortMitPLZ") or location_data.get("full") or location_data.get("displayName") or ""

    if city:
        result["location_city"] = city.strip()
    if region:
        result["location_state"] = region.strip()
    if full:
        result["location"] = full.strip()
    elif city and region:
        result["location"] = f"{city}, {region}"
    elif city:
        result["location"] = city

    return result


def parse_job_response(response_data: dict[str, Any] | bytes | str) -> list[dict[str, Any]]:
    """Parse a BA API search response into a list of normalized job records.

    Supports both JSON (dict) and XML (bytes/str) response formats.

    Args:
        response_data: Raw BA API response (dict for JSON, bytes/str for XML).

    Returns:
        List of normalized job posting dicts ready for storage.
    """
    if isinstance(response_data, (bytes, str)):
        return _parse_xml_response(response_data)
    return _parse_json_response(response_data)


def _parse_json_response(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a JSON BA API response."""
    results: list[dict[str, Any]] = []
    items = data.get("list", data.get("ergebnisse", data.get("items", [])))

    for item in items:
        if not item:
            continue

        # Navigate BA's nested response structure
        content = item.get("beruf", item.get("job", item.get("content", item)))

        title = (
            content.get("titel")
            or content.get("berufsbezeichnung")
            or content.get("title")
            or ""
        )
        source_job_id = (
            content.get("refnr")
            or content.get("id")
            or content.get("stellenangebotId")
            or content.get("source_id")
            or ""
        )
        company_name = (
            content.get("arbeitgeber")
            or content.get("unternehmen")
            or content.get("company")
            or content.get("company_name")
            or ""
        )

        description = (
            content.get("beschreibung")
            or content.get("stellenbeschreibung")
            or content.get("description")
            or content.get("kurztext")
            or ""
        )

        source_url = (
            content.get("link")
            or content.get("url")
            or content.get("bewerbungsurl")
            or ""
        )

        raw_location = content.get("ort", content.get("location", {}))
        location_info = _extract_location(
            raw_location if isinstance(raw_location, dict) else {"ort": str(raw_location)}
        )

        salary_info = _parse_salary(content.get("vergutung", content.get("salary")))

        employment_type_raw = content.get("art", content.get("employmentType", ""))
        employment_type = EMPLOYMENT_TYPE_MAP.get(
            str(employment_type_raw), str(employment_type_raw) if employment_type_raw else None
        )

        posted_at_raw = content.get("aktuelleVeroeffentlichungsdatum") or content.get(
            "veroeffentlichungsdatum"
        ) or content.get("posted_at") or content.get("datum")

        occupation_code = content.get("berufscode") or content.get("occupation_code") or content.get("schluessel")

        record = {
            "source_job_id": source_job_id,
            "title": title,
            "company_name": company_name,
            "description": description,
            "source_url": source_url,
            "posted_at": _parse_date(posted_at_raw),
            "occupation_code": str(occupation_code) if occupation_code else None,
            "employment_type": employment_type,
            "raw_data": item,
            **location_info,
            **salary_info,
        }
        results.append(record)

    logger.debug("Parsed %d jobs from BA JSON response", len(results))
    return results


def _parse_xml_response(data: bytes | str) -> list[dict[str, Any]]:
    """Parse an XML BA API response (legacy format)."""
    import xml.etree.ElementTree as ET

    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace")

    root = ET.fromstring(data)
    ns = _detect_xml_namespace(root)
    results: list[dict[str, Any]] = []

    items = root.findall(f".//{ns}ergebnis") or root.findall(f".//{ns}item") or root.findall(".//ergebnis") or root.findall(".//item") or [root]

    for item in items:
        content = item
        title = _xml_text(content, "titel", ns) or _xml_text(content, "berufsbezeichnung", ns) or ""
        source_job_id = _xml_text(content, "refnr", ns) or _xml_text(content, "id", ns) or ""
        company_name = _xml_text(content, "arbeitgeber", ns) or _xml_text(content, "unternehmen", ns) or ""

        description = _xml_text(content, "beschreibung", ns) or _xml_text(content, "stellenbeschreibung", ns) or ""
        source_url = _xml_text(content, "link", ns) or _xml_text(content, "url", ns) or ""

        city = _xml_text(content, "ort", ns) or ""
        region = _xml_text(content, "region", ns) or _xml_text(content, "bundesland", ns) or ""

        posted_at_raw = _xml_text(content, "aktuelleVeroeffentlichungsdatum", ns) or _xml_text(content, "veroeffentlichungsdatum", ns)

        occupation_code = _xml_text(content, "berufscode", ns) or _xml_text(content, "schluessel", ns)

        record: dict[str, Any] = {
            "source_job_id": source_job_id,
            "title": title,
            "company_name": company_name,
            "description": description,
            "source_url": source_url,
            "posted_at": _parse_date(posted_at_raw),
            "occupation_code": occupation_code or None,
            "employment_type": None,
            "location_city": city or None,
            "location_state": region or None,
            "location": f"{city}, {region}".strip(", ") or None,
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "raw_data": _element_to_dict(item),
        }
        results.append(record)

    logger.debug("Parsed %d jobs from BA XML response", len(results))
    return results


def _detect_xml_namespace(root: Any) -> str:
    """Detect XML namespace prefix from the root element."""
    m = re.match(r"\{(.+?)\}", root.tag)
    if m:
        return "{" + m.group(1) + "}"
    return ""


def _xml_text(element: Any, tag: str, ns: str = "") -> str | None:
    """Get text content of a child XML element, if it exists."""
    if ns:
        child = element.find(f"{ns}{tag}")
    else:
        child = element.find(tag)
        if child is None:
            child = element.find(f".//{tag}")
    return child.text.strip() if child is not None and child.text else None


def _element_to_dict(element: Any) -> dict[str, Any]:
    """Convert an XML element to a simple dict for raw_data storage."""
    result: dict[str, Any] = {}
    for child in element:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if len(child) > 0:
            result[tag] = _element_to_dict(child)
        else:
            result[tag] = child.text or ""
    return result
