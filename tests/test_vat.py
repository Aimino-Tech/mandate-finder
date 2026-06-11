from decimal import Decimal

from src.services.billing.vat import (
    GERMAN_VAT_RATE,
    calculate_vat,
)


def test_german_b2c_vat():
    result = calculate_vat(
        Decimal("100.00"),
        is_b2b=False,
        buyer_country="DE",
    )
    assert result.rate == GERMAN_VAT_RATE
    assert result.amount == Decimal("19.00")
    assert not result.is_b2b_reverse_charge


def test_german_b2b_valid_vat():
    result = calculate_vat(
        Decimal("100.00"),
        is_b2b=True,
        vat_id_valid=True,
        buyer_country="DE",
    )
    assert result.rate == Decimal("0")
    assert result.amount == Decimal("0")
    assert result.is_b2b_reverse_charge


def test_german_b2b_invalid_vat():
    result = calculate_vat(
        Decimal("100.00"),
        is_b2b=True,
        vat_id_valid=False,
        buyer_country="DE",
    )
    assert result.rate == GERMAN_VAT_RATE
    assert result.is_b2b_reverse_charge is False


def test_eu_b2b_valid_vat():
    result = calculate_vat(
        Decimal("200.00"),
        is_b2b=True,
        vat_id_valid=True,
        buyer_country="AT",
    )
    assert result.rate == Decimal("0")
    assert result.is_b2b_reverse_charge


def test_non_eu_b2b():
    result = calculate_vat(
        Decimal("100.00"),
        is_b2b=True,
        vat_id_valid=True,
        buyer_country="US",
    )
    assert result.rate == Decimal("0")
    assert result.is_b2b_reverse_charge


def test_vat_amount_precision():
    result = calculate_vat(
        Decimal("33.33"),
        is_b2b=False,
        buyer_country="DE",
    )
    assert result.amount == Decimal("6.33")
    assert result.rate == GERMAN_VAT_RATE
