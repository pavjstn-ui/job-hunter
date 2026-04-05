"""
Karriere.at Scraper
Austria's major job board.
"""

import asyncio
from typing import List, Dict
import httpx
from bs4 import BeautifulSoup
from .base import BaseScraper


class KarriereScraper(BaseScraper):
    """Scraper for karriere.at - Austria"""
    
    source_name = "karriere"
    base_url = "https://www.karriere.at"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,de;q=0.8"
        }
    
    async def search(self, keyword: str, location: str = None) -> List[Dict]:
        """Search karriere.at for jobs"""
        jobs = []
        
        # Build search URL
        search_url = f"{self.base_url}/jobs"
        params = {
            "keywords": keyword
        }
        
        if location:
            params["location"] = location
        
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            try:
                response = await client.get(search_url, params=params)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, "lxml")
                
                # karriere.at job listings
                job_listings = soup.select("article.m-jobItem")
                if not job_listings:
                    job_listings = soup.select("div.m-jobsListItem")
                
                for listing in job_listings[:20]:
                    job = self._parse_listing(listing)
                    if job:
                        jobs.append(self.normalize_job(job))
                
            except Exception as e:
                print(f"Error searching karriere.at: {e}")
        
        return jobs
    
    def _parse_listing(self, listing) -> Dict:
        """Parse a single job listing"""
        try:
            # Title and URL
            title_elem = listing.select_one("a.m-jobItem__titleLink")
            if not title_elem:
                title_elem = listing.select_one("h2 a")
            
            if not title_elem:
                return None
            
            title = title_elem.get_text(strip=True)
            url = title_elem.get("href", "")
            if url and not url.startswith("http"):
                url = self.base_url + url
            
            # Company
            company_elem = listing.select_one("span.m-jobItem__company")
            if not company_elem:
                company_elem = listing.select_one(".m-jobsListItem__company")
            company = company_elem.get_text(strip=True) if company_elem else ""
            
            # Location
            location_elem = listing.select_one("span.m-jobItem__location")
            if not location_elem:
                location_elem = listing.select_one(".m-jobsListItem__location")
            location = location_elem.get_text(strip=True) if location_elem else ""
            
            # Salary (karriere.at often shows salary)
            salary_elem = listing.select_one("span.m-jobItem__salary")
            salary_text = salary_elem.get_text(strip=True) if salary_elem else ""
            salary = self.parse_salary(salary_text)
            
            return {
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "description": "",  # Get from details page
                "salary_min": salary["min"],
                "salary_max": salary["max"],
                "currency": salary["currency"]
            }
            
        except Exception as e:
            print(f"Error parsing listing: {e}")
            return None
    
    async def get_job_details(self, job_url: str) -> Dict:
        """Get full job details"""
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            try:
                response = await client.get(job_url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, "lxml")
                
                # Job description
                desc_elem = soup.select_one("div.m-jobContent__description")
                if not desc_elem:
                    desc_elem = soup.select_one("div[itemprop='description']")
                description = desc_elem.get_text(strip=True) if desc_elem else ""
                
                # Requirements/qualifications
                req_elem = soup.select_one("div.m-jobContent__requirements")
                requirements = req_elem.get_text(strip=True) if req_elem else ""
                
                # Benefits
                benefits_elem = soup.select_one("div.m-jobContent__benefits")
                benefits = benefits_elem.get_text(strip=True) if benefits_elem else ""
                
                return {
                    "url": job_url,
                    "description": description,
                    "requirements": requirements,
                    "benefits": benefits
                }
                
            except Exception as e:
                print(f"Error fetching job details: {e}")
                return {"url": job_url}


# Test
if __name__ == "__main__":
    async def test():
        scraper = KarriereScraper()
        jobs = await scraper.search("AI engineer", "Wien")
        print(f"Found {len(jobs)} jobs")
        for job in jobs[:3]:
            print(f"  - {job['title']} @ {job['company']}")
    
    asyncio.run(test())
