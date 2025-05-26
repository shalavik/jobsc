"""
Job fetcher module for retrieving jobs from multiple sources.
"""
import asyncio
import logging
from typing import List, Optional
from datetime import datetime, timedelta

from jobradar.domain.job import Job, JobSource
from jobradar.ingest.browser_pool import BrowserPool
from jobradar.ingest.rate_limiter import RateLimiter
from jobradar.ingest.parsers.base import BaseParser
from jobradar.ingest.parsers.linkedin import LinkedInParser

logger = logging.getLogger(__name__)


class JobFetcher:
    """
    Fetches jobs from multiple sources and returns raw Job dataclasses.
    
    This class coordinates job fetching across different job sources,
    respecting rate limits and using browser pools for efficient scraping.
    """
    
    def __init__(self, browser_pool: BrowserPool, rate_limiter: RateLimiter):
        """
        Initialize the JobFetcher.
        
        Args:
            browser_pool: Pool of browsers for web scraping
            rate_limiter: Rate limiter to control request frequency
        """
        self.browser_pool = browser_pool
        self.rate_limiter = rate_limiter
        self.parsers = self._initialize_parsers()
        # Default rate limit config for job sources
        self.default_rate_limit = {
            'requests_per_minute': 30,
            'retry_after': 2
        }
    
    def _initialize_parsers(self) -> dict[JobSource, BaseParser]:
        """Initialize parsers for each job source."""
        return {
            JobSource.LINKEDIN: LinkedInParser(),
            # Add more parsers as they're implemented
            # JobSource.INDEED: IndeedParser(),
            # JobSource.GLASSDOOR: GlassdoorParser(),
        }
    
    def fetch_all(self, sources: List[JobSource]) -> List[Job]:
        """
        Fetch jobs from all specified sources.
        
        Args:
            sources: List of job sources to fetch from
            
        Returns:
            List of raw Job dataclasses without database dependencies
        """
        if not sources:
            logger.info("No sources specified, returning empty list")
            return []
        
        all_jobs = []
        
        for source in sources:
            try:
                logger.info(f"Fetching jobs from {source.value}")
                
                # Apply rate limiting between sources
                self.rate_limiter.wait_if_needed(source.value, self.default_rate_limit)
                
                # Fetch jobs from this source
                jobs = self._fetch_from_source(source)
                all_jobs.extend(jobs)
                
                logger.info(f"Fetched {len(jobs)} jobs from {source.value}")
                
            except Exception as e:
                logger.error(f"Error fetching from {source.value}: {e}")
                continue
        
        logger.info(f"Total jobs fetched: {len(all_jobs)}")
        return all_jobs
    
    def _fetch_from_source(self, source: JobSource) -> List[Job]:
        """
        Fetch jobs from a specific source.
        
        Args:
            source: The job source to fetch from
            
        Returns:
            List of jobs from this source
        """
        parser = self.parsers.get(source)
        if not parser:
            logger.warning(f"No parser available for {source.value}")
            return []
        
        try:
            # Get a browser from the pool
            browser = self.browser_pool.get_browser()
            
            # Use the parser to fetch jobs
            jobs = parser.parse_jobs(browser)
            
            # Return browser to pool
            self.browser_pool.return_browser(browser)
            
            return jobs
            
        except Exception as e:
            logger.error(f"Error parsing jobs from {source.value}: {e}")
            return []
    
    async def fetch_all_async(self, sources: List[JobSource]) -> List[Job]:
        """
        Asynchronously fetch jobs from all specified sources.
        
        Args:
            sources: List of job sources to fetch from
            
        Returns:
            List of raw Job dataclasses without database dependencies
        """
        if not sources:
            return []
        
        tasks = []
        for source in sources:
            task = asyncio.create_task(self._fetch_from_source_async(source))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_jobs = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Async fetch error: {result}")
            elif isinstance(result, list):
                all_jobs.extend(result)
        
        return all_jobs
    
    async def _fetch_from_source_async(self, source: JobSource) -> List[Job]:
        """
        Asynchronously fetch jobs from a specific source.
        
        Args:
            source: The job source to fetch from
            
        Returns:
            List of jobs from this source
        """
        parser = self.parsers.get(source)
        if not parser:
            logger.warning(f"No parser available for {source.value}")
            return []
        
        try:
            # Apply rate limiting - get wait time and sleep if needed
            wait_time = self.rate_limiter.wait_if_needed(source.value, self.default_rate_limit)
            if wait_time and wait_time > 0:
                await asyncio.sleep(wait_time)
            
            # Get a browser from the pool
            browser = self.browser_pool.get_browser()
            
            # Use the parser to fetch jobs
            jobs = parser.parse_jobs(browser)
            
            # Return browser to pool
            self.browser_pool.return_browser(browser)
            
            return jobs
            
        except Exception as e:
            logger.error(f"Error parsing jobs from {source.value}: {e}")
            return [] 