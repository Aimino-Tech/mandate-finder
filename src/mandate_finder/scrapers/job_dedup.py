"""Multi-level job posting deduplication engine.

Four levels of dedup, each returning (decision, existing_record, confidence):

    Level 1 — SOURCE_ID   : Same (source, source_job_id) -> EXISTING
    Level 2 — FINGERPRINT : MD5 fingerprint collision     -> FINGERPRINT
    Level 3 — SEMANTIC    : AGI-powered similarity check  -> MERGED
    Level 4 — CACHE       : DedupCache lookup             -> CACHE
"""

from __future__ import annotations

import hashlib
import json
import logging
from enum import StrEnum
from typing import Any, NamedTuple
from uuid import UUID

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------
class DedupDecision(StrEnum):
    NEW = "NEW"
    EXISTING = "EXISTING"
    FINGERPRINT = "FINGERPRINT"
    MERGED = "MERGED"
    CACHE = "CACHE"


class DedupResult(NamedTuple):
    decision: DedupDecision
    existing_id: UUID | None
    confidence: float
    detail: str | None = None


# ---------------------------------------------------------------------------
# Fingerprint computation
# ---------------------------------------------------------------------------
def compute_fingerprint(posting: dict[str, Any]) -> str:
    """Compute an MD5 fingerprint from the core identifying fields.

    Uses title (normalized), company_name, and location to generate
    a consistent hash for exact-match dedup.
    """
    raw = {
        "title": (posting.get("normalized_title") or posting.get("title") or "").strip().lower(),
        "company": (posting.get("company_name") or posting.get("company") or "").strip().lower(),
        "location": (posting.get("location") or "").strip().lower(),
    }
    serialized = json.dumps(raw, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Semantic similarity (heuristic baseline)
# ---------------------------------------------------------------------------
# Synonym map for job-title-related terms
_TITLE_SYNONYMS: dict[str, set[str]] = {
    "frontend": {"react", "angular", "vue", "svelte", "ui", "ux"},
    "backend": {"node", "django", "flask", "spring", "api", "server"},
    "fullstack": {"full stack", "react", "angular", "node", "frontend", "backend"},
    "engineer": {"developer", "engineer", "programmer", "architect", "sde"},
    "developer": {"developer", "engineer", "programmer", "architect", "sde"},
    "react": {"frontend", "javascript", "typescript", "web"},
    "senior": {"senior", "sr", "lead", "principal", "staff"},
    "junior": {"junior", "jr", "entry", "associate"},
    "software": {"software", "sw", "application", "platform"},
    "manager": {"manager", "mgr", "head", "director"},
    "data": {"data", "analytics", "ml", "machine learning", "ai"},
}


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard index: |intersection| / |union|."""
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / max(len(set_a | set_b), 1)


def _synonym_boost(
    words_a: set[str], words_b: set[str]
) -> float:
    """Score boost from cross-term synonyms.

    For each word in A, if it has synonyms in _TITLE_SYNONYMS, check whether
    any synonym appears in B.  Returns fraction of A-words that have a
    semantic link to B.
    """
    if not words_a or not words_b:
        return 0.0
    linked = 0
    for word in words_a:
        synonyms = _TITLE_SYNONYMS.get(word, set())
        # also treat the word itself as its own synonym
        if word in words_b:
            linked += 1
        elif synonyms & words_b:
            linked += 1
    return linked / len(words_a)


async def _semantic_similarity(
    a: dict[str, Any],
    b: dict[str, Any],
) -> float:
    """Compare two job postings using semantic similarity.

    Uses a lightweight heuristic based on title/company/location token overlap
    with synonym boosting for common tech/role terms.
    In production this would call an AGI embedding model.

    Returns a float in [0.0, 1.0].
    """
    title_a = set((a.get("normalized_title") or a.get("title") or "").lower().split())
    title_b = set((b.get("normalized_title") or b.get("title") or "").lower().split())
    company_a = (a.get("company_name") or a.get("company") or "").lower().strip()
    company_b = (b.get("company_name") or b.get("company") or "").lower().strip()
    location_a = (a.get("location") or "").lower().strip()
    location_b = (b.get("location") or "").lower().strip()

    if not title_a or not title_b:
        return 0.0

    # 1. Direct Jaccard overlap
    jaccard = _jaccard_similarity(title_a, title_b)

    # 2. Synonym-boosted overlap
    syn_boost_a = _synonym_boost(title_a, title_b)
    syn_boost_b = _synonym_boost(title_b, title_a)
    syn_boost = (syn_boost_a + syn_boost_b) / 2.0

    # Combined title score: use the max of Jaccard and synonym boost
    title_score = jaccard * 0.5 + syn_boost * 0.5

    company_match = 1.0 if company_a and company_b and company_a == company_b else 0.0
    location_match = 1.0 if location_a and location_b and location_a == location_b else 0.0

    score = title_score * 0.6 + company_match * 0.25 + location_match * 0.15
    return min(score, 1.0)


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------
class JobDedupEngine:
    """Four-level dedup engine for job postings.

    Usage::

        engine = JobDedupEngine()
        decision, existing_id, confidence = await engine.check_new(posting, existing=[])
        if decision == DedupDecision.NEW:
            # persist posting
            ...
    """

    FINGERPRINT_THRESHOLD = 0.95
    SEMANTIC_THRESHOLD = 0.75
    CACHE_THRESHOLD = 0.90

    @staticmethod
    async def check_new(
        posting: dict[str, Any],
        existing: list[dict[str, Any]] | None = None,
        cache_entries: list[dict[str, Any]] | None = None,
    ) -> DedupResult:
        """Run all four dedup levels against *existing* records.

        Args:
            posting: The incoming job posting dict (must include at least
                ``title``, optionally ``normalized_title``, ``company_name``,
                ``location``, ``source``, ``source_job_id``).
            existing: List of already-persisted job posting dicts.
            cache_entries: List of ``DedupCache`` entry dicts keyed by
                ``fingerprint_md5``.

        Returns:
            A ``DedupResult`` with the strongest match found.
        """
        engine = JobDedupEngine()

        # Level 1 — Source ID exact match
        src_result = engine._check_source_id(posting, existing or [])
        if src_result.decision != DedupDecision.NEW:
            return src_result

        fingerprint = compute_fingerprint(posting)

        # Level 2 — Fingerprint MD5
        fp_result = engine._check_fingerprint(fingerprint, existing or [])
        if fp_result.decision != DedupDecision.NEW:
            return fp_result

        # Level 3 — Semantic (AGI)
        sem_result = await engine._check_semantic(posting, existing or [])
        if sem_result.decision != DedupDecision.NEW:
            return sem_result

        # Level 4 — DedupCache
        cache_result = engine._check_cache(fingerprint, cache_entries or [])
        if cache_result.decision != DedupDecision.NEW:
            return cache_result

        return DedupResult(
            decision=DedupDecision.NEW,
            existing_id=None,
            confidence=1.0,
            detail="No duplicate found across any dedup level",
        )

    # ------------------------------------------------------------------
    # Individual level checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_source_id(
        posting: dict[str, Any],
        existing: list[dict[str, Any]],
    ) -> DedupResult:
        """Level 1: Same (source, source_job_id) -> EXISTING."""
        source = posting.get("source")
        source_job_id = posting.get("source_job_id")
        if not source or not source_job_id:
            return DedupResult(DedupDecision.NEW, None, 1.0)

        for record in existing:
            if (
                record.get("source") == source
                and record.get("source_job_id") == source_job_id
            ):
                return DedupResult(
                    decision=DedupDecision.EXISTING,
                    existing_id=_get_id(record),
                    confidence=1.0,
                    detail=f"Source ID match: {source}/{source_job_id}",
                )
        return DedupResult(DedupDecision.NEW, None, 1.0)

    @staticmethod
    def _check_fingerprint(
        fingerprint: str,
        existing: list[dict[str, Any]],
    ) -> DedupResult:
        """Level 2: MD5 fingerprint collision -> FINGERPRINT."""
        if not fingerprint:
            return DedupResult(DedupDecision.NEW, None, 1.0)

        for record in existing:
            record_fp = record.get("fingerprint_md5")
            if record_fp and record_fp == fingerprint:
                return DedupResult(
                    decision=DedupDecision.FINGERPRINT,
                    existing_id=_get_id(record),
                    confidence=0.98,
                    detail=f"Fingerprint match: {fingerprint}",
                )
        return DedupResult(DedupDecision.NEW, None, 1.0)

    @staticmethod
    async def _check_semantic(
        posting: dict[str, Any],
        existing: list[dict[str, Any]],
    ) -> DedupResult:
        """Level 3: Semantic (AGI) similarity -> MERGED."""
        best_score = 0.0
        best_record: dict[str, Any] | None = None

        for record in existing:
            score = await _semantic_similarity(posting, record)
            if score > best_score:
                best_score = score
                best_record = record

        if best_score >= JobDedupEngine.SEMANTIC_THRESHOLD:
            return DedupResult(
                decision=DedupDecision.MERGED,
                existing_id=_get_id(best_record) if best_record else None,
                confidence=round(best_score, 4),
                detail=f"Semantic match (score={best_score:.4f})",
            )
        return DedupResult(DedupDecision.NEW, None, 1.0)

    @staticmethod
    def _check_cache(
        fingerprint: str,
        cache_entries: list[dict[str, Any]],
    ) -> DedupResult:
        """Level 4: DedupCache lookup -> CACHE."""
        if not fingerprint:
            return DedupResult(DedupDecision.NEW, None, 1.0)

        for entry in cache_entries:
            if entry.get("fingerprint_md5") == fingerprint:
                conf = entry.get("confidence", 0.9)
                if conf >= JobDedupEngine.CACHE_THRESHOLD:
                    return DedupResult(
                        decision=DedupDecision.CACHE,
                        existing_id=entry.get("merged_job_posting_id"),
                        confidence=conf,
                        detail=f"Cache match for fingerprint {fingerprint}",
                    )
        return DedupResult(DedupDecision.NEW, None, 1.0)

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    @staticmethod
    async def merge_job_postings(
        primary: dict[str, Any],
        duplicate: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge two job posting records into one consolidated record.

        The *primary* record takes precedence; fields from *duplicate* are
        used only when the primary has a null/empty value.
        """
        merged = dict(primary)

        for key in (
            "title",
            "normalized_title",
            "company_name",
            "location",
            "description",
            "salary_min",
            "salary_max",
            "salary_currency",
            "employment_type",
            "source_url",
            "occupation_code",
        ):
            if not merged.get(key) and duplicate.get(key):
                merged[key] = duplicate[key]

        primary_skills: list[str] = primary.get("skills") or []
        duplicate_skills: list[str] = duplicate.get("skills") or []
        merged["skills"] = list(set(primary_skills) | set(duplicate_skills))

        merged["source_job_ids"] = list(
            set(
                (primary.get("source_job_ids") or [primary.get("source_job_id")])
                + (duplicate.get("source_job_ids") or [duplicate.get("source_job_id")])
            )
        )
        merged.setdefault("_merged_from", []).append(
            str(duplicate.get("id", "unknown"))
        )
        merged["fingerprint_md5"] = primary.get("fingerprint_md5")

        return merged


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_id(record: dict[str, Any]) -> UUID | None:
    """Extract UUID id from a record dict (handles string or UUID)."""
    raw = record.get("id")
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    try:
        return UUID(str(raw))
    except (ValueError, AttributeError):
        return None
