import hashlib
import re
from dataclasses import dataclass, field
from typing import Protocol


class AgiClient(Protocol):
    async def check_semantic_match(
        self, job_a: dict, job_b: dict
    ) -> tuple[bool, float]:
        ...


@dataclass
class DedupResult:
    decision: str
    match_reason: str
    existing_record: dict | None
    confidence: float

    def __iter__(self):
        return iter((self.decision, self.existing_record, self.confidence))


_TOKEN_SPLIT = re.compile(r"[^a-zA-Z0-9]+")


def _normalize(s: str) -> str:
    return s.strip().lower()


def _tokens(s: str) -> set[str]:
    return {t for t in _TOKEN_SPLIT.split(_normalize(s)) if len(t) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _fingerprint(company: str, title: str, location: str) -> str:
    raw = f"{_normalize(company)}|{_normalize_title(title)}|{_normalize(location)}"
    return hashlib.md5(raw.encode()).hexdigest()


def _normalize_title(raw: str) -> str:
    _title_shortcuts = {
        "sr": "senior", "jr": "junior", "lead": "lead",
        "principal": "principal", "staff": "staff",
        "vp": "vice president", "vice pres": "vice president",
        "eng": "engineer", "eng.": "engineer",
        "mgr": "manager", "dir": "director",
        "dept": "department", "admin": "administrator",
        "asst": "assistant", "assoc": "associate",
        "coord": "coordinator", "coord.": "coordinator",
        "dev": "developer",
    }
    words = raw.split()
    expanded = []
    for w in words:
        cleaned = w.strip(".,()[]{}").lower()
        expanded.append(_title_shortcuts.get(cleaned, cleaned))
    result = " ".join(expanded)
    return re.sub(r"\s+", " ", result).strip()


@dataclass
class JobDedupEngine:
    agi_client: AgiClient | None = None
    fingerprint_confidence: float = 0.98
    source_id_confidence: float = 0.99
    semantic_threshold: float = 0.55
    _semantic_titles: set = field(default_factory=lambda: {"senior", "junior", "lead", "sr", "jr", "principal", "staff", "head", "manager", "director", "vp", "vice", "president"})

    async def check_new(
        self,
        job: dict,
        existing: list[dict] | None = None,
        cache: dict[str, str] | None = None,
    ) -> DedupResult:
        existing = existing or []
        cache = cache or {}

        result = self._check_cache(job, cache)
        if result.decision != "NEW":
            return result

        result = self._check_source_id(job, existing)
        if result.decision != "NEW":
            return result

        result = self._check_fingerprint(job, existing)
        if result.decision != "NEW":
            return result

        result = await self._check_semantic(job, existing)
        if result.decision != "NEW":
            return result

        return DedupResult("NEW", None, None, 1.0)

    def _check_cache(
        self, job: dict, cache: dict[str, str]
    ) -> DedupResult:
        cache_key = self._cache_key(job)
        cached_decision = cache.get(cache_key)
        if cached_decision == "EXISTING":
            return DedupResult("EXISTING", "CACHE", None, 1.0)
        return DedupResult("NEW", None, None, 0.0)

    def _check_source_id(
        self, job: dict, existing: list[dict]
    ) -> DedupResult:
        source = job.get("source")
        source_job_id = job.get("source_job_id")
        if not source or not source_job_id:
            return DedupResult("NEW", None, None, 0.0)

        for rec in existing:
            if rec.get("source") == source and rec.get("source_job_id") == source_job_id:
                return DedupResult(
                    "EXISTING", "SOURCE_ID", rec, self.source_id_confidence
                )
        return DedupResult("NEW", None, None, 0.0)

    def _check_fingerprint(
        self, job: dict, existing: list[dict]
    ) -> DedupResult:
        fp = _fingerprint(
            job.get("company", ""),
            job.get("title", ""),
            job.get("location", ""),
        )
        for rec in existing:
            rec_fp = _fingerprint(
                rec.get("company", ""),
                rec.get("title", ""),
                rec.get("location", ""),
            )
            if fp == rec_fp:
                return DedupResult(
                    "FINGERPRINT", "FINGERPRINT", rec, self.fingerprint_confidence
                )
        return DedupResult("NEW", None, None, 0.0)

    async def _check_semantic(
        self, job: dict, existing: list[dict]
    ) -> DedupResult:
        if self.agi_client is not None:
            return await self._check_semantic_agi(job, existing)
        return self._check_semantic_fallback(job, existing)

    async def _check_semantic_agi(
        self, job: dict, existing: list[dict]
    ) -> DedupResult:
        highest: DedupResult = DedupResult("NEW", None, None, 0.0)
        for rec in existing:
            is_match, confidence = await self.agi_client.check_semantic_match(job, rec)
            if is_match and confidence > highest.confidence:
                highest = DedupResult("MERGED", "SEMANTIC", rec, confidence)
        return highest

    def _check_semantic_fallback(
        self, job: dict, existing: list[dict]
    ) -> DedupResult:
        job_title_tokens = _tokens(job.get("title", ""))
        job_company_tokens = _tokens(job.get("company", ""))
        job_location_tokens = _tokens(job.get("location", ""))

        highest: DedupResult = DedupResult("NEW", None, None, 0.0)
        for rec in existing:
            title_sim = _jaccard(
                job_title_tokens, _tokens(rec.get("title", ""))
            )
            company_sim = _jaccard(
                job_company_tokens, _tokens(rec.get("company", ""))
            )
            location_sim = _jaccard(
                job_location_tokens, _tokens(rec.get("location", ""))
            )

            company_weight = 0.4
            title_weight = 0.35
            location_weight = 0.25
            combined = (
                company_sim * company_weight
                + title_sim * title_weight
                + location_sim * location_weight
            )

            if combined >= self.semantic_threshold and combined > highest.confidence:
                highest = DedupResult("MERGED", "SEMANTIC", rec, combined)

        return highest

    @staticmethod
    def _cache_key(job: dict) -> str:
        source = job.get("source", "")
        source_job_id = job.get("source_job_id", "")
        if source and source_job_id:
            return f"source:{source}:{source_job_id}"
        fp = _fingerprint(
            job.get("company", ""),
            job.get("title", ""),
            job.get("location", ""),
        )
        return f"fp:{fp}"
