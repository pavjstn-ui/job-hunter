"""
Job Scoring and Filtering
Scores jobs based on keyword match, company priority, location, salary.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import re


class JobScorer:
    """
    Score jobs against configured criteria.
    Returns 0.0-1.0 score with breakdown.
    """
    
    def __init__(self, config: Dict):
        self.config = config
        
        # Load weights
        weights = config.get("scoring", {}).get("weights", {})
        self.weights = {
            "keyword": weights.get("keyword_match", 0.3),
            "company": weights.get("company_match", 0.25),
            "location": weights.get("location_match", 0.2),
            "salary": weights.get("salary_match", 0.15),
            "recency": weights.get("recency", 0.1)
        }
        
        # Load thresholds
        thresholds = config.get("scoring", {}).get("thresholds", {})
        self.auto_apply_threshold = thresholds.get("auto_apply", 0.85)
        self.manual_threshold = thresholds.get("manual_review", 0.60)
        self.reject_threshold = thresholds.get("reject", 0.60)
        
        # Load keywords
        search_config = config.get("search", {})
        keywords = search_config.get("keywords", {})
        self.primary_keywords = [k.lower() for k in keywords.get("primary", [])]
        self.secondary_keywords = [k.lower() for k in keywords.get("secondary", [])]
        self.exclude_keywords = [k.lower() for k in search_config.get("exclude_keywords", [])]
        
        # Load target companies
        companies = config.get("target_companies", {})
        self.priority_companies = [c.lower() for c in companies.get("priority", [])]
        self.preferred_companies = [c.lower() for c in companies.get("preferred", [])]
        
        # Load locations
        self.target_locations = [
            loc.get("name", "").lower() 
            for loc in search_config.get("locations", [])
        ]
        
        # Salary
        self.min_salary = search_config.get("salary", {}).get("min_eur", 0)
    
    def score(self, job: Dict) -> Dict:
        """
        Score a job and return overall score with breakdown.
        
        Returns:
            {
                "score": float,
                "breakdown": {component: score},
                "decision": "auto_apply" | "manual_review" | "reject",
                "reasons": [str]
            }
        """
        breakdown = {}
        reasons = []
        
        # Check exclusions first
        if self._should_exclude(job):
            return {
                "score": 0.0,
                "breakdown": {"excluded": 0.0},
                "decision": "reject",
                "reasons": ["Matched exclusion keywords"]
            }
        
        # Score each component
        breakdown["keyword"] = self._score_keywords(job)
        breakdown["company"] = self._score_company(job)
        breakdown["location"] = self._score_location(job)
        breakdown["salary"] = self._score_salary(job)
        breakdown["recency"] = self._score_recency(job)
        
        # Calculate weighted score
        total_score = sum(
            breakdown[k] * self.weights[k] 
            for k in self.weights
        )
        
        # Determine decision
        if total_score >= self.auto_apply_threshold:
            decision = "auto_apply"
            reasons.append(f"High score ({total_score:.0%}) - auto-apply candidate")
        elif total_score >= self.manual_threshold:
            decision = "manual_review"
            reasons.append(f"Medium score ({total_score:.0%}) - manual review needed")
        else:
            decision = "reject"
            reasons.append(f"Low score ({total_score:.0%}) - below threshold")
        
        # Add specific reasons
        if breakdown["company"] == 1.0:
            reasons.append("Priority company match!")
        elif breakdown["company"] >= 0.7:
            reasons.append("Preferred company")
        
        if breakdown["keyword"] >= 0.8:
            reasons.append("Strong keyword match")
        
        return {
            "score": round(total_score, 3),
            "breakdown": {k: round(v, 3) for k, v in breakdown.items()},
            "decision": decision,
            "reasons": reasons
        }
    
    def _should_exclude(self, job: Dict) -> bool:
        """Check if job matches exclusion keywords"""
        text = f"{job.get('title', '')} {job.get('description', '')} {job.get('requirements', '')}".lower()
        
        for keyword in self.exclude_keywords:
            if keyword in text:
                return True
        
        return False
    
    def _score_keywords(self, job: Dict) -> float:
        """Score based on keyword matches"""
        text = f"{job.get('title', '')} {job.get('description', '')} {job.get('requirements', '')}".lower()
        
        # Primary keywords (worth more)
        primary_matches = sum(1 for kw in self.primary_keywords if kw in text)
        primary_score = min(primary_matches / max(len(self.primary_keywords), 1) * 1.5, 1.0)
        
        # Secondary keywords
        secondary_matches = sum(1 for kw in self.secondary_keywords if kw in text)
        secondary_score = min(secondary_matches / max(len(self.secondary_keywords), 1), 1.0)
        
        # Title match bonus (if keyword in title, extra weight)
        title = job.get("title", "").lower()
        title_bonus = 0.2 if any(kw in title for kw in self.primary_keywords) else 0
        
        return min((primary_score * 0.7 + secondary_score * 0.3) + title_bonus, 1.0)
    
    def _score_company(self, job: Dict) -> float:
        """Score based on company match"""
        company = job.get("company", "").lower()
        
        # Priority companies
        for c in self.priority_companies:
            if c in company:
                return 1.0
        
        # Preferred companies
        for c in self.preferred_companies:
            if c in company:
                return 0.7
        
        # Unknown company - neutral score
        return 0.4
    
    def _score_location(self, job: Dict) -> float:
        """Score based on location match"""
        location = job.get("location", "").lower()
        
        if not location:
            return 0.3  # Unknown location
        
        if "remote" in location:
            return 1.0  # Remote is always good
        
        for target in self.target_locations:
            if target in location:
                return 1.0
        
        # Nearby countries/cities
        nearby = ["czech", "prague", "vienna", "wien", "bratislava", "slovakia", "austria"]
        if any(n in location for n in nearby):
            return 0.7
        
        return 0.2  # Not a target location
    
    def _score_salary(self, job: Dict) -> float:
        """Score based on salary"""
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")
        currency = job.get("currency", "EUR")
        
        if not salary_min and not salary_max:
            return 0.5  # No salary info - neutral
        
        # Convert to EUR (rough)
        salary = salary_max or salary_min
        if currency == "CZK":
            salary = salary / 25  # Rough CZK to EUR
        
        if salary >= self.min_salary:
            return 1.0
        elif salary >= self.min_salary * 0.8:
            return 0.7
        else:
            return 0.3
    
    def _score_recency(self, job: Dict) -> float:
        """Score based on how recent the posting is"""
        posted = job.get("posted_date")
        
        if not posted:
            return 0.5  # Unknown - neutral
        
        try:
            if isinstance(posted, str):
                posted_date = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            else:
                posted_date = posted
            
            days_old = (datetime.now(posted_date.tzinfo) - posted_date).days
            
            if days_old <= 3:
                return 1.0
            elif days_old <= 7:
                return 0.8
            elif days_old <= 14:
                return 0.6
            elif days_old <= 30:
                return 0.4
            else:
                return 0.2
        except:
            return 0.5


def filter_jobs(jobs: List[Dict], scorer: JobScorer) -> Dict[str, List[Dict]]:
    """
    Filter and categorize jobs by decision.
    
    Returns:
        {
            "auto_apply": [...],
            "manual_review": [...],
            "reject": [...]
        }
    """
    results = {
        "auto_apply": [],
        "manual_review": [],
        "reject": []
    }
    
    for job in jobs:
        score_result = scorer.score(job)
        job["score"] = score_result["score"]
        job["score_breakdown"] = score_result["breakdown"]
        job["score_reasons"] = score_result["reasons"]
        
        results[score_result["decision"]].append(job)
    
    # Sort by score descending
    for key in results:
        results[key].sort(key=lambda x: x["score"], reverse=True)
    
    return results


if __name__ == "__main__":
    import yaml
    
    # Load config
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    
    scorer = JobScorer(config)
    
    # Test job
    test_job = {
        "title": "AI Research Engineer",
        "company": "ESET",
        "location": "Bratislava, Slovakia",
        "description": "Looking for ML Engineer with Python, PyTorch experience...",
        "salary_min": 50000,
        "salary_max": 70000,
        "currency": "EUR"
    }
    
    result = scorer.score(test_job)
    print(f"Score: {result['score']:.0%}")
    print(f"Decision: {result['decision']}")
    print(f"Breakdown: {result['breakdown']}")
    print(f"Reasons: {result['reasons']}")
