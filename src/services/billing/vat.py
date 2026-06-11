from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from src.config import settings

GERMAN_VAT_RATE = Decimal("19.00")
REDUCED_VAT_RATE = Decimal("7.00")


@dataclass
class VatResult:
    rate: Decimal
    amount: Decimal
    is_b2b_reverse_charge: bool
    vat_id_valid: bool | None = None
    vat_country: str | None = None


async def validate_vat_id(vat_id: str) -> dict[str, Any]:
    clean = vat_id.upper().replace(" ", "").replace("-", "")
    if not clean.startswith("DE"):
        msg = "Only German VAT IDs (DE) are supported for validation"
        raise ValueError(msg)

    number = clean[2:]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            settings.vat_api_url,
            params={"wsdl": ""},
            content=f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
  xmlns:urn="urn:ec.europa.eu:taxation:customs:vies:checkVat:wsdl">
  <soap:Body>
    <urn:checkVat>
      <urn:countryCode>DE</urn:countryCode>
      <urn:vatNumber>{number}</urn:vatNumber>
    </urn:checkVat>
  </soap:Body>
</soap:Envelope>""",
            headers={"Content-Type": "text/xml; charset=utf-8"},
        )
        valid = "true" in resp.text and "invalid" not in resp.text.lower()
        return {"valid": valid, "country": "DE"}


def calculate_vat(
    net_amount: Decimal,
    *,
    is_b2b: bool = False,
    vat_id_valid: bool | None = None,
    buyer_country: str = "DE",
) -> VatResult:
    if is_b2b and vat_id_valid and buyer_country == "DE":
        return VatResult(
            rate=Decimal("0"),
            amount=Decimal("0"),
            is_b2b_reverse_charge=True,
            vat_id_valid=True,
            vat_country=buyer_country,
        )

    if is_b2b and vat_id_valid and buyer_country != "DE":
        if buyer_country in ("AT", "CH"):
            return VatResult(
                rate=Decimal("0"),
                amount=Decimal("0"),
                is_b2b_reverse_charge=True,
                vat_id_valid=True,
                vat_country=buyer_country,
            )
        return VatResult(
            rate=Decimal("0"),
            amount=Decimal("0"),
            is_b2b_reverse_charge=True,
            vat_id_valid=True,
            vat_country=buyer_country,
        )

    if buyer_country == "DE" or buyer_country in ("AT", "CH"):
        tax_rate = GERMAN_VAT_RATE
    else:
        tax_rate = Decimal("0")

    tax_amount = (net_amount * tax_rate / Decimal("100")).quantize(Decimal("0.01"))

    return VatResult(
        rate=tax_rate,
        amount=tax_amount,
        is_b2b_reverse_charge=False,
        vat_id_valid=vat_id_valid,
        vat_country=buyer_country,
    )
