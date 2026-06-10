from datetime import datetime

from market_intelligence.models import EarlySignal, Industry

_FUNDING_KW = ["raised", "series a", "series b", "series c", "seed round", "funding", "finanzierung", "investition", "wachstumskapital"]
_LEADERSHIP_KW = ["new ceo", "neuer ceo", "appointed", "ernannt", "chief", "vp of", "head of", "director of", "leadership change", "c-level", "vorstand"]
_OFFICE_KW = ["new office", "expansion", "eröffnet", "standort", "niederlassung", "new location", "expands to", "wachstum"]
_INDUSTRY_MAP: dict[Industry, list[str]] = {
    Industry.health: ["health", "biotech", "pharma", "medical", "gesundheit"],
    Industry.finance: ["fintech", "bank", "insurance", "finance"],
    Industry.technology: ["tech", "software", "saas", "ai", "cloud", "digital"],
    Industry.manufacturing: ["manufacturing", "industrial", "produktion"],
    Industry.retail: ["retail", "e-commerce", "commerce"],
    Industry.energy: ["energy", "cleantech", "renewable", "solar"],
    Industry.logistics: ["logistics", "delivery", "transport"],
}


def _confidence(h: str) -> float:
    hl = h.lower()
    s = 0.3
    if "series b" in hl or "series c" in hl:
        s += 0.3
    if any(w in hl for w in ["million", "billion", "mr", "mio"]):
        s += 0.2
    if any(k in hl for k in _LEADERSHIP_KW):
        s += 0.2
    if any(k in hl for k in _OFFICE_KW):
        s += 0.2
    return min(s, 0.95)


def _window(h: str, st: str) -> int | None:
    if st == "funding":
        hl = h.lower()
        if "series a" in hl:
            return 60
        if "series b" in hl:
            return 45
        if "series c" in hl or "series d" in hl:
            return 30
        return 60 if not any(w in hl for w in ["million", "billion"]) else 45
    if st == "new_office":
        return 30
    return None


def _detect_type(h: str) -> str | None:
    hl = h.lower()
    scores = [("funding", sum(1 for k in _FUNDING_KW if k in hl)), ("leadership_change", sum(1 for k in _LEADERSHIP_KW if k in hl)), ("new_office", sum(1 for k in _OFFICE_KW if k in hl))]
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[0][0] if scores[0][1] > 0 else None


def _infer_industry(h: str) -> Industry:
    hl = h.lower()
    for ind, kw in _INDUSTRY_MAP.items():
        if any(k in hl for k in kw):
            return ind
    return Industry.other


def parse_signal(company: str, headline: str, source_url: str) -> EarlySignal | None:
    st = _detect_type(headline)
    if st is None:
        return None
    return EarlySignal(signal_type=st, company=company, industry=_infer_industry(headline), headline=headline, source_url=source_url, detected_at=datetime.now(), confidence=round(_confidence(headline), 2), predicted_hiring_window_days=_window(headline, st))
