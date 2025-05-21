"""Job filtering functionality."""
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
import re
import logging
from datetime import datetime
from .models import Job

logger = logging.getLogger(__name__)

@dataclass
class FilterConfig:
    """Configuration for job filtering."""
    keywords: List[str]
    locations: List[str]
    exclude: List[str]
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    job_types: List[str] = None
    experience_levels: List[str] = None
    is_remote: Optional[bool] = None
    sources: List[str] = None

class JobFilter:
    """Handles filtering of job listings based on configuration rules."""
    
    def __init__(self, config: FilterConfig):
        """Initialize the job filter.
        
        Args:
            config: Filter configuration
        """
        self.config = config
        self.keyword_patterns = [re.compile(rf'\b{re.escape(kw)}\b', re.IGNORECASE) 
                               for kw in config.keywords]
        self.location_patterns = [re.compile(rf'\b{re.escape(loc)}\b', re.IGNORECASE) 
                                for loc in config.locations]
        self.exclude_patterns = [re.compile(rf'\b{re.escape(ex)}\b', re.IGNORECASE) 
                               for ex in config.exclude]
    
    def _parse_salary(self, salary_str: str) -> Optional[int]:
        """Parse salary string to integer value.
        
        Args:
            salary_str: Salary string (e.g., "$100k", "100000")
            
        Returns:
            Optional[int]: Parsed salary value or None
        """
        if not salary_str:
            return None
            
        # Remove currency symbols and convert to lowercase
        salary_str = salary_str.lower().replace('$', '').replace(',', '')
        
        # Handle 'k' suffix
        if 'k' in salary_str:
            salary_str = salary_str.replace('k', '')
            try:
                return int(float(salary_str) * 1000)
            except ValueError:
                return None
                
        try:
            return int(salary_str)
        except ValueError:
            return None
    
    def matches_salary(self, job: Job) -> bool:
        """Check if job salary matches configured range.
        
        Args:
            job: Job to check
            
        Returns:
            bool: True if salary matches range
        """
        if not hasattr(job, 'salary') or not job.salary:
            return True
            
        salary = self._parse_salary(job.salary)
        if salary is None:
            return True
            
        if self.config.salary_min and salary < self.config.salary_min:
            return False
        if self.config.salary_max and salary > self.config.salary_max:
            return False
            
        return True
    
    def matches_job_type(self, job: Job) -> bool:
        """Check if job type matches configured types.
        
        Args:
            job: Job to check
            
        Returns:
            bool: True if job type matches
        """
        if not self.config.job_types:
            return True
            
        if not hasattr(job, 'job_type') or not job.job_type:
            return False
            
        return job.job_type.lower() in [t.lower() for t in self.config.job_types]
    
    def matches_experience(self, job: Job) -> bool:
        """Check if experience level matches configured levels.
        
        Args:
            job: Job to check
            
        Returns:
            bool: True if experience level matches
        """
        if not self.config.experience_levels:
            return True
            
        if not hasattr(job, 'experience_level') or not job.experience_level:
            return False
            
        return job.experience_level.lower() in [e.lower() for e in self.config.experience_levels]
    
    def matches_remote(self, job: Job) -> bool:
        """Check if remote status matches configuration.
        
        Args:
            job: Job to check
            
        Returns:
            bool: True if remote status matches
        """
        if self.config.is_remote is None:
            return True
            
        if not hasattr(job, 'is_remote'):
            return False
            
        return job.is_remote == self.config.is_remote
    
    def matches_source(self, job: Job) -> bool:
        """Check if source matches configured sources.
        
        Args:
            job: Job to check
            
        Returns:
            bool: True if source matches
        """
        if not self.config.sources:
            return True
            
        return job.source.lower() in [s.lower() for s in self.config.sources]
    
    def matches_keywords(self, job: Job) -> bool:
        """Check if job matches any of the configured keywords.
        
        Args:
            job: Job to check
            
        Returns:
            bool: True if job matches keywords
        """
        if not self.keyword_patterns:
            return True
            
        text_to_check = f"{job.title} {job.company}"
        if hasattr(job, 'description'):
            text_to_check += f" {job.description}"
            
        return any(pattern.search(text_to_check) for pattern in self.keyword_patterns)
    
    def matches_location(self, job: Job) -> bool:
        """Check if job matches any of the configured locations.
        
        Args:
            job: Job to check
            
        Returns:
            bool: True if job matches locations
        """
        if not self.location_patterns:
            return True
            
        if not hasattr(job, 'location') or not job.location:
            return False
            
        return any(pattern.search(job.location) for pattern in self.location_patterns)
    
    def is_excluded(self, job: Job) -> bool:
        """Check if job should be excluded based on exclusion rules.
        
        Args:
            job: Job to check
            
        Returns:
            bool: True if job should be excluded
        """
        if not self.exclude_patterns:
            return False
            
        text_to_check = f"{job.title} {job.company}"
        if hasattr(job, 'description'):
            text_to_check += f" {job.description}"
            
        return any(pattern.search(text_to_check) for pattern in self.exclude_patterns)
    
    def filter_jobs(self, jobs: List[Job]) -> List[Job]:
        """Filter a list of jobs based on configuration rules.
        
        Args:
            jobs: List of jobs to filter
            
        Returns:
            List[Job]: Filtered list of jobs
        """
        filtered_jobs = []
        
        for job in jobs:
            # Skip if job matches exclusion rules
            if self.is_excluded(job):
                logger.debug(f"Excluding job: {job.title} at {job.company}")
                continue
                
            # Check all filter conditions
            if (self.matches_keywords(job) and 
                self.matches_location(job) and
                self.matches_salary(job) and
                self.matches_job_type(job) and
                self.matches_experience(job) and
                self.matches_remote(job) and
                self.matches_source(job)):
                filtered_jobs.append(job)
                logger.debug(f"Including job: {job.title} at {job.company}")
            else:
                logger.debug(f"Filtering out job: {job.title} at {job.company}")
        
        return filtered_jobs

def create_filter_from_config(config: Dict[str, Any]) -> JobFilter:
    """Create a JobFilter instance from configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        JobFilter: Configured job filter
    """
    filter_config = FilterConfig(
        keywords=config.get('keywords', []),
        locations=config.get('locations', []),
        exclude=config.get('exclude', []),
        salary_min=config.get('salary_min'),
        salary_max=config.get('salary_max'),
        job_types=config.get('job_types', []),
        experience_levels=config.get('experience_levels', []),
        is_remote=config.get('is_remote'),
        sources=config.get('sources', [])
    )
    return JobFilter(filter_config)

def keyword_match(job: Job, keywords: List[str]) -> bool:
    """Check if a job matches any of the given keywords.
    
    Args:
        job: Job to check
        keywords: List of keywords to match against
        
    Returns:
        True if any keyword matches, False otherwise
    """
    if not keywords:
        return True
        
    text = f"{job.title} {job.company}".lower()
    return any(keyword.lower() in text for keyword in keywords)

def dedupe(jobs: List[Job]) -> List[Job]:
    """Remove duplicate jobs based on title, company, and source.
    
    Args:
        jobs: List of jobs to deduplicate
        
    Returns:
        List of unique jobs
    """
    seen: Set[str] = set()
    unique_jobs: List[Job] = []
    
    for job in jobs:
        # Create a unique key for the job
        key = f"{job.title}|{job.company}|{job.source}"
        
        if key not in seen:
            seen.add(key)
            unique_jobs.append(job)
            
    return unique_jobs 

def filter_jobs(jobs: List[Job], filters: dict) -> List[Job]:
    """Filter jobs by keyword, location, and company."""
    keyword = filters.get('keyword')
    location = filters.get('location')
    company = filters.get('company')

    def match(job: Job) -> bool:
        if keyword and keyword.lower() not in (job.title + ' ' + job.company).lower():
            return False
        if location and location.lower() not in (getattr(job, 'location', '') or '').lower():
            return False
        if company and company.lower() not in job.company.lower():
            return False
        return True

    return [job for job in jobs if match(job)] 