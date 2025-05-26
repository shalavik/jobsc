"""Tests for job expiration functionality."""
import pytest
from datetime import datetime, timedelta
from jobradar.domain.job import Job, JobSource

class TestJobExpiration:
    """Test job expiration logic for data quality."""
    
    def test_job_not_expired_when_recent(self):
        """Test that recent jobs are not considered expired."""
        job = Job(
            title="Test Job",
            company="Test Company", 
            location="Remote",
            description="Test description",
            url="https://example.com/job",
            source=JobSource.LINKEDIN,
            last_seen=datetime.utcnow() - timedelta(days=1)  # 1 day ago
        )
        
        assert not job.is_expired(max_age_days=7)
    
    def test_job_expired_when_old_last_seen(self):
        """Test that jobs with old last_seen are considered expired."""
        job = Job(
            title="Test Job",
            company="Test Company",
            location="Remote", 
            description="Test description",
            url="https://example.com/job",
            source=JobSource.LINKEDIN,
            last_seen=datetime.utcnow() - timedelta(days=10)  # 10 days ago
        )
        
        assert job.is_expired(max_age_days=7)
    
    def test_job_expired_when_explicit_expires_set(self):
        """Test that jobs with explicit expires date are handled correctly."""
        job = Job(
            title="Test Job",
            company="Test Company",
            location="Remote",
            description="Test description", 
            url="https://example.com/job",
            source=JobSource.LINKEDIN,
            expires=datetime.utcnow() - timedelta(days=1)  # Expired yesterday
        )
        
        assert job.is_expired()
    
    def test_job_not_expired_when_explicit_expires_future(self):
        """Test that jobs with future expires date are not expired."""
        job = Job(
            title="Test Job",
            company="Test Company",
            location="Remote",
            description="Test description",
            url="https://example.com/job", 
            source=JobSource.LINKEDIN,
            expires=datetime.utcnow() + timedelta(days=5)  # Expires in 5 days
        )
        
        assert not job.is_expired()
    
    def test_job_expired_fallback_to_posted_at(self):
        """Test that jobs fall back to posted_at when last_seen is not available."""
        job = Job(
            title="Test Job",
            company="Test Company",
            location="Remote",
            description="Test description",
            url="https://example.com/job",
            source=JobSource.LINKEDIN,
            posted_at=datetime.utcnow() - timedelta(days=10),  # 10 days ago
            last_seen=None
        )
        
        assert job.is_expired(max_age_days=7)
    
    def test_expired_job_dropped_from_list(self):
        """Test that expired jobs can be filtered out of job lists."""
        jobs = [
            Job(
                title="Fresh Job",
                company="Test Company",
                location="Remote",
                description="Test description",
                url="https://example.com/job1",
                source=JobSource.LINKEDIN,
                last_seen=datetime.utcnow() - timedelta(days=1)  # Recent
            ),
            Job(
                title="Expired Job", 
                company="Test Company",
                location="Remote",
                description="Test description",
                url="https://example.com/job2",
                source=JobSource.LINKEDIN,
                last_seen=datetime.utcnow() - timedelta(days=10)  # Old
            )
        ]
        
        # Filter out expired jobs
        fresh_jobs = [job for job in jobs if not job.is_expired(max_age_days=7)]
        
        assert len(fresh_jobs) == 1
        assert fresh_jobs[0].title == "Fresh Job"
        
        # Verify the expired job was dropped
        expired_jobs = [job for job in jobs if job.is_expired(max_age_days=7)]
        assert len(expired_jobs) == 1
        assert expired_jobs[0].title == "Expired Job" 