"""
Base Scraper Class
Common interface for all job board scrapers.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime
import hashlib


class BaseScraper(ABC):
    """Abstract base class for job scrapers"""
    
    source_name: str = "unknown"
    base_url: str = ""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.keywords = self.config.get("keywords", {})
        self.locations = self.config.get("locations", [])
    
    @abstractmethod
    async def search(self, keyword: str, location: str = None) -> List[Dict]:
        """
        Search for jobs matching keyword and location.
        
        Returns:
            List of job dicts with: external_id, title, company, location,
            description, url, salary_min, salary_max, posted_date
        """
        pass
    
    @abstractmethod
    async def get_job_details(self, job_url: str) -> Dict:
        """
        Get full details for a specific job.
        
        Returns:
            Job dict with full description, requirements, etc.
        """
        pass
    
    def generate_external_id(self, source: str, url: str) -> str:
        """Generate unique external ID from source and URL"""
        content = f"{source}:{url}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def parse_salary(self, salary_text: str) -> Dict[str, Optional[int]]:
        """
        Parse salary string into min/max values.
        
        Returns:
            {"min": int or None, "max": int or None, "currency": str}
        """
        import re
        
        if not salary_text:
            return {"min": None, "max": None, "currency": "EUR"}
        
        # Remove whitespace and lowercase
        text = salary_text.lower().replace(" ", "").replace(",", "")
        
        # Detect currency
        currency = "EUR"
        if "czk" in text or "kč" in text:
            currency = "CZK"
        elif "€" in text or "eur" in text:
            currency = "EUR"
        elif "$" in text or "usd" in text:
            currency = "USD"
        
        # Extract numbers
        numbers = re.findall(r'\d+', text)
        numbers = [int(n) for n in numbers if len(n) >= 3]  # Filter small numbers
        
        if not numbers:
            return {"min": None, "max": None, "currency": currency}
        
        if len(numbers) == 1:
            return {"min": numbers[0], "max": numbers[0], "currency": currency}
        
        return {
            "min": min(numbers),
            "max": max(numbers),
            "currency": currency
        }
    
    def normalize_job(self, raw: Dict) -> Dict:
        """Normalize job data to standard format"""
        return {
            "external_id": raw.get("external_id") or self.generate_external_id(
                self.source_name, raw.get("url", "")
            ),
            "source": self.source_name,
            "title": raw.get("title", "").strip(),
            "company": raw.get("company", "").strip(),
            "location": raw.get("location", "").strip(),
            "description": raw.get("description", "").strip(),
            "requirements": raw.get("requirements", "").strip(),
            "url": raw.get("url", "").strip(),
            "salary_min": raw.get("salary_min"),
            "salary_max": raw.get("salary_max"),
            "currency": raw.get("currency", "EUR"),
            "posted_date": raw.get("posted_date"),
            "scraped_at": datetime.utcnow().isoformat()
        }
