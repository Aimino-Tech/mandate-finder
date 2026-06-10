"""Seed demo data into the market-intelligence API for testing/evaluation."""
import argparse
import random
import sys
from datetime import datetime, timedelta

import httpx

BASE = "http://127.0.0.1:8000/api/market-intelligence"

ROLES = ["engineering", "sales", "marketing", "data", "design", "product", "hr", "finance", "operations", "management"]
INDUSTRIES = ["technology", "health", "finance", "manufacturing", "retail", "logistics", "energy", "education", "media", "construction"]
COMPANIES = [
    "TechFlow", "DataPulse", "CloudNine", "GreenEnergy", "MediCore",
    "FinLeap", "BuildRight", "EduSpark", "LogiStar", "RetailNext",
]
LOCATIONS = ["Berlin", "Munich", "Hamburg", "Cologne", "Frankfurt", "Stuttgart", "Düsseldorf", "Leipzig", "Dresden", "Nuremberg"]


def generate_postings(count: int, days: int) -> list[dict]:
    now = datetime.now()
    return [
        {
            "id": f"demo-{i}",
            "title": f"{random.choice(['Senior', 'Junior', 'Principal', 'Lead', ''])} {random.choice(ROLES).title()} {random.choice(['Engineer', 'Specialist', 'Manager', 'Associate', 'Consultant'])}",
            "company": random.choice(COMPANIES),
            "industry": random.choice(INDUSTRIES),
            "role_category": random.choice(ROLES),
            "location": random.choice(LOCATIONS),
            "skills": random.sample(["python", "sql", "aws", "kubernetes", "react", "go", "rust", "typescript", "docker", "terraform"], k=random.randint(1, 4)),
            "posted_at": (now - timedelta(days=random.randint(0, days))).isoformat(),
            "source": "demo",
        }
        for i in range(count)
    ]


def generate_signals() -> list[dict]:
    return [
        {"signal_type": "funding", "company": "TechFlow", "industry": "technology", "headline": "TechFlow raises $50M Series C for AI expansion", "source_url": "https://example.com/tf", "detected_at": datetime.now().isoformat(), "confidence": 0.9, "predicted_hiring_window_days": 30},
        {"signal_type": "funding", "company": "MediCore", "industry": "health", "headline": "MediCore closes $12M Series A for digital health platform", "source_url": "https://example.com/mc", "detected_at": datetime.now().isoformat(), "confidence": 0.8, "predicted_hiring_window_days": 60},
        {"signal_type": "new_office", "company": "CloudNine", "industry": "technology", "headline": "CloudNine opens new engineering office in Berlin", "source_url": "https://example.com/c9", "detected_at": datetime.now().isoformat(), "confidence": 0.7, "predicted_hiring_window_days": 30},
        {"signal_type": "leadership_change", "company": "FinLeap", "industry": "finance", "headline": "FinLeap appoints new CTO from Stripe", "source_url": "https://example.com/fl", "detected_at": datetime.now().isoformat(), "confidence": 0.65, "predicted_hiring_window_days": None},
    ]


def main():
    parser = argparse.ArgumentParser(description="Seed demo data into market-intelligence API")
    parser.add_argument("--postings", type=int, default=500, help="Number of demo job postings")
    parser.add_argument("--days", type=int, default=90, help="Days of history to cover")
    parser.add_argument("--base", default=BASE, help="API base URL")
    args = parser.parse_args()

    with httpx.Client() as client:
        print(f"Seeding {args.postings} job postings ({args.days} day history)...")
        postings = generate_postings(args.postings, args.days)
        r = client.post(f"{args.base}/postings", json=postings)
        r.raise_for_status()
        print(f"  Response: {r.json()}")

        print("Seeding early signals...")
        signals = generate_signals()
        r = client.post(f"{args.base}/signals", json=signals)
        r.raise_for_status()
        print(f"  Response: {r.json()}")

        print("Fetching trend report...")
        r = client.get(f"{args.base}/trends?days={args.days}")
        r.raise_for_status()
        data = r.json()
        print(f"  Top roles: {len(data.get('top_growing_roles', []))}")
        print(f"  Industries: {len(data.get('industry_pulse', []))}")
        print(f"  Early warnings: {len(data.get('early_warnings', []))}")
        print("\nDemo data seeded successfully. Open http://127.0.0.1:8000/ for the dashboard.")


if __name__ == "__main__":
    main()
