import re
from dataclasses import dataclass, field
from typing import Protocol


class AgiNormalizer(Protocol):
    async def normalize_title(self, raw_title: str) -> str: ...
    async def extract_skills(self, description: str) -> list[str]: ...


@dataclass
class NormalizedJob:
    title: str
    company: str
    location: str
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    skills: list[str] = field(default_factory=list)
    employment_type: str | None = None
    description: str = ""


_TITLE_SHORTCUTS: dict[str, str] = {
    "sr": "Senior",
    "jr": "Junior",
    "lead": "Lead",
    "principal": "Principal",
    "staff": "Staff",
    "vp": "Vice President",
    "vice pres": "Vice President",
    "eng": "Engineer",
    "eng.": "Engineer",
    "dept": "Department",
    "mgr": "Manager",
    "admin": "Administrator",
    "asst": "Assistant",
    "assoc": "Associate",
    "coord": "Coordinator",
    "coord.": "Coordinator",
    "dir": "Director",
    "de": "Engineer",
    "développeur": "Developer",
    "entwickler": "Developer",
    "ingenieur": "Engineer",
    "fachinformatiker": "IT Specialist",
}

_CURRENCY = r"(?:€|\$|£|eur|usd|gbp|chf)"
_SALARY_PATTERNS: list[re.Pattern] = [
    re.compile(
        rf"(?P<currency>{_CURRENCY})?\s*"
        r"(?P<min>[\d,.]+)\s*(?:k|K)?\s*"
        r"(?:–|-|to|–)\s*"
        rf"{_CURRENCY}?\s*(?P<max>[\d,.]+)\s*(?:k|K)?\s*"
        r"(?P<period>/hr|/h|/hour|/year|/yr|/annum|p\.?a\.?|per year|annually)?",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<currency>{_CURRENCY})?\s*"
        r"(?:from|up to|bis|ab)?\s*"
        r"(?P<amount>[\d,.]+)\s*(?:k|K)?\s*"
        r"(?P<period>/hr|/h|/hour|/year|/yr|/annum|p\.?a\.?|per year|annually)?",
        re.IGNORECASE,
    ),
]

_EMPLOYMENT_TYPES: dict[str, str] = {
    "full.time": "full_time",
    "fulltime": "full_time",
    "festanstellung": "full_time",
    "part.time": "part_time",
    "parttime": "part_time",
    "teilzeit": "part_time",
    "contract": "contract",
    "freelance": "freelance",
    "freiberuflich": "freelance",
    "temporary": "contract",
    "befristet": "contract",
    "intern": "internship",
    "internship": "internship",
    "praktikum": "internship",
    "werkstudent": "part_time",
    "working student": "part_time",
}

_EMPLOYMENT_PATTERN = re.compile(
    "|".join(re.escape(t) for t in _EMPLOYMENT_TYPES),
    re.IGNORECASE,
)

_GERMAN_TITLE_CLEANUP = re.compile(
    r"\(?(?:m/f/x|m/w/d|m/w/x|w/m/d|m/f|m/w|w/m|diverse|x)\)?", re.IGNORECASE
)


@dataclass
class JobNormalizer:
    agi: AgiNormalizer | None = None

    async def normalize(self, raw_job: dict) -> NormalizedJob:
        title = await self.normalize_title(raw_job.get("title", ""))
        company = raw_job.get("company", "")
        location = raw_job.get("location", "")
        description = raw_job.get("description", "")

        salary = await self._extract_salary(raw_job, description)
        skills = await self.extract_skills(description)
        employment_type = await self._extract_employment_type(raw_job, description)

        return NormalizedJob(
            title=title,
            company=company,
            location=location,
            salary_min=salary.get("min"),
            salary_max=salary.get("max"),
            salary_currency=salary.get("currency"),
            salary_period=salary.get("period"),
            skills=skills,
            employment_type=employment_type,
            description=description,
        )

    async def normalize_title(self, raw_title: str) -> str:
        if not raw_title:
            return ""

        if self.agi is not None:
            return await self.agi.normalize_title(raw_title)

        title = _GERMAN_TITLE_CLEANUP.sub("", raw_title).strip()
        words = title.split()
        cleaned: list[str] = []
        for w in words:
            stripped = w.strip(".,()[]{}")
            lower = stripped.lower()
            cleaned.append(_TITLE_SHORTCUTS.get(lower, stripped))

        result = " ".join(cleaned)
        result = re.sub(r"\s+", " ", result).strip()
        return result

    async def extract_skills(
        self, description: str
    ) -> list[str]:
        if not description:
            return []

        if self.agi is not None:
            return await self.agi.extract_skills(description)

        known_skills: dict[str, str] = {
            "python": "Python",
            "java": "Java",
            "javascript": "JavaScript",
            "typescript": "TypeScript",
            "react": "React",
            "angular": "Angular",
            "vue": "Vue.js",
            "node": "Node.js",
            "node.js": "Node.js",
            "aws": "AWS",
            "azure": "Azure",
            "gcp": "GCP",
            "docker": "Docker",
            "kubernetes": "Kubernetes",
            "sql": "SQL",
            "postgresql": "PostgreSQL",
            "mysql": "MySQL",
            "mongodb": "MongoDB",
            "redis": "Redis",
            "kafka": "Kafka",
            "git": "Git",
            "ci/cd": "CI/CD",
            "terraform": "Terraform",
            "ansible": "Ansible",
            "linux": "Linux",
            "agile": "Agile",
            "scrum": "Scrum",
            "rest": "REST API",
            "graphql": "GraphQL",
            "html": "HTML",
            "css": "CSS",
            "sass": "Sass",
            "tailwind": "Tailwind CSS",
            "next.js": "Next.js",
            "fastapi": "FastAPI",
            "django": "Django",
            "flask": "Flask",
            "spring": "Spring",
            "spring boot": "Spring Boot",
            ".net": ".NET",
            "go": "Go",
            "rust": "Rust",
            "c++": "C++",
            "c#": "C#",
            "jira": "Jira",
            "confluence": "Confluence",
        }

        desc_lower = description.lower()
        found: list[str] = []
        for kw, display in known_skills.items():
            if kw in desc_lower:
                found.append(display)

        seen: set[str] = set()
        deduped: list[str] = []
        for s in found:
            if s not in seen:
                seen.add(s)
                deduped.append(s)

        return deduped

    async def _extract_salary(
        self, raw_job: dict, description: str
    ) -> dict:
        salary_field = raw_job.get("salary", "")
        if isinstance(salary_field, dict):
            return salary_field

        text = f"{salary_field} {description}"
        for pattern in _SALARY_PATTERNS:
            match = pattern.search(text)
            if match:
                result: dict[str, str | int | None] = {}
                currency = match.group("currency")
                if currency:
                    result["currency"] = _normalize_currency(currency)
                else:
                    result["currency"] = None

                if "min" in match.groupdict() and match.group("min"):
                    result["min"] = _parse_salary_amount(match.group("min"))
                else:
                    result["min"] = None

                if "max" in match.groupdict() and match.group("max"):
                    result["max"] = _parse_salary_amount(match.group("max"))
                elif "amount" in match.groupdict() and match.group("amount"):
                    result["max"] = _parse_salary_amount(match.group("amount"))
                else:
                    result["max"] = None

                period = match.group("period")
                result["period"] = _normalize_period(period) if period else None

                return result

        return {"min": None, "max": None, "currency": None, "period": None}

    async def _extract_employment_type(
        self, raw_job: dict, description: str
    ) -> str | None:
        employment = raw_job.get("employment_type", "")
        if employment:
            key = employment.lower().replace(" ", "").replace("-", ".")
            normalized = _EMPLOYMENT_TYPES.get(key)
            if normalized:
                return normalized

        match = _EMPLOYMENT_PATTERN.search(description)
        if match:
            key = match.group(0).lower().replace(" ", "").replace("-", ".")
            normalized = _EMPLOYMENT_TYPES.get(key)
            return normalized

        return None


def _normalize_currency(raw: str) -> str:
    raw = raw.strip().lower()
    table: dict[str, str] = {
        "€": "EUR",
        "$": "USD",
        "£": "GBP",
        "eur": "EUR",
        "usd": "USD",
        "gbp": "GBP",
        "chf": "CHF",
    }
    return table.get(raw, raw.upper())


def _normalize_period(raw: str) -> str:
    raw = raw.strip().lower().replace(".", "")
    table: dict[str, str] = {
        "hr": "hour",
        "h": "hour",
        "hour": "hour",
        "year": "year",
        "yr": "year",
        "annum": "year",
        "pa": "year",
        "per year": "year",
        "annually": "year",
    }
    return table.get(raw, "year")


def _parse_salary_amount(raw: str) -> int:
    cleaned = raw.replace(",", ".").replace(" ", "")
    if "." in cleaned:
        parts = cleaned.split(".")
        if len(parts) == 2 and len(parts[1]) > 2:
            cleaned = parts[0]
    amount = int(float(cleaned))
    return amount * 1000 if amount < 1000 else amount
