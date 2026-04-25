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
from scraper.linkedin_scraper import LinkedInScraper
from scraper.scorer import JobScorer, filter_jobs
from bot.telegram import ApprovalBot
from playwright_applier import JobsCzApplier

# Import new scrapers
from scraper.startupjobs_scraper import StartupJobsScraper
from scraper.remoteok_scraper import RemoteOkScraper

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
            "karriere": KarriereScraper(self.config),
            "linkedin": LinkedInScraper(self.config),
            "startupjobs": StartupJobsScraper(self.config),
            "remoteok": RemoteOkScraper(self.config)
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
            print("No new jobs found from scrapers")
            # Continue to LinkedIn feed processing
        else:
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

        # 7. Process LinkedIn URLs from email feed
        print("\n" + "="*60)
        print("ABOUT TO PROCESS LINKEDIN FEED")
        print("="*60)
        await self._process_linkedin_feed()
    
    async def _scrape_all(self) -> List[Dict]:
        """Scrape all configured sources"""
        all_jobs = []
        keywords = self.config.get("search", {}).get("keywords", {})
        primary_keywords = keywords.get("primary", [])[:3]  # Top 3 keywords
        
        for source, scraper in self.scrapers.items():
            # Skip the "all" source which is handled differently
            if source == "all":
                continue
                
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
    
    async def _process_linkedin_feed(self):
        """Process LinkedIn job URLs from /tmp/linkedin_jobs.txt"""
        print("\n" + "="*60)
        print("INSIDE _process_linkedin_feed() - METHOD STARTED")
        print("="*60)
        
        feed_file = "/tmp/linkedin_jobs.txt"
        if not os.path.exists(feed_file):
            print("No LinkedIn feed file found")
            return

        with open(feed_file, 'r') as f:
            urls = [line.strip() for line in f if line.strip() and line.strip().startswith('http')]

        if not urls:
            print("No LinkedIn URLs found in feed")
            return

        print(f"Found {len(urls)} LinkedIn URLs in feed")

        processed_count = 0
        for url in urls[:20]:  # Limit to 20 per cycle
            try:
                job = await self.scrapers['linkedin'].get_job_details(url)
                score_result = self.scorer.score(job)
                job['score'] = score_result['score']

                if score_result['decision'] == 'manual_review':
                    await self._process_job(job, auto=False)
                    processed_count += 1

            except Exception as e:
                print(f"Error processing {url}: {e}")

        print(f"Processed {processed_count} LinkedIn jobs")

        # Clear feed file
        open(feed_file, 'w').close()

    async def _process_job(self, job: Dict, auto: bool = False):
        """Process a single job: save to DB, queue for approval (NO cover letter yet)"""
        # Check if job already exists in DB (by external_id)
        existing_job = self.db.get_job_by_external_id(job.get("external_id"))

        if existing_job:
            # Job already exists, reuse its data
            job_id = existing_job["id"]
            job["id"] = job_id
            print(f"Job already exists: {job['title']} @ {job['company']}")
        else:
            # New job - save to DB
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

        # ❌ REMOVED: Cover letter generation moved to _on_approve callback
        # Cover letters are now ONLY generated when user approves via Telegram
        
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
        """Handle approval from Telegram - Generate cover letter and log"""
        print(f"Approved: {job['title']} @ {job['company']}")

        self.db.update_status(job_id, JobStatus.APPROVED)

        # ✅ Generate cover letter ONLY on approval
        print(f"Generating cover letter for approved job: {job['title']} @ {job['company']}")
        result = self.generator.generate_from_job(job)
        cover_letter = result["cover_letter"]

        # Save cover letter to DB
        self.db.set_cover_letter(job_id, cover_letter)
        job["cover_letter"] = cover_letter

        # Log to MLflow
        run_id = self.tracker.log_application(
            job_id=job_id,
            job_title=job.get("title", ""),
            company=job.get("company", ""),
            source=job.get("source", ""),
            score=job.get("score", 0),
            score_breakdown=job.get("score_breakdown", {}),
            cover_letter=cover_letter,  # Use freshly generated CL
            cover_letter_version=1,
            status="approved",
            location=job.get("location", ""),
            salary_min=job.get("salary_min"),
            salary_max=job.get("salary_max"),
            llm_provider=self.generator.provider
        )
        
        print(f"Logged to MLflow: {run_id}")

        # Apply to job using Playwright (if not dry run and if it's a jobs.cz posting)
        job_url = job.get('url', '')
        application_result = None

        if self.dry_run:
            # Dry run mode - don't actually apply
            await self.bot.send_notification(
                f"🧪 DRY RUN - Would apply to:\n"
                f"*{job['title']}* @ {job['company']}\n"
                f"📝 Cover letter generated\n"
                f"🔗 {job_url}"
            )
        elif 'jobs.cz' in job_url:
            # Apply automatically using Playwright for jobs.cz
            try:
                print(f"Applying to job via Playwright: {job_url}")
                await self.bot.send_notification(
                    f"🤖 Applying automatically to:\n"
                    f"*{job['title']}* @ {job['company']}\n"
                    f"Please wait..."
                )

                async with JobsCzApplier() as applier:
                    application_result = await applier.apply_to_job(job_url, cover_letter)

                if application_result['success']:
                    # Update status to applied
                    self.db.update_status(job_id, JobStatus.APPLIED)

                    # Log application success to MLflow
                    self.tracker.log_application_result(
                        run_id=run_id,
                        applied=True,
                        result_message=application_result['message']
                    )

                    await self.bot.send_notification(
                        f"✅ Applied successfully!\n"
                        f"*{job['title']}* @ {job['company']}\n"
                        f"📝 {application_result['message']}\n"
                        f"🔗 {job_url}"
                    )
                else:
                    # Application failed
                    error_msg = application_result['message']
                    print(f"Application failed: {error_msg}")

                    # Log failure to MLflow
                    self.tracker.log_application_result(
                        run_id=run_id,
                        applied=False,
                        result_message=f"Failed: {error_msg}"
                    )

                    screenshot_info = ""
                    if application_result.get('screenshot_path'):
                        screenshot_info = f"\n📸 Screenshot: {application_result['screenshot_path']}"

                    await self.bot.send_notification(
                        f"❌ Application failed:\n"
                        f"*{job['title']}* @ {job['company']}\n"
                        f"Error: {error_msg}{screenshot_info}\n"
                        f"Please apply manually at:\n{job_url}"
                    )

            except Exception as e:
                print(f"Error during automatic application: {e}")

                # Log error to MLflow
                self.tracker.log_application_result(
                    run_id=run_id,
                    applied=False,
                    result_message=f"Error: {str(e)}"
                )

                await self.bot.send_notification(
                    f"❌ Error applying automatically:\n"
                    f"*{job['title']}* @ {job['company']}\n"
                    f"Error: {str(e)}\n"
                    f"📝 Cover letter saved. Apply manually at:\n{job_url}"
                )
        else:
            # Not a jobs.cz posting - manual application required
            await self.bot.send_notification(
                f"✅ Ready to apply: *{job['title']}* @ {job['company']}\n"
                f"📝 Cover letter saved. Apply manually at:\n{job_url}\n"
                f"ℹ️ Automatic application only supported for jobs.cz"
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
