from market_intelligence.workers.early_signal_scraper import parse_signal


def test_funding():
    s = parse_signal("TC", "TC raises $10M Series B", "https://x.com/1")
    assert s and s.signal_type == "funding" and s.predicted_hiring_window_days == 45


def test_leadership():
    s = parse_signal("CX", "CX appoints new CEO", "https://x.com/2")
    assert s and s.signal_type == "leadership_change"


def test_office():
    s = parse_signal("GI", "GI opens new office in Berlin", "https://x.com/3")
    assert s and s.signal_type == "new_office" and s.predicted_hiring_window_days == 30


def test_unrelated():
    assert parse_signal("NC", "NC releases earnings report", "https://x.com/4") is None
