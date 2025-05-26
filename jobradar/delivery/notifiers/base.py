"""Base notifier for job alerts."""
from abc import ABC, abstractmethod
from typing import List
from jobradar.domain.job import Job

class Notifier(ABC):
    """Base class for all job notifiers."""
    
    def __init__(self, config: dict):
        """Initialize the notifier.
        
        Args:
            config: Configuration dictionary for the notifier
        """
        self.config = config
    
    @abstractmethod
    async def notify(self, jobs: List[Job]) -> bool:
        """Send notification about new jobs.
        
        Args:
            jobs: List of jobs to notify about
            
        Returns:
            True if notification was successful
        """
        pass
    
    def format_job_message(self, job: Job) -> str:
        """Format a job into a notification message.
        
        Args:
            job: Job to format
            
        Returns:
            Formatted message string
        """
        message = f"🎯 {job.title}\n"
        message += f"🏢 {job.company}\n"
        message += f"📍 {job.location}\n"
        
        if job.salary_range:
            message += f"💰 {job.salary_range}\n"
            
        if job.job_type:
            message += f"📋 {job.job_type}\n"
            
        if job.experience_level:
            message += f"📊 {job.experience_level}\n"
            
        if job.remote:
            message += "🌐 Remote\n"
            
        message += f"\n🔗 {job.url}\n"
        
        return message 