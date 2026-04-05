"""
Job Hunter Database Schema and Operations
SQLite-based job tracking with full state management
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum
import json


class JobStatus(Enum):
    NEW = "new"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"
    NO_RESPONSE = "no_response"
    INTERVIEW = "interview"
    OFFER = "offer"
    DECLINED = "declined"


class JobDB:
    def __init__(self, db_path: str = "./db/jobs.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database with schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                salary_min INTEGER,
                salary_max INTEGER,
                currency TEXT DEFAULT 'EUR',
                description TEXT,
                url TEXT,
                requirements TEXT,
                posted_date TEXT,
                scraped_at TEXT NOT NULL,
                score REAL,
                score_breakdown TEXT,
                status TEXT DEFAULT 'new',
                cover_letter TEXT,
                cover_letter_version INTEGER DEFAULT 0,
                applied_at TEXT,
                response_at TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                method TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                confirmation TEXT,
                mlflow_run_id TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telegram_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                message_id INTEGER,
                sent_at TEXT NOT NULL,
                response TEXT,
                responded_at TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        """)
        
        # Indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score)")
        
        conn.commit()
        conn.close()
    
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def add_job(self, job_data: Dict[str, Any]) -> int:
        """Add a new job to the database"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Check if job already exists
        cursor.execute(
            "SELECT id FROM jobs WHERE external_id = ?",
            (job_data.get("external_id"),)
        )
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return existing["id"]
        
        cursor.execute("""
            INSERT INTO jobs (
                external_id, source, title, company, location,
                salary_min, salary_max, currency, description, url,
                requirements, posted_date, scraped_at, score, score_breakdown
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_data.get("external_id"),
            job_data.get("source"),
            job_data.get("title"),
            job_data.get("company"),
            job_data.get("location"),
            job_data.get("salary_min"),
            job_data.get("salary_max"),
            job_data.get("currency", "EUR"),
            job_data.get("description"),
            job_data.get("url"),
            job_data.get("requirements"),
            job_data.get("posted_date"),
            datetime.utcnow().isoformat(),
            job_data.get("score"),
            json.dumps(job_data.get("score_breakdown", {}))
        ))
        
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return job_id
    
    def update_status(self, job_id: int, status: JobStatus, notes: str = None):
        """Update job status"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        update_fields = ["status = ?", "updated_at = ?"]
        params = [status.value, datetime.utcnow().isoformat()]
        
        if notes:
            update_fields.append("notes = ?")
            params.append(notes)
        
        if status == JobStatus.APPLIED:
            update_fields.append("applied_at = ?")
            params.append(datetime.utcnow().isoformat())
        
        params.append(job_id)
        
        cursor.execute(
            f"UPDATE jobs SET {', '.join(update_fields)} WHERE id = ?",
            params
        )
        
        conn.commit()
        conn.close()
    
    def set_cover_letter(self, job_id: int, cover_letter: str):
        """Store generated cover letter"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute(
            """UPDATE jobs 
               SET cover_letter = ?, 
                   cover_letter_version = cover_letter_version + 1,
                   updated_at = ?
               WHERE id = ?""",
            (cover_letter, datetime.utcnow().isoformat(), job_id)
        )
        
        conn.commit()
        conn.close()
    
    def get_job(self, job_id: int) -> Optional[Dict]:
        """Get job by ID"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_jobs_by_status(self, status: JobStatus, limit: int = 50) -> List[Dict]:
        """Get jobs with a specific status"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY score DESC LIMIT ?",
            (status.value, limit)
        )
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_pending_approvals(self) -> List[Dict]:
        """Get jobs waiting for Telegram approval"""
        return self.get_jobs_by_status(JobStatus.PENDING_APPROVAL)
    
    def log_application(self, job_id: int, method: str, mlflow_run_id: str = None):
        """Log an application submission"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO applications (job_id, method, submitted_at, mlflow_run_id)
            VALUES (?, ?, ?, ?)
        """, (job_id, method, datetime.utcnow().isoformat(), mlflow_run_id))
        
        conn.commit()
        conn.close()
    
    def log_telegram_message(self, job_id: int, message_id: int):
        """Log sent Telegram message for tracking"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO telegram_messages (job_id, message_id, sent_at)
            VALUES (?, ?, ?)
        """, (job_id, message_id, datetime.utcnow().isoformat()))
        
        conn.commit()
        conn.close()
    
    def get_stats(self) -> Dict[str, int]:
        """Get application statistics"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM jobs
            GROUP BY status
        """)
        
        stats = {row["status"]: row["count"] for row in cursor.fetchall()}
        
        cursor.execute("SELECT COUNT(*) as total FROM jobs")
        stats["total"] = cursor.fetchone()["total"]
        
        conn.close()
        return stats


    def get_job_by_external_id(self, external_id: str):
        """Get job by external ID to check for duplicates"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM jobs WHERE external_id = ?", (external_id,)
            )
            row = cursor.fetchone()
            if row:
                columns = [d[0] for d in cursor.description]
                return dict(zip(columns, row))
            return None

if __name__ == "__main__":
    # Test database
    db = JobDB()
    print("Database initialized successfully")
    print(f"Stats: {db.get_stats()}")
