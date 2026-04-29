"""Test scoring for specific jobs to validate fixes"""
import sqlite3
import yaml
from scraper.scorer import JobScorer

# Load config
with open("config.yaml") as f:
    config = yaml.safe_load(f)

scorer = JobScorer(config)

# Connect to DB
conn = sqlite3.connect("db/jobs.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get test jobs
test_job_ids = [
    14047,  # Deutsche Telekom - DevOps Engineer for Industrial AI Cloud (Košice)
    14048,  # Deutsche Telekom - Senior DevOps Engineer for Industrial AI Cloud (Košice)
    14059,  # MARKÍZA - Data Scientist pre Voyo (Bratislava)
    14056,  # Caterpillar - Senior Site Reliability Engineer (Košice)
    14057,  # Caterpillar - Lead Data Support Engineer (Košice)
    13950,  # Solar Turbines - Data Scientist (Košice)
    13959,  # Deutsche Telekom - AI Automation Engineer (Bratislava)
]

print("=" * 80)
print("CURRENT SCORING TEST")
print("=" * 80)

for job_id in test_job_ids:
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()

    if not row:
        continue

    job = dict(row)
    result = scorer.score(job)

    print(f"\nID: {job['id']}")
    print(f"Title: {job['title']}")
    print(f"Company: {job['company']}")
    print(f"Location: {job['location']}")
    print(f"SCORE: {result['score']:.3f} ({result['decision']})")
    print(f"Breakdown: keyword={result['breakdown']['keyword']:.2f}, "
          f"company={result['breakdown']['company']:.2f}, "
          f"location={result['breakdown']['location']:.2f}, "
          f"salary={result['breakdown']['salary']:.2f}, "
          f"recency={result['breakdown']['recency']:.2f}")
    print(f"Reasons: {'; '.join(result['reasons'])}")

conn.close()
