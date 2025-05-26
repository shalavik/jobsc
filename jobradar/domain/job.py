from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

class JobSource(Enum):
    """Enumeration of job sources."""
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    REMOTE_OK = "remote_ok"
    WE_WORK_REMOTELY = "weworkremotely"
    STACK_OVERFLOW = "stackoverflow"
    GITHUB = "github"
    HACKERNEWS = "hackernews"
    ANGEL_LIST = "angelist"
    DICE = "dice"
    CLEVER_TECH = "clevertech"
    WORKING_NOMADS = "working_nomads"
    GLASSDOOR = "glassdoor"
    JOBRADAR = "jobradar"
    SNAPHUNT = "snaphunt"

@dataclass
class Job:
    """Job posting data model with freshness tracking."""
    title: str
    company: str
    location: str
    description: str
    url: str
    source: JobSource
    posted_at: Optional[datetime] = None
    salary_range: Optional[str] = None
    job_type: Optional[str] = None
    experience_level: Optional[str] = None
    skills: Optional[List[str]] = None
    benefits: Optional[List[str]] = None
    remote: Optional[bool] = None
    raw_data: Optional[Dict[str, Any]] = None
    
    # Data quality fields
    last_seen: Optional[datetime] = None
    expires: Optional[datetime] = None
    
    def __post_init__(self):
        """Validate the job data after initialization."""
        if not self.title or not self.company or not self.url:
            raise ValueError("Title, company, and URL are required fields")
        
        if not isinstance(self.source, JobSource):
            self.source = JobSource(self.source)

    def is_expired(self, max_age_days: int = 7) -> bool:
        """Check if job is expired based on last_seen or expires field.
        
        Args:
            max_age_days: Maximum age in days before considering job expired
            
        Returns:
            True if job should be considered expired
        """
        now = datetime.utcnow()
        
        # Check explicit expiration
        if self.expires and now > self.expires:
            return True
            
        # Check age based on last_seen
        if self.last_seen:
            age_days = (now - self.last_seen).days
            return age_days > max_age_days
            
        # Fallback to posted_at if available
        if self.posted_at:
            age_days = (now - self.posted_at).days
            return age_days > max_age_days
            
        return False 