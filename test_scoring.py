import asyncio
import yaml
from scraper.scorer import JobScorer
from scraper.profesia import ProfesiaScraper
from scraper.jobscz import JobsCzScraper
from scraper.karriere import KarriereScraper

# Load config
with open("config.yaml") as f:
    config = yaml.safe_load(f)

scorer = JobScorer(config)

# Test with provided job titles
test_jobs = [
    {
        "title": "AI Engineer",
        "company": "Test Company",
        "location": "Bratislava, Slovakia",
        "description": "Looking for AI Engineer with Python, ML experience...",
        "salary_min": 50000,
        "salary_max": 70000,
        "currency": "EUR"
    },
    {
        "title": "DevOps Engineer - Platform Team",
        "company": "Test Company",
        "location": "Prague, Czech Republic",
        "description": "DevOps Engineer needed for platform engineering...",
        "salary_min": 40000,
        "salary_max": 60000,
        "currency": "EUR"
    },
    {
        "title": "Senior Machine Learning Engineer",
        "company": "Test Company",
        "location": "Vienna, Austria",
        "description": "ML Engineer with deep learning and data science background...",
        "salary_min": 60000,
        "salary_max": 80000,
        "currency": "EUR"
    }
]

print("=== Testing Job Titles ===")
for job in test_jobs:
    result = scorer.score(job)
    print(f"Title: {job['title']}")
    print(f"Score: {result['score']:.0%}")
    print(f"Decision: {result['decision']}")
    print(f"Breakdown: {result['breakdown']}")
    print(f"Reasons: {result['reasons']}")
    print("-" * 50)

# Test with real job URLs (simulated)
print("\n=== Testing Real Job URLs ===")

# Simulate job data from the provided URLs
allianz_job = {
    "title": "Business Analytik/čka se zaměřením na vývoj AI",
    "company": "Allianz",
    "location": "Praha, Česká republika",
    "description": "Hlavní zaměření na oblast rozvoje řešení s využitím umělé inteligence v péči o klienta...",
    "salary_min": 40000,
    "salary_max": 60000,
    "currency": "EUR"
}

swiss_re_job = {
    "title": "AI Engineer",
    "company": "Swiss Re",
    "location": "Bratislava, Slovakia",
    "description": "We are part of Swiss Re's P&C Digital & Technology Re organization and are looking for an enthusiastic AI Engineer...",
    "salary_min": 2400,
    "salary_max": 4100,
    "currency": "EUR"
}

print("Allianz Job (Business Analytik se zaměřením na vývoj AI):")
result = scorer.score(allianz_job)
print(f"Score: {result['score']:.0%}")
print(f"Decision: {result['decision']}")
print(f"Breakdown: {result['breakdown']}")
print(f"Reasons: {result['reasons']}")
print("-" * 50)

print("Swiss Re Job (AI Engineer):")
result = scorer.score(swiss_re_job)
print(f"Score: {result['score']:.0%}")
print(f"Decision: {result['decision']}")
print(f"Breakdown: {result['breakdown']}")
print(f"Reasons: {result['reasons']}")
