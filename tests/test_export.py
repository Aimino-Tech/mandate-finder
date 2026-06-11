from datetime import datetime

import pytest

from market_intelligence.models import TrendPoint, TrendReport, TrendSeries
from market_intelligence.services.export import export_report


def _r():
    return TrendReport(generated_at=datetime.now(), top_growing_roles=[TrendSeries(category="engineering", points=[TrendPoint(date=datetime.now().date(), value=10, moving_avg=9.5)], growth_rate=0.15, direction="up")], industry_pulse=[], early_warnings=[])


def test_csv():
    c = export_report(_r(), fmt="csv").decode()
    assert "engineering" in c and "0.15" in c


def test_pdf():
    p = export_report(_r(), fmt="pdf")
    assert p.startswith(b"%PDF") and len(p) > 100


def test_invalid():
    with pytest.raises(ValueError, match="Unsupported format"):
        export_report(_r(), fmt="xlsx")
