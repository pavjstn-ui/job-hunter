"""
Jobs.cz Scraper
Czech Republic's major job board.
"""

import asyncio
from typing import List, Dict
import httpx
from bs4 import BeautifulSoup
from .base import BaseScraper


class JobsCzScraper(BaseScraper):
    """Scraper for jobs.cz - Czech Republic"""
    
    source_name = "jobscz"
    base_url = "https://www.jobs.cz"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,cs;q=0.8"
        }
    
    async def search(self, keyword: str, location: str = None) -> List[Dict]:
        """Search jobs.cz for jobs"""
        jobs = []
        
        # Build search URL
        params = {
            "q[]": keyword,
            "locality[]": location or "praha"  # Default to Prague
        }
        
        search_url = f"{self.base_url}/prace/"
        
        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            try:
                response = await client.get(search_url, params=params)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, "lxml")
                
                # jobs.cz uses article elements for listings
                job_listings = soup.select("article.SearchResultCard")
                
                for listing in job_listings[:20]:
                    job = self._parse_listing(listing)
                    if job:
                        jobs.append(self.normalize_job(job))
                
            except Exception as e:
                print(f"Error searching jobs.cz: {e}")
        
        return jobs
    
    def _parse_listing(self, listing) -> Dict:
        """Parse a single job listing"""
        try:
            # Title and URL
            title_elem = listing.select_one("a[data-link='jd-title']")
            if not title_elem:
                title_elem = listing.select_one("h2 a")
            
            if not title_elem:
                return None
            
            title = title_elem.get_text(strip=True)
            url = title_elem.get("href", "")
            if url and not url.startswith("http"):
                url = self.base_url + url
            
            # Company
            company_elem = listing.select_one("span[data-test='company-name']")
            if not company_elem:
                company_elem = listing.select_one(".SearchResultCard__company")
            company = company_elem.get_text(strip=True) if company_elem else ""
            
            # Location
            location_elem = listing.select_one("span[data-test='location']")
            if not location_elem:
                location_elem = listing.select_one(".SearchResultCard__location")
            location = location_elem.get_text(strip=True) if location_elem else ""
            
            # Salary
            salary_elem = listing.select_one("span[data-test='salary']")
            if not salary_elem:
                salary_elem = listing.select_one(".SearchResultCard__salary")
            salary_text = salary_elem.get_text(strip=True) if salary_elem else ""
            salary = self.parse_salary(salary_text)
            
            # Description snippet
            desc_elem = listing.select_one(".SearchResultCard__description")
            description = desc_elem.get_text(strip=True) if desc_elem else ""
            
            return {
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "description": description,
                "salary_min": salary["min"],
                "salary_max": salary["max"],
                "currency": salary["currency"]
            }
            
        except Exception as e:
            print(f"Error parsing listing: {e}")
            return None
    
    async def get_job_details(self, job_url: str) -> Dict:
        """Get full job details"""
        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            try:
                response = await client.get(job_url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, "lxml")
                
                # Main content
                content_elem = soup.select_one("div[data-test='job-detail-content']")
                if not content_elem:
                    content_elem = soup.select_one(".JobDetail__content")
                
                description = content_elem.get_text(strip=True) if content_elem else ""
                
                # Requirements
                req_elem = soup.select_one("div[data-test='requirements']")
                requirements = req_elem.get_text(strip=True) if req_elem else ""
                
                return {
                    "url": job_url,
                    "description": description,
                    "requirements": requirements
                }
                
            except Exception as e:
                print(f"Error fetching job details: {e}")
                return {"url": job_url}


# Test
if __name__ == "__main__":
    async def test():
        scraper = JobsCzScraper()
        jobs = await scraper.search("AI engineer", "Praha")
        print(f"Found {len(jobs)} jobs")
        for job in jobs[:3]:
            print(f"  - {job['title']} @ {job['company']}")
    
    asyncio.run(test())
