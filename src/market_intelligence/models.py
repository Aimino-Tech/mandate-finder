from datetime import date, datetime
from enum import Enum
from pydantic import BaseModel, Field


class Industry(str, Enum):
    health = "health"
    finance = "finance"
    technology = "technology"
    manufacturing = "manufacturing"
    retail = "retail"
    education = "education"
    construction = "construction"
    logistics = "logistics"
    energy = "energy"
    media = "media"
    other = "other"


class RoleCategory(str, Enum):
    engineering = "engineering"
    sales = "sales"
    marketing = "marketing"
    finance = "finance"
    hr = "hr"
    operations = "operations"
    product = "product"
    design = "design"
    data = "data"
    management = "management"
    other = "other"


class JobPosting(BaseModel):
    id: str
    title: str
    company: str
    industry: Industry | None = None
    role_category: RoleCategory | None = None
    location: str | None = None
    skills: list[str] = Field(default_factory=list)
    posted_at: datetime
    source: str | None = None


class TrendPoint(BaseModel):
    date: date
    value: float
    moving_avg: float | None = None
    seasonal: float | None = None
    residual: float | None = None


class TrendSeries(BaseModel):
    category: str
    points: list[TrendPoint]
    growth_rate: float
    direction: str


class EarlySignal(BaseModel):
    signal_type: str
    company: str
    industry: Industry | None = None
    headline: str
    source_url: str
    detected_at: datetime
    confidence: float = Field(ge=0, le=1)
    predicted_hiring_window_days: int | None = None


class TrendReport(BaseModel):
    generated_at: datetime
    top_growing_roles: list[TrendSeries]
    industry_pulse: list[TrendSeries]
    early_warnings: list[EarlySignal]
    user_insights: list[str] = Field(default_factory=list)
