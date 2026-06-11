"""Job posting normalizer — title normalization, salary extraction,
skill detection, and employment type classification."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Title normalisation map
# Applied in order; more-specific patterns first.
# NOTE: patterns without trailing \b when they end with optional \.?
# because \b doesn't work after a non-word char like '.' followed by space.
# ---------------------------------------------------------------------------
TITLE_REPLACEMENTS: list[tuple[str, str]] = [
    # Seniority levels
    (r"\bSr(?:\.)?(?=\s|$)", "Senior"),
    (r"\bJr(?:\.)?(?=\s|$)", "Junior"),
    (r"\bMid[- ]?Level\b", "Mid-Level"),
    (r"\bLead\b", "Lead"),
    (r"\bPrincipal\b", "Principal"),
    (r"\bStaff\b", "Staff"),
    # Abbreviations in job titles
    (r"\bEng(?:ineer)?(?:\.)?(?=\s|$)", "Engineer"),
    (r"\bDev(?:eloper)?(?:\.)?(?=\s|$)", "Developer"),
    (r"\bMgr(?:\.)?(?=\s|$)", "Manager"),
    (r"\bMgmt\b", "Management"),
    (r"\bSpec(?:ialist)?(?:\.)?(?=\s|$)", "Specialist"),
    (r"\bArch(?:itect)?(?:\.)?(?=\s|$)", "Architect"),
    (r"\bAnalyst\b", "Analyst"),
    (r"\bCoord(?:inator)?\b", "Coordinator"),
    (r"\bAssoc(?:iate)?\b", "Associate"),
    (r"\bAsst(?:\.)?(?=\s|$)", "Assistant"),
    (r"\bVP\b", "Vice President"),
    (r"\bDir(?:ector)?(?:\.)?(?=\s|$)", "Director"),
    # Tech-specific abbreviations
    (r"\bFE\b", "Frontend"),
    (r"\bBE\b", "Backend"),
    (r"\bFS\b", "Full Stack"),
    (r"\bUX\b", "UX"),
    (r"\bUI\b", "UI"),
    (r"\bML\b", "Machine Learning"),
    (r"\bAI\b", "AI"),
    (r"\bNLP\b", "NLP"),
    (r"\bQA\b", "QA"),
    (r"\bSW\b", "Software"),
    (r"\bSDE\b", "Software Development Engineer"),
    (r"\bSRE\b", "Site Reliability Engineer"),
    (r"\bInfra\b", "Infrastructure"),
    # German / European parenthetical markers
    (r"\(m/f/x\)", ""),
    (r"\(m/w/d\)", ""),
    (r"\(m/f\)", ""),
    (r"\(w/m\)", ""),
    (r"\(all genders\)", ""),
    (r"\bin Vollzeit\b", ""),
    (r"\bin Teilzeit\b", ""),
]

# ---------------------------------------------------------------------------
# Salary regex patterns
# ---------------------------------------------------------------------------
SALARY_PATTERNS: list[re.Pattern[str]] = [
    # Pattern 1: currency before min, optional currency before max
    re.compile(
        r"(?P<currency>€|\$|£|CHF|EUR|USD|GBP)?\s*"
        r"(?P<min>[\d]{2,3}(?:[.,]\d{3})*(?:[kK])?)\s*"
        r"[-–]\s*"
        r"(?:€|\$|£|CHF|EUR|USD|GBP)?\s*"
        r"(?P<max>[\d]{2,3}(?:[.,]\d{3})*(?:[kK])?)\s*"
        r"(?P<period>/yr|/year|/annum|p\.?a\.?|per year|annually)?",
        re.IGNORECASE,
    ),
    # Pattern 2: currency after max
    re.compile(
        r"(?P<min>[\d]{2,3}(?:[.,]\d{3})*(?:[kK])?)\s*"
        r"[-–]\s*"
        r"(?P<max>[\d]{2,3}(?:[.,]\d{3})*(?:[kK])?)\s*"
        r"(?P<currency>€|\$|£|CHF|EUR|USD|GBP)?\s*"
        r"(?P<period>/yr|/year|/annum|p\.?a\.?|per year|annually)?",
        re.IGNORECASE,
    ),
    # Pattern 3: single value with per-hour
    re.compile(
        r"(?P<currency>€|\$|£|CHF|EUR|USD|GBP)?\s*"
        r"(?P<min>[\d]{2,3}(?:[.,]\d{3})*(?:[kK])?)\s*"
        r"(?P<period>/hr|/hour|per hour|hourly)?",
        re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# Known skill keywords
# ---------------------------------------------------------------------------
KNOWN_SKILLS: set[str] = {
    "python", "javascript", "typescript", "java", "c#", "c++", "go", "golang",
    "rust", "ruby", "php", "scala", "kotlin", "swift", "objective-c", "perl",
    "r", "matlab", "dart", "elixir", "clojure", "haskell", "lua",
    "react", "angular", "vue", "svelte", "next.js", "nuxt", "redux",
    "html", "css", "scss", "sass", "tailwind", "bootstrap", "webpack",
    "vite", "jest", "cypress", "storybook",
    "node.js", "express", "django", "flask", "fastapi", "spring boot",
    "asp.net", "rails", "laravel", "symfony", "gin", "echo",
    "postgresql", "postgres", "mysql", "mongodb", "redis", "elasticsearch",
    "cassandra", "dynamodb", "sqlite", "mariadb", "cockroachdb",
    "sql", "nosql",
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "k8s",
    "terraform", "ansible", "puppet", "chef", "jenkins", "github actions",
    "gitlab ci", "circleci", "argocd", "helm",
    "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy", "spark",
    "apache spark", "hadoop", "airflow", "dbt", "kafka", "rabbitmq",
    "machine learning", "deep learning", "nlp", "computer vision",
    "llm", "langchain", "openai", "generative ai",
    "unit testing", "integration testing", "e2e", "selenium", "playwright",
    "pytest", "junit", "mocha",
    "git", "github", "gitlab", "bitbucket", "jira", "confluence",
    "agile", "scrum", "kanban", "ci/cd", "microservices",
    "rest api", "graphql", "grpc", "websocket",
    "oauth", "jwt", "saml", "ssl/tls", "penetration testing",
    "sap", "salesforce", "servicenow", "workday",
}

# ---------------------------------------------------------------------------
# Employment type classification
# ---------------------------------------------------------------------------
EMPLOYMENT_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("full-time", re.compile(r"\b(?:full[- ]?time|vollzeit|permanent|festanstellung)\b", re.IGNORECASE)),
    ("part-time", re.compile(r"\b(?:part[- ]?time|teilzeit|halbzeit)\b", re.IGNORECASE)),
    ("contract", re.compile(r"\b(?:contract|contractor|fixed[- ]?term|befristet|consultant)\b", re.IGNORECASE)),
    ("freelance", re.compile(r"\b(?:freelance|freelancer|free[- ]?lancer|selbstständig|independent)\b", re.IGNORECASE)),
    ("internship", re.compile(r"\b(?:internship|intern|praktikum|trainee|werkstudent)\b", re.IGNORECASE)),
    ("temporary", re.compile(r"\b(?:temporary|temp|zeitarbeit|leiharbeit)\b", re.IGNORECASE)),
]


class JobNormalizer:
    """Normalizes raw job posting fields into structured, comparable data."""

    @staticmethod
    def normalize_title(title: str) -> str:
        """Normalize a raw job title into a canonical form.

        Examples:
            "Sr. Full Stack Eng. (m/f/x)" -> "Senior Full Stack Engineer"
            "Jr. React Dev." -> "Junior React Developer"
        """
        normalized = title.strip()
        for pattern, replacement in TITLE_REPLACEMENTS:
            normalized = re.sub(pattern, replacement, normalized).strip()
        # Collapse multiple whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()
        # Remove trailing punctuation (but keep periods in abbreviations)
        normalized = normalized.rstrip(".,;:")
        return normalized

    @staticmethod
    def extract_salary(text: str) -> dict[str, object]:
        """Parse salary information from free-text description.

        Returns a dict with keys: salary_min, salary_max, salary_currency.
        Returns None-values if nothing found.
        """
        result: dict[str, object] = {
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
        }

        for pattern in SALARY_PATTERNS:
            match = pattern.search(text)
            if match:
                groups = match.groupdict()
                currency = (groups.get("currency") or "").strip() or "EUR"
                currency_map = {"€": "EUR", "$": "USD", "£": "GBP", "CHF": "CHF"}
                currency = currency_map.get(currency, currency)

                raw_min = groups.get("min", "").replace(".", "").replace(",", ".").upper().rstrip("K")
                raw_max = groups.get("max", "").replace(".", "").replace(",", ".").upper().rstrip("K")

                try:
                    min_val = float(raw_min)
                    max_val = float(raw_max) if raw_max else None
                except ValueError:
                    continue

                if groups.get("min", "").rstrip("Kk").isnumeric() and "k" in groups.get("min", "").lower():
                    min_val *= 1000
                    if max_val:
                        max_val *= 1000

                result = {
                    "salary_min": min_val,
                    "salary_max": max_val if max_val and max_val > min_val else min_val,
                    "salary_currency": currency,
                }
                break

        return result

    @staticmethod
    def extract_skills(description: str) -> list[str]:
        """Detect known skills from a job description.

        Returns a deduplicated, sorted list of detected skill keywords.
        """
        if not description:
            return []

        text_lower = description.lower()
        found: set[str] = set()

        for skill in KNOWN_SKILLS:
            escaped = re.escape(skill)
            if re.search(r"\b" + escaped + r"\b", text_lower):
                found.add(skill)

        return sorted(found)

    @staticmethod
    def classify_employment_type(text: str) -> str:
        """Classify the employment type from a job posting text.

        Returns one of: "full-time", "part-time", "contract", "freelance",
        "internship", "temporary", or "unknown".
        """
        if not text:
            return "unknown"

        text_lower = text.lower()
        scores: dict[str, int] = {}

        for etype, pattern in EMPLOYMENT_TYPE_PATTERNS:
            matches = pattern.findall(text_lower)
            if matches:
                scores[etype] = len(matches)

        if not scores:
            return "unknown"

        return max(scores, key=scores.get)  # type: ignore[arg-type]
