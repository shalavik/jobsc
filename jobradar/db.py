"""Database functionality for the job radar application."""
import sqlite3
from pathlib import Path
from datetime import datetime
import json
from typing import List, Optional
from .models import Job, Feed

def init_db(db_path: Path = Path("jobs.db")):
    """Initialize the database with required tables."""
    with sqlite3.connect(db_path) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT,
                company TEXT,
                url TEXT,
                source TEXT,
                date TEXT,
                location TEXT,
                salary TEXT,
                job_type TEXT,
                description TEXT,
                posted_date TEXT,
                is_remote BOOLEAN,
                experience_level TEXT,
                skills TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS feed_cache (
                feed_name TEXT PRIMARY KEY,
                last_fetched TEXT,
                error_count INTEGER,
                last_error TEXT,
                data TEXT
            )
        ''')

def save_jobs(jobs: List[Job], db_path: Path = Path("jobs.db")):
    """Save jobs to the database."""
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO jobs (
                id, title, company, url, source, date, location, salary,
                job_type, description, posted_date, is_remote,
                experience_level, skills, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(
                job.id,
                job.title,
                job.company,
                job.url,
                job.source,
                job.date,
                job.location,
                job.salary,
                job.job_type,
                job.description,
                job.posted_date.isoformat() if job.posted_date else None,
                job.is_remote,
                job.experience_level,
                json.dumps(job.skills),
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ) for job in jobs]
        )

def get_jobs(
    db_path: Path = Path("jobs.db"),
    filters: Optional[dict] = None
) -> List[Job]:
    """Retrieve jobs from the database with optional filtering."""
    query = "SELECT * FROM jobs WHERE 1=1"
    params = []
    
    if filters:
        if filters.get('source'):
            query += " AND source = ?"
            params.append(filters['source'])
        if filters.get('location'):
            query += " AND location LIKE ?"
            params.append(f"%{filters['location']}%")
        if filters.get('job_type'):
            query += " AND job_type = ?"
            params.append(filters['job_type'])
        if filters.get('is_remote') is not None:
            query += " AND is_remote = ?"
            params.append(filters['is_remote'])
        if filters.get('experience_level'):
            query += " AND experience_level = ?"
            params.append(filters['experience_level'])
        if filters.get('salary_min'):
            query += " AND CAST(REPLACE(REPLACE(salary, '$', ''), 'k', '000') AS INTEGER) >= ?"
            params.append(int(filters['salary_min']) * 1000)
        if filters.get('salary_max'):
            query += " AND CAST(REPLACE(REPLACE(salary, '$', ''), 'k', '000') AS INTEGER) <= ?"
            params.append(int(filters['salary_max']) * 1000)
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        
        jobs = []
        for row in rows:
            job = Job(
                id=row[0],
                title=row[1],
                company=row[2],
                url=row[3],
                source=row[4],
                date=row[5],
                location=row[6],
                salary=row[7],
                job_type=row[8],
                description=row[9],
                posted_date=datetime.fromisoformat(row[10]) if row[10] else None,
                is_remote=bool(row[11]),
                experience_level=row[12],
                skills=json.loads(row[13]) if row[13] else []
            )
            jobs.append(job)
        
        return jobs

def save_feed_cache(feed: Feed, jobs: List[Job], db_path: Path = Path("jobs.db")):
    """Save feed cache to the database."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO feed_cache (
                feed_name, last_fetched, error_count, last_error, data
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                feed.name,
                datetime.now().isoformat(),
                feed.error_count,
                feed.last_error,
                json.dumps([job.__dict__ for job in jobs])
            )
        )

def get_feed_cache(feed: Feed, db_path: Path = Path("jobs.db")) -> Optional[List[Job]]:
    """Retrieve feed cache from the database."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT last_fetched, data FROM feed_cache WHERE feed_name = ?",
            (feed.name,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
            
        last_fetched = datetime.fromisoformat(row[0])
        if (datetime.now() - last_fetched).total_seconds() > feed.cache_duration * 60:
            return None
            
        jobs_data = json.loads(row[1])
        return [Job(**job_data) for job_data in jobs_data]

def update_feed_error(feed: Feed, error: str, db_path: Path = Path("jobs.db")):
    """Update feed error information in the database."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE feed_cache
            SET error_count = ?, last_error = ?
            WHERE feed_name = ?
            """,
            (feed.error_count + 1, error, feed.name)
        ) 