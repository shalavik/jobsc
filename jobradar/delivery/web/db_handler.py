"""Database-backed web handler for job delivery (sync version)."""
import logging
from typing import List
from fastapi import FastAPI
from jobradar.domain.job import Job, JobSource
from jobradar.domain.matching import SmartTitleMatcher
from jobradar.database import Database

logger = logging.getLogger(__name__)

class DatabaseWebHandler:
    """Database-backed web handler for job delivery (sync version)."""
    
    def __init__(
        self,
        app: FastAPI,
        matcher: SmartTitleMatcher,
        db_url: str = "sqlite:///jobs.db"
    ):
        """Initialize the database web handler.
        
        Args:
            app: FastAPI application instance
            matcher: Smart title matcher for filtering jobs
            db_url: Database connection URL
        """
        self.app = app
        self.matcher = matcher
        self.db = Database(db_url)
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up FastAPI routes."""
        @self.app.get("/jobs")
        async def get_jobs():
            """Get all jobs from the database."""
            return await self._get_jobs()
        
        @self.app.get("/jobs/smart")
        async def get_smart_jobs():
            """Get smart-filtered jobs from the database."""
            jobs = await self._get_jobs()
            return self.matcher.filter_jobs(jobs)
    
    async def _get_jobs(self) -> List[Job]:
        """Get all jobs from the database (sync call in async context).
        
        Returns:
            List of all jobs
        """
        try:
            # Get all jobs (limit 100 for demo)
            job_models = self.db.search_jobs({}, limit=100)
            jobs = []
            for jm in job_models:
                try:
                    # Validate required fields before creating Job
                    title = getattr(jm, 'title', None)
                    company = getattr(jm, 'company', None)
                    url = getattr(jm, 'url', None)
                    
                    if not title or not company or not url:
                        logger.warning(f"Skipping job with missing required fields: title={title}, company={company}, url={url}")
                        continue
                    
                    # Try to parse source as enum, fallback to LINKEDIN
                    source_str = getattr(jm, 'source', 'linkedin')
                    try:
                        source = JobSource(source_str.lower())
                    except ValueError:
                        source = JobSource.LINKEDIN
                        logger.warning(f"Unknown job source '{source_str}', defaulting to LINKEDIN")
                    
                    job = Job(
                        title=title,
                        company=company,
                        location=getattr(jm, 'location', 'Unknown'),
                        description=getattr(jm, 'description', ''),
                        url=url,
                        source=source,
                        posted_at=getattr(jm, 'date', None),
                        salary_range=getattr(jm, 'salary', None),
                        job_type=getattr(jm, 'job_type', None),
                        experience_level=getattr(jm, 'experience_level', None),
                        remote=getattr(jm, 'is_remote', None),
                        skills=getattr(jm, 'skills', None),
                        benefits=None,
                        raw_data={}
                    )
                    jobs.append(job)
                except Exception as e:
                    logger.error(f"Error creating Job object: {str(e)}")
                    continue
                    
            logger.info(f"Successfully loaded {len(jobs)} jobs from database")
            return jobs
        except Exception as e:
            logger.error(f"Error getting jobs from database: {str(e)}")
            # Return empty list instead of raising to prevent 500 errors
            return [] 