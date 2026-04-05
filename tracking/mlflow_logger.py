"""
MLflow Application Tracking
Logs each job application with full context for analysis.

Same pattern as MalVision - demonstrates MLflow in production.
"""

import os
from datetime import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import mlflow
from mlflow.tracking import MlflowClient

load_dotenv()


class ApplicationTracker:
    """
    MLflow-based tracking for job applications.
    Logs: job details, scores, cover letters, outcomes.
    """
    
    def __init__(
        self,
        tracking_uri: str = None,
        experiment_name: str = None
    ):
        self.tracking_uri = tracking_uri or os.getenv(
            "MLFLOW_TRACKING_URI", "./mlruns"
        )
        self.experiment_name = experiment_name or os.getenv(
            "MLFLOW_EXPERIMENT_NAME", "job-applications"
        )
        
        # Configure MLflow
        mlflow.set_tracking_uri(self.tracking_uri)
        
        # Create or get experiment
        experiment = mlflow.get_experiment_by_name(self.experiment_name)
        if experiment is None:
            self.experiment_id = mlflow.create_experiment(
                self.experiment_name,
                tags={"project": "job-hunter", "type": "application-tracking"}
            )
        else:
            self.experiment_id = experiment.experiment_id
        
        mlflow.set_experiment(self.experiment_name)
        self.client = MlflowClient(tracking_uri=self.tracking_uri)
        
        print(f"MLflow tracker initialized: {self.experiment_name}")
    
    def log_application(
        self,
        job_id: int,
        job_title: str,
        company: str,
        source: str,
        score: float,
        score_breakdown: Dict[str, float],
        cover_letter: str,
        cover_letter_version: int,
        status: str,
        location: str = "",
        salary_min: int = None,
        salary_max: int = None,
        llm_provider: str = "",
        tokens_used: Dict[str, int] = None,
        extra_params: Dict[str, Any] = None
    ) -> str:
        """
        Log a complete job application record.
        
        Returns:
            MLflow run_id for reference
        """
        with mlflow.start_run(run_name=f"{company}_{job_title[:30]}") as run:
            # Log parameters (job metadata)
            mlflow.log_params({
                "job_id": job_id,
                "job_title": job_title,
                "company": company,
                "source": source,
                "location": location,
                "status": status,
                "llm_provider": llm_provider,
                "cover_letter_version": cover_letter_version
            })
            
            # Log metrics (quantitative)
            mlflow.log_metrics({
                "overall_score": score,
                **{f"score_{k}": v for k, v in score_breakdown.items()}
            })
            
            if salary_min:
                mlflow.log_metric("salary_min", salary_min)
            if salary_max:
                mlflow.log_metric("salary_max", salary_max)
            
            if tokens_used:
                mlflow.log_metrics({
                    "tokens_prompt": tokens_used.get("prompt_tokens", 0),
                    "tokens_completion": tokens_used.get("completion_tokens", 0),
                    "tokens_total": tokens_used.get("total_tokens", 0),
                    "cost_usd": tokens_used.get("cost_usd", 0)
                })
            
            # Log artifacts (cover letter text)
            cover_letter_path = f"/tmp/cover_letter_{job_id}.txt"
            with open(cover_letter_path, "w") as f:
                f.write(f"Company: {company}\n")
                f.write(f"Position: {job_title}\n")
                f.write(f"Generated: {datetime.utcnow().isoformat()}\n")
                f.write(f"Version: {cover_letter_version}\n")
                f.write("=" * 60 + "\n\n")
                f.write(cover_letter)
            
            mlflow.log_artifact(cover_letter_path, "cover_letters")
            
            # Log extra params if provided
            if extra_params:
                mlflow.log_params({
                    f"extra_{k}": str(v)[:250]  # Truncate long values
                    for k, v in extra_params.items()
                })
            
            # Set tags for filtering
            mlflow.set_tags({
                "application_date": datetime.utcnow().strftime("%Y-%m-%d"),
                "company": company,
                "source": source,
                "status": status
            })
            
            return run.info.run_id
    
    def update_outcome(
        self,
        run_id: str,
        outcome: str,
        notes: str = ""
    ):
        """
        Update application outcome after response received.
        
        Args:
            run_id: MLflow run_id from log_application
            outcome: "interview", "rejected", "offer", "no_response"
            notes: Any additional notes
        """
        self.client.set_tag(run_id, "outcome", outcome)
        self.client.set_tag(run_id, "outcome_date", datetime.utcnow().strftime("%Y-%m-%d"))
        
        if notes:
            self.client.set_tag(run_id, "outcome_notes", notes[:250])
        
        # Log response time metric
        run = self.client.get_run(run_id)
        start_time = datetime.fromisoformat(
            run.data.tags.get("application_date", datetime.utcnow().strftime("%Y-%m-%d"))
        )
        days_to_response = (datetime.utcnow() - start_time).days
        self.client.log_metric(run_id, "days_to_response", days_to_response)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get application statistics from MLflow"""
        runs = self.client.search_runs(
            experiment_ids=[self.experiment_id],
            max_results=1000
        )
        
        stats = {
            "total_applications": len(runs),
            "by_status": {},
            "by_source": {},
            "by_company": {},
            "avg_score": 0,
            "total_tokens": 0,
            "total_cost": 0
        }
        
        scores = []
        for run in runs:
            status = run.data.tags.get("status", "unknown")
            source = run.data.params.get("source", "unknown")
            company = run.data.params.get("company", "unknown")
            
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            stats["by_source"][source] = stats["by_source"].get(source, 0) + 1
            stats["by_company"][company] = stats["by_company"].get(company, 0) + 1
            
            if "overall_score" in run.data.metrics:
                scores.append(run.data.metrics["overall_score"])
            
            stats["total_tokens"] += run.data.metrics.get("tokens_total", 0)
            stats["total_cost"] += run.data.metrics.get("cost_usd", 0)
        
        if scores:
            stats["avg_score"] = sum(scores) / len(scores)
        
        return stats
    
    def get_recent_runs(self, limit: int = 10) -> list:
        """Get most recent application runs"""
        runs = self.client.search_runs(
            experiment_ids=[self.experiment_id],
            order_by=["start_time DESC"],
            max_results=limit
        )
        
        return [
            {
                "run_id": run.info.run_id,
                "company": run.data.params.get("company"),
                "job_title": run.data.params.get("job_title"),
                "score": run.data.metrics.get("overall_score"),
                "status": run.data.tags.get("status"),
                "outcome": run.data.tags.get("outcome"),
                "date": run.data.tags.get("application_date")
            }
            for run in runs
        ]


if __name__ == "__main__":
    # Test tracker
    tracker = ApplicationTracker()
    
    # Log a test application
    run_id = tracker.log_application(
        job_id=1,
        job_title="AI Research Engineer",
        company="ESET",
        source="profesia",
        score=0.85,
        score_breakdown={"keyword": 0.9, "company": 1.0, "location": 0.8},
        cover_letter="Test cover letter content...",
        cover_letter_version=1,
        status="applied",
        location="Bratislava",
        llm_provider="deepseek",
        tokens_used={"prompt_tokens": 500, "completion_tokens": 300, "total_tokens": 800}
    )
    
    print(f"Logged application with run_id: {run_id}")
    print(f"Stats: {tracker.get_stats()}")
