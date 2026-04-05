"""
Profesia.sk Scraper
Slovakia's largest job board.
"""

import asyncio
from typing import List, Dict
import httpx
from bs4 import BeautifulSoup
from .base import BaseScraper


class ProfesiaScraper(BaseScraper):
    """Scraper for profesia.sk - Slovakia"""
    
    source_name = "profesia"
    base_url = "https://www.profesia.sk"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,sk;q=0.8"
        }
    
    async def search(self, keyword: str, location: str = None) -> List[Dict]:
        """Search profesia.sk for jobs"""
        jobs = []
        
        # Build search URL
        # profesia.sk format: /praca/ai-engineer/
        search_term = keyword.lower().replace(" ", "-")
        search_url = f"{self.base_url}/praca/?search_anywhere={keyword}"
        
        if location:
            location_slug = location.lower().replace(" ", "-")
            search_url = f"{self.base_url}/praca/?search_anywhere={keyword}&region={location}"
        
        async with httpx.AsyncClient(headers=self.headers, follow_redirects=True, timeout=30) as client:
            try:
                response = await client.get(search_url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, "lxml")
                job_listings = soup.select("li.list-row")
                
                for listing in job_listings[:20]:  # Limit to 20 per search
                    job = self._parse_listing(listing)
                    if job:
                        jobs.append(self.normalize_job(job))
                
            except Exception as e:
                print(f"Error searching profesia.sk: {e}")
        
        return jobs
    
    def _parse_listing(self, listing) -> Dict:
        """Parse a single job listing from search results"""
        try:
            # Title and URL
            title_elem = listing.select_one("h2 a")
            if not title_elem:
                return None
            
            title = title_elem.get_text(strip=True)
            url = title_elem.get("href", "")
            if url and not url.startswith("http"):
                url = self.base_url + url
            
            # Company
            company_elem = listing.select_one("span.employer")
            company = company_elem.get_text(strip=True) if company_elem else ""
            
            # Location
            location_elem = listing.select_one("span.job-location")
            location = location_elem.get_text(strip=True) if location_elem else ""
            
            # Salary (if shown)
            salary_elem = listing.select_one("span.label-salary")
            salary_text = salary_elem.get_text(strip=True) if salary_elem else ""
            salary = self.parse_salary(salary_text)
            
            # Short description
            desc_elem = listing.select_one("div.description")
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
        """Get full job details from job page"""
        async with httpx.AsyncClient(headers=self.headers, follow_redirects=True, timeout=30) as client:
            try:
                response = await client.get(job_url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, "lxml")
                
                # Full description
                desc_elem = soup.select_one("div.job-description")
                description = desc_elem.get_text(strip=True) if desc_elem else ""
                
                # Requirements section
                req_elem = soup.select_one("div.job-requirements")
                requirements = req_elem.get_text(strip=True) if req_elem else ""
                
                # Benefits
                benefits_elem = soup.select_one("div.job-benefits")
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
        scraper = ProfesiaScraper()
        jobs = await scraper.search("AI engineer", "Bratislava")
        print(f"Found {len(jobs)} jobs")
        for job in jobs[:3]:
            print(f"  - {job['title']} @ {job['company']}")
    
    asyncio.run(test())
