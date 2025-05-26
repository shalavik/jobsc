import pytest
from datetime import datetime
from typing import List
from jobradar.ingest.fetcher import JobFetcher
from jobradar.domain.job import Job, JobSource
from jobradar.ingest.browser_pool import BrowserPool
from jobradar.ingest.rate_limiter import RateLimiter

class TestJobFetcher:
    @pytest.fixture
    def browser_pool(self):
        return BrowserPool(max_browsers=2)
    
    @pytest.fixture
    def rate_limiter(self):
        return RateLimiter(max_requests_per_minute=30)
    
    @pytest.fixture
    def job_fetcher(self, browser_pool, rate_limiter):
        return JobFetcher(browser_pool=browser_pool, rate_limiter=rate_limiter)
    
    def test_fetch_all_returns_raw_jobs(self, job_fetcher):
        """Test that fetch_all returns raw Job objects without database dependencies"""
        # Arrange
        sources = [JobSource.LINKEDIN, JobSource.INDEED]
        
        # Act
        jobs = job_fetcher.fetch_all(sources)
        
        # Assert
        assert isinstance(jobs, list)
        assert all(isinstance(job, Job) for job in jobs)
        
        # Verify job objects have required fields but no DB-specific attributes
        for job in jobs:
            assert hasattr(job, 'title')
            assert hasattr(job, 'company')
            assert hasattr(job, 'location')
            assert hasattr(job, 'description')
            assert hasattr(job, 'url')
            assert hasattr(job, 'source')
            assert hasattr(job, 'posted_at')
            
            # Verify no DB-specific attributes
            assert not hasattr(job, 'id')
            assert not hasattr(job, 'created_at')
            assert not hasattr(job, 'updated_at')
    
    def test_fetch_all_handles_empty_sources(self, job_fetcher):
        """Test that fetch_all handles empty source list gracefully"""
        jobs = job_fetcher.fetch_all([])
        assert isinstance(jobs, list)
        assert len(jobs) == 0
    
    def test_fetch_all_respects_rate_limits(self, job_fetcher):
        """Test that fetch_all respects rate limits between sources"""
        start_time = datetime.now()
        job_fetcher.fetch_all([JobSource.LINKEDIN, JobSource.INDEED])
        end_time = datetime.now()
        
        # Verify that at least 2 seconds passed (rate limit between sources)
        assert (end_time - start_time).total_seconds() >= 2 