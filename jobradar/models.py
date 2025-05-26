"""Data models for the job radar application."""
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

@dataclass
class Job:
    """Represents a job posting.
    
    Attributes:
        id: Unique identifier for the job
        title: Job title
        company: Company name
        url: URL to the job posting
        source: Source of the job posting (e.g., "RemoteOK", "WorkingNomads")
        date: Publication date (optional)
        location: Job location (e.g., "Remote", "New York, NY")
        salary: Salary information (e.g., "$100k - $150k", "€50k - €70k")
        job_type: Type of job (e.g., "Full-time", "Contract", "Part-time")
        description: Job description
        posted_date: When the job was posted (datetime object)
        is_remote: Whether the job is remote
        experience_level: Required experience level (e.g., "Entry", "Mid", "Senior")
        skills: List of required skills
    """
    id: str
    title: str
    company: str
    url: str
    source: str
    date: str = ""
    location: str = ""
    salary: str = ""
    job_type: str = ""
    description: str = ""
    posted_date: Optional[datetime] = None
    is_remote: bool = False
    experience_level: str = ""
    skills: list = None

    def __post_init__(self):
        """Initialize default values for mutable attributes and validate required fields."""
        if self.skills is None:
            self.skills = []
        
        # Validate required fields
        if not self.id or not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Job ID is required and must be a non-empty string")
        if not self.title or not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Job title is required and must be a non-empty string")
    
    def __eq__(self, other):
        """Two jobs are equal if they have the same ID."""
        if not isinstance(other, Job):
            return False
        return self.id == other.id
    
    def __hash__(self):
        """Hash based on job ID for use in sets and dictionaries."""
        return hash(self.id)

@dataclass
class Feed:
    """Represents a job feed configuration.
    
    Attributes:
        name: Feed name
        url: Feed URL
        type: Feed type (e.g., "rss", "json", "html")
        parser: Parser to use for this feed
        fetch_method: Method to use for fetching (e.g., "rss", "json", "html", "headless")
        rate_limit: Rate limit configuration
        cache_duration: How long to cache the feed results (in minutes)
        last_fetched: When the feed was last fetched
        error_count: Number of consecutive errors
        last_error: Last error message
        headers: Custom HTTP headers
        cookies: Custom HTTP cookies
    """
    name: str
    url: str
    type: str
    parser: str
    fetch_method: Optional[str] = None
    rate_limit: Dict[str, Any] = None
    cache_duration: int = 30  # Default cache duration in minutes
    last_fetched: Optional[datetime] = None
    error_count: int = 0
    last_error: str = ""
    headers: Optional[Dict[str, str]] = None  # Custom HTTP headers
    cookies: Optional[Dict[str, str]] = None  # Custom HTTP cookies
    
    def __post_init__(self):
        """Validate required fields."""
        if not self.url or not isinstance(self.url, str) or not self.url.strip():
            raise ValueError("Feed URL is required and must be a non-empty string") 