import asyncio
import httpx
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class JobsCzScraper:
    """Scraper for jobs.cz - Czech Republic"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.base_url = "https://www.jobs.cz/prace/"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    
    async def search(self, keyword: str, location: str = None) -> List[Dict]:
        """
        Search for jobs on jobs.cz
        
        Args:
            keyword: Search term
            location: Optional location filter
            
        Returns:
            List of job dicts with keys: title, company, url, location, source
        """
        jobs = []
        
        params = {
            "q[]": keyword,
        }
        if location:
            params["locality[]"] = location
            
        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                follow_redirects=True,
                timeout=30.0
            ) as client:
                response = await client.get(
                    self.base_url,
                    params=params
                )
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find job listings - looking for elements that contain job information
                # Based on the provided HTML structure, job cards appear to be in various divs
                # Let's try to find job title links first
                job_links = soup.select('h2 a[href*="/rpd/"]')
                
                for link in job_links:
                    try:
                        title = link.get_text(strip=True)
                        url = link.get('href')
                        
                        if not url.startswith('http'):
                            url = f"https://www.jobs.cz{url}" if url.startswith('/') else f"https://www.jobs.cz/{url}"
                        
                        # Find company - look for elements with company info
                        # In the provided HTML, company appears in list items after the job card
                        job_card = link.find_parent('article') or link.find_parent('div') or link.find_parent('li')
                        company = None
                        location_text = location or ""
                        
                        if job_card:
                            # Try to find company in various possible selectors
                            company_elem = job_card.select_one('.SearchResultCard__footerItem')
                            if not company_elem:
                                # Try other possible selectors
                                company_elem = job_card.select_one('li:first-child')
                            
                            if company_elem:
                                company = company_elem.get_text(strip=True)
                                # Sometimes company text includes location, try to clean it
                                if '—' in company:
                                    parts = company.split('—')
                                    company = parts[0].strip()
                                    if len(parts) > 1 and not location_text:
                                        location_text = parts[1].strip()
                            
                            # If still no company, try to find in sibling elements
                            if not company:
                                # Look for company in nearby elements
                                next_siblings = job_card.find_next_siblings('ul')
                                for sibling in next_siblings[:2]:  # Check first couple of sibling uls
                                    li_items = sibling.find_all('li')
                                    if li_items:
                                        company = li_items[0].get_text(strip=True)
                                        break
                        
                        # If company still not found, use a placeholder
                        if not company:
                            company = "Not specified"
                        
                        job_data = {
                            "title": title,
                            "company": company,
                            "url": url,
                            "location": location_text,
                            "source": "jobs.cz"
                        }
                        
                        jobs.append(job_data)
                        
                    except Exception as e:
                        logger.warning(f"Error parsing job listing: {e}")
                        continue
                
                # If we didn't find jobs with the first method, try alternative approach
                if not jobs:
                    # Look for job cards in the search results
                    job_cards = soup.select('article, .search-result, .job-card')
                    for card in job_cards:
                        try:
                            title_elem = card.select_one('h2 a, h3 a, .job-title a')
                            if not title_elem:
                                continue
                                
                            title = title_elem.get_text(strip=True)
                            url = title_elem.get('href')
                            
                            if not url.startswith('http'):
                                url = f"https://www.jobs.cz{url}" if url.startswith('/') else f"https://www.jobs.cz/{url}"
                            
                            # Try to extract company
                            company_elem = card.select_one('.company, .employer, .firma')
                            company = company_elem.get_text(strip=True) if company_elem else "Not specified"
                            
                            # Try to extract location
                            location_elem = card.select_one('.location, .misto, .localita')
                            job_location = location_elem.get_text(strip=True) if location_elem else (location or "")
                            
                            jobs.append({
                                "title": title,
                                "company": company,
                                "url": url,
                                "location": job_location,
                                "source": "jobs.cz"
                            })
                        except Exception as e:
                            logger.debug(f"Error parsing alternative job card: {e}")
                            continue
                
                logger.info(f"Found {len(jobs)} jobs from jobs.cz")
                return jobs
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error while scraping jobs.cz: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error while scraping jobs.cz: {e}")
            return []
    
    async def get_job_details(self, job_url: str) -> Dict:
        """
        Get detailed information for a specific job
        
        Args:
            job_url: URL of the job posting
            
        Returns:
            Dict with detailed job information
        """
        # This method would be implemented to fetch full job details
        # For now, return a minimal implementation
        return {
            "url": job_url,
            "description": "Detailed description not implemented yet",
            "source": "jobs.cz"
        }

if __name__ == "__main__":
    async def test():
        scraper = JobsCzScraper()
        jobs = await scraper.search("AI engineer", "Praha")
        print(f"Found {len(jobs)} jobs")
        for job in jobs[:3]:
            print(f"Title: {job['title']}")
            print(f"Company: {job['company']}")
            print(f"URL: {job['url']}")
            print(f"Location: {job['location']}")
            print()
    
    asyncio.run(test())
