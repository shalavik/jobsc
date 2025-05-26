"""Base parser for job sources."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from playwright.sync_api import Browser
from jobradar.domain.job import Job, JobSource

class BaseParser(ABC):
    """Base class for all job source parsers."""
    
    def __init__(self, source: JobSource):
        """Initialize the parser.
        
        Args:
            source: The job source this parser handles
        """
        self.source = source
        self.rate_limit = {
            'requests_per_minute': 30,
            'retry_after': 2
        }
    
    @abstractmethod
    async def fetch_jobs(self, browser: Browser) -> List[Dict[str, Any]]:
        """Fetch jobs from the source.
        
        Args:
            browser: Browser instance to use for fetching
            
        Returns:
            List of job data dictionaries
        """
        pass
    
    def parse_job(self, job_data: Dict[str, Any]) -> Job:
        """Parse raw job data into a Job object.
        
        Args:
            job_data: Raw job data from the source
            
        Returns:
            Parsed Job object
        """
        return Job(
            title=job_data['title'],
            company=job_data['company'],
            location=job_data['location'],
            description=job_data['description'],
            url=job_data['url'],
            source=self.source,
            posted_at=job_data.get('posted_at'),
            salary_range=job_data.get('salary_range'),
            job_type=job_data.get('job_type'),
            experience_level=job_data.get('experience_level'),
            skills=job_data.get('skills'),
            benefits=job_data.get('benefits'),
            remote=job_data.get('remote'),
            raw_data=job_data
        ) 