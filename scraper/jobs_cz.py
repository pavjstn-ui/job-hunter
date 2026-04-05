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
        self.base_url = "https://www.jobs.cz/en/"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive"
        }
    
    async def search(self, keyword: str, location: str = None) -> List[Dict]:
        """
        Search for jobs on jobs.cz (English version)
        
        Args:
            keyword: Search term
            location: Optional location filter (ignored for now as per instructions)
            
        Returns:
            List of job dicts with keys: title, company, url, location, source
        """
        jobs = []
        
        # Only use q[] parameter, drop locality as per instructions
        params = {
            "q[]": keyword,
        }
            
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
                
                # Based on the provided HTML structure, job listings are in <article> elements
                # Let's find all job cards
                job_cards = soup.find_all('article')
                
                for card in job_cards:
                    try:
                        # Find the job title link - looking for h2 or h3 with a link containing /rpd/
                        title_elem = card.find('h2') or card.find('h3')
                        if not title_elem:
                            continue
                            
                        link_elem = title_elem.find('a', href=lambda x: x and '/rpd/' in x)
                        if not link_elem:
                            continue
                            
                        title = link_elem.get_text(strip=True)
                        url = link_elem.get('href')
                        
                        if not url.startswith('http'):
                            url = f"https://www.jobs.cz{url}" if url.startswith('/') else f"https://www.jobs.cz/{url}"
                        
                        # Extract company - in the provided HTML, company is in a list item
                        company = "Not specified"
                        location_text = ""
                        
                        # Look for company information
                        # In the sample HTML, company appears in list items or specific spans
                        # Let's look for text that might contain company name
                        # First, try to find list items
                        list_items = card.find_all('li')
                        if list_items:
                            # The first list item often contains company
                            company_text = list_items[0].get_text(strip=True)
                            # Sometimes it contains location separated by em dash
                            if '—' in company_text:
                                parts = company_text.split('—')
                                company = parts[0].strip()
                                if len(parts) > 1:
                                    location_text = parts[1].strip()
                            else:
                                company = company_text
                        
                        # If we didn't find company in list items, try other approaches
                        if company == "Not specified":
                            # Look for spans with company info
                            spans = card.find_all('span')
                            for span in spans:
                                text = span.get_text(strip=True)
                                if text and len(text) < 100:  # Company names are usually short
                                    company = text
                                    break
                        
                        # Try to extract location from other list items if not found
                        if not location_text and len(list_items) > 1:
                            # The second list item might have location
                            location_text = list_items[1].get_text(strip=True)
                        
                        # Also look for location in other elements
                        if not location_text:
                            location_elems = card.find_all(string=lambda x: 'Praha' in str(x) or 'Brno' in str(x) if x else False)
                            if location_elems:
                                location_text = location_elems[0].strip()
                        
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
                
                # If we didn't find jobs with the first method, try a broader approach
                if not jobs:
                    # Look for all links containing /rpd/
                    job_links = soup.find_all('a', href=lambda x: x and '/rpd/' in x)
                    for link in job_links:
                        try:
                            title = link.get_text(strip=True)
                            if not title:
                                continue
                                
                            url = link.get('href')
                            if not url.startswith('http'):
                                url = f"https://www.jobs.cz{url}" if url.startswith('/') else f"https://www.jobs.cz/{url}"
                            
                            # Find parent element to look for company and location
                            parent = link.find_parent(['article', 'div', 'li'])
                            company = "Not specified"
                            location_text = ""
                            
                            if parent:
                                # Look for company in nearby elements
                                text_elements = parent.find_all(string=True)
                                for text in text_elements:
                                    t = text.strip()
                                    if t and t != title and len(t) < 100:
                                        company = t
                                        break
                            
                            jobs.append({
                                "title": title,
                                "company": company,
                                "url": url,
                                "location": location_text,
                                "source": "jobs.cz"
                            })
                        except Exception as e:
                            logger.debug(f"Error parsing alternative job link: {e}")
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
        jobs = await scraper.search("AI engineer")
        print(f"Found {len(jobs)} jobs")
        for job in jobs[:3]:
            print(f"Title: {job['title']}")
            print(f"Company: {job['company']}")
            print(f"URL: {job['url']}")
            print(f"Location: {job['location']}")
            print()
    
    asyncio.run(test())
