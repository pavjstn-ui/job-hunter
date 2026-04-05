"""
Job Hunter Agent - Main Loop
Orchestrates: scraping → scoring → cover letter → approval → application
"""

import os
import asyncio
import yaml
from datetime import datetime
from typing import Dict, List
from pathlib import Path
from dotenv import load_dotenv

# Local imports
from db.schema import JobDB, JobStatus
from rag.vectorstore import JobVectorStore
from rag.ingest import ingest_cv
from generator.cover_letter import create_generator
from tracking.mlflow_logger import ApplicationTracker
from scraper.profesia import ProfesiaScraper
from scraper.jobscz import JobsCzScraper
from scraper.karriere import KarriereScraper
from scraper.scorer import JobScorer, filter_jobs
from bot.telegram import ApprovalBot

load_dotenv()


class JobHunterAgent:
    """
    Main agent coordinating all job hunting operations.
    
    Flow:
    1. Scrape job boards periodically
    2. Score and filter jobs
    3. Generate cover letters via RAG
    4. Send to Telegram for approval
    5. Apply on approval
    6. Log everything to MLflow
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        # Load config
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        
        # Initialize components
        self.db = JobDB()
        self.vectorstore = JobVectorStore()
        self.generator = create_generator(vectorstore=self.vectorstore)
        self.tracker = ApplicationTracker()
        self.scorer = JobScorer(self.config)
        
        # Initialize scrapers
        self.scrapers = {
            "profesia": ProfesiaScraper(self.config),
            "jobscz": JobsCzScraper(self.config),
            "karriere": KarriereScraper(self.config)
        }
        
        # Initialize Telegram bot
        self.bot = ApprovalBot(
            on_approve=self._on_approve,
            on_reject=self._on_reject
        )
        
        # State
        self.running = False
        self.dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
        
        print("Job Hunter Agent initialized")
        print(f"  LLM Provider: {self.generator.provider}")
        print(f"  Dry run: {self.dry_run}")
    
    async def setup(self):
        """Initial setup - ingest CV, start bot"""
        # Ingest CV if exists
        cv_path = Path("cv/cv_base.pdf")
        if cv_path.exists():
            print("Ingesting CV...")
            ingest_cv(str(cv_path), self.vectorstore)
        else:
            print(f"Warning: CV not found at {cv_path}")
            print("Place your CV there for RAG-based cover letters")
        
        # Start Telegram bot
        await self.bot.start_async()
        await self.bot.send_notification("🚀 Job Hunter Agent started!")
    
    async def run(self):
        """Main agent loop"""
        self.running = True
        
        # Setup
        await self.setup()
        
        # Get schedule config
        schedule = self.config.get("scrape_schedule", {})
        interval = schedule.get("interval_minutes", 60) * 60  # Convert to seconds
        
        print(f"Starting main loop (interval: {interval//60} minutes)")
        
        while self.running:
            try:
                await self._run_cycle()
            except Exception as e:
                print(f"Error in cycle: {e}")
                await self.bot.send_notification(f"⚠️ Error: {str(e)[:200]}")
            
            # Wait for next cycle
            await asyncio.sleep(interval)
    
    async def _run_cycle(self):
        """Single scrape → score → generate → approve cycle"""
        print(f"\n{'='*60}")
        print(f"Starting cycle at {datetime.now().isoformat()}")
        print(f"{'='*60}")
        
        # 1. Scrape all sources
        all_jobs = await self._scrape_all()
        print(f"Scraped {len(all_jobs)} total jobs")
        
        if not all_jobs:
            return
        
        # 2. Filter out already-seen jobs
        new_jobs = self._filter_seen(all_jobs)
        print(f"New jobs: {len(new_jobs)}")
        
        if not new_jobs:
            print("No new jobs found")
            return
        
        # 3. Score and categorize
        categorized = filter_jobs(new_jobs, self.scorer)
        print(f"Auto-apply: {len(categorized['auto_apply'])}")
        print(f"Manual review: {len(categorized['manual_review'])}")
        print(f"Rejected: {len(categorized['reject'])}")
        
        # 4. Process auto-apply candidates
        for job in categorized["auto_apply"][:5]:  # Limit per cycle
            await self._process_job(job, auto=True)
        
        # 5. Send manual review to Telegram
        for job in categorized["manual_review"][:10]:
            await self._process_job(job, auto=False)
        
        # 6. Store rejected for reference
        for job in categorized["reject"]:
            job_id = self.db.add_job(job)
            self.db.update_status(job_id, JobStatus.REJECTED)
    
    async def _scrape_all(self) -> List[Dict]:
        """Scrape all configured sources"""
        all_jobs = []
        keywords = self.config.get("search", {}).get("keywords", {})
        primary_keywords = keywords.get("primary", [])[:3]  # Top 3 keywords
        
        for source, scraper in self.scrapers.items():
            for keyword in primary_keywords:
                try:
                    jobs = await scraper.search(keyword)
                    all_jobs.extend(jobs)
                    print(f"  {source}/{keyword}: {len(jobs)} jobs")
                except Exception as e:
                    print(f"  Error scraping {source}/{keyword}: {e}")
                
                await asyncio.sleep(2)  # Rate limiting
        
        return all_jobs
    
    def _filter_seen(self, jobs: List[Dict]) -> List[Dict]:
        """Filter out jobs we've already seen"""
        new_jobs = []
        
        for job in jobs:
            existing = self.db.get_job_by_external_id(job.get("external_id"))
            if not existing:
                new_jobs.append(job)
        
        return new_jobs
    
    async def _process_job(self, job: Dict, auto: bool = False):
        """Process a single job: save, generate cover letter, queue for approval"""
        # Save to DB
        job_id = self.db.add_job(job)
        job["id"] = job_id
        
        # Get full job details if available
        scraper = self.scrapers.get(job.get("source"))
        if scraper and job.get("url"):
            try:
                details = await scraper.get_job_details(job["url"])
                job.update(details)
            except:
                pass
        
        # Generate cover letter
        print(f"Generating cover letter for: {job['title']} @ {job['company']}")
        result = self.generator.generate_from_job(job)
        job["cover_letter"] = result["cover_letter"]
        
        # Save cover letter
        self.db.set_cover_letter(job_id, result["cover_letter"])
        
        if auto and not self.dry_run:
            # Auto-apply (if we had apply functionality)
            self.db.update_status(job_id, JobStatus.APPROVED)
            await self.bot.send_notification(
                f"🤖 Auto-approved: *{job['title']}* @ {job['company']}\n"
                f"Score: {job['score']:.0%}"
            )
        else:
            # Send to Telegram for approval
            self.db.update_status(job_id, JobStatus.PENDING_APPROVAL)
            await self.bot.request_approval(job)
    
    async def _on_approve(self, job_id: int, job: Dict):
        """Handle approval from Telegram"""
        print(f"Approved: {job['title']} @ {job['company']}")
        
        self.db.update_status(job_id, JobStatus.APPROVED)
        
        # Log to MLflow
        run_id = self.tracker.log_application(
            job_id=job_id,
            job_title=job.get("title", ""),
            company=job.get("company", ""),
            source=job.get("source", ""),
            score=job.get("score", 0),
            score_breakdown=job.get("score_breakdown", {}),
            cover_letter=job.get("cover_letter", ""),
            cover_letter_version=1,
            status="approved",
            location=job.get("location", ""),
            salary_min=job.get("salary_min"),
            salary_max=job.get("salary_max"),
            llm_provider=self.generator.provider
        )
        
        print(f"Logged to MLflow: {run_id}")
        
        # TODO: Actual application submission
        # For now, just mark as needing manual application
        await self.bot.send_notification(
            f"✅ Ready to apply: {job['title']} @ {job['company']}\n"
            f"📝 Cover letter saved. Apply manually at:\n{job.get('url', 'No URL')}"
        )
    
    async def _on_reject(self, job_id: int, job: Dict):
        """Handle rejection from Telegram"""
        print(f"Rejected: {job['title']} @ {job['company']}")
        self.db.update_status(job_id, JobStatus.REJECTED, notes="Rejected via Telegram")
    
    async def stop(self):
        """Stop the agent"""
        self.running = False
        await self.bot.stop_async()
        print("Agent stopped")


async def main():
    """Entry point"""
    agent = JobHunterAgent()
    
    try:
        await agent.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
