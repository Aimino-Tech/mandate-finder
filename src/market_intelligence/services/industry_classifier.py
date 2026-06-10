from market_intelligence.models import Industry, JobPosting, RoleCategory

_INDUSTRY_KEYWORDS: dict[Industry, set[str]] = {
    Industry.health: {"krankenhaus", "klinik", "arzt", "pflege", "gesundheit", "pharma", "hospital", "health", "medical", "nurse", "doctor"},
    Industry.finance: {"bank", "versicherung", "finanz", "investment", "audit", "steuer", "insurance", "finance", "banking"},
    Industry.technology: {"software", "it-", "entwickler", "devops", "data", "cloud", "ai", "machine learning", "cyber", "engineering", "developer", "tech"},
    Industry.manufacturing: {"produktion", "fertigung", "maschinenbau", "industrie", "manufacturing", "production", "plant"},
    Industry.retail: {"einzelhandel", "verkauf", "retail", "e-commerce", "handel", "store"},
    Industry.education: {"schule", "universität", "bildung", "lehre", "pädagogik", "education", "teaching", "university"},
    Industry.construction: {"bau", "architektur", "immobilien", "construction", "real estate", "building"},
    Industry.logistics: {"logistik", "transport", "lieferkette", "supply chain", "warehouse", "lager"},
    Industry.energy: {"energie", "strom", "gas", "erneuerbar", "solar", "wind", "energy", "renewable"},
    Industry.media: {"medien", "verlag", "werbung", "journalismus", "media", "publishing", "marketing"},
}

_ROLE_KEYWORDS: dict[RoleCategory, set[str]] = {
    RoleCategory.engineering: {"engineer", "entwickler", "software", "devops", "backend", "frontend", "fullstack", "architect", "sre", "infrastructure"},
    RoleCategory.sales: {"sales", "vertrieb", "account executive", "business development", "key account"},
    RoleCategory.marketing: {"marketing", "growth", "seo", "content", "social media", "brand", "campaign"},
    RoleCategory.finance: {"controller", "accountant", "finanz", "buchhaltung", "finance", "tax", "audit"},
    RoleCategory.hr: {"hr", "personal", "recruiter", "talent", "people", "human resources"},
    RoleCategory.operations: {"operations", "betrieb", "project manager", "projektmanager", "coordinator", "koordinator"},
    RoleCategory.product: {"product manager", "produktmanager", "product owner", "po", "product"},
    RoleCategory.design: {"designer", "ux", "ui", "product design", "visual", "graphic"},
    RoleCategory.data: {"data scientist", "data engineer", "data analyst", "machine learning", "ml", "analytics", "bi"},
    RoleCategory.management: {"manager", "director", "head of", "vp ", "chief", "ceo", "cto", "cfo", "lead"},
}


def classify_job_posting(posting: JobPosting) -> JobPosting:
    tl = posting.title.lower()
    cl = posting.company.lower()
    for ind, kw in _INDUSTRY_KEYWORDS.items():
        if any(k in tl or k in cl for k in kw):
            posting.industry = ind
            break
    if posting.industry is None:
        combined = " ".join(s.lower() for s in posting.skills)
        for ind, kw in _INDUSTRY_KEYWORDS.items():
            if any(k in combined for k in kw):
                posting.industry = ind
                break
    if posting.industry is None:
        posting.industry = Industry.other
    for rol, kw in _ROLE_KEYWORDS.items():
        if any(k in tl for k in kw):
            posting.role_category = rol
            break
    if posting.role_category is None and posting.skills:
        cs = " ".join(s.lower() for s in posting.skills)
        for rol, kw in _ROLE_KEYWORDS.items():
            if any(k in cs for k in kw):
                posting.role_category = rol
                break
    if posting.role_category is None:
        posting.role_category = RoleCategory.other
    return posting


def classify_batch(postings: list[JobPosting]) -> list[JobPosting]:
    return [classify_job_posting(p) for p in postings]
