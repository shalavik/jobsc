"""LinkedIn job parser."""
import logging
from typing import List, Dict, Any
from playwright.sync_api import Browser, Page
from datetime import datetime
from .base import BaseParser
from jobradar.domain.job import JobSource

logger = logging.getLogger(__name__)

class LinkedInParser(BaseParser):
    """Parser for LinkedIn jobs."""
    
    def __init__(self):
        """Initialize the LinkedIn parser."""
        super().__init__(JobSource.LINKEDIN)
        self.rate_limit = {
            'requests_per_minute': 20,
            'retry_after': 3
        }
    
    async def fetch_jobs(self, browser: Browser) -> List[Dict[str, Any]]:
        """Fetch jobs from LinkedIn.
        
        Args:
            browser: Browser instance to use for fetching
            
        Returns:
            List of job data dictionaries
        """
        jobs = []
        page = await browser.new_page()
        
        try:
            # Navigate to LinkedIn jobs
            await page.goto('https://www.linkedin.com/jobs/')
            
            # Wait for job cards to load
            await page.wait_for_selector('.job-card-container')
            
            # Extract job data
            job_cards = await page.query_selector_all('.job-card-container')
            
            for card in job_cards:
                try:
                    # Extract basic info
                    title_elem = await card.query_selector('.job-card-list__title')
                    company_elem = await card.query_selector('.job-card-container__company-name')
                    location_elem = await card.query_selector('.job-card-container__metadata-item')
                    link_elem = await card.query_selector('a.job-card-list__title')
                    
                    if not all([title_elem, company_elem, location_elem, link_elem]):
                        continue
                    
                    title = await title_elem.inner_text()
                    company = await company_elem.inner_text()
                    location = await location_elem.inner_text()
                    url = await link_elem.get_attribute('href')
                    
                    # Get full job details
                    job_data = await self._get_job_details(page, url)
                    
                    if job_data:
                        jobs.append({
                            'title': title,
                            'company': company,
                            'location': location,
                            'url': url,
                            **job_data
                        })
                        
                except Exception as e:
                    logger.error(f"Error parsing LinkedIn job card: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error fetching LinkedIn jobs: {str(e)}")
            
        finally:
            await page.close()
            
        return jobs
    
    async def _get_job_details(self, page: Page, url: str) -> Dict[str, Any]:
        """Get detailed information for a specific job.
        
        Args:
            page: Browser page to use
            url: Job posting URL
            
        Returns:
            Dictionary with job details
        """
        try:
            await page.goto(url)
            await page.wait_for_selector('.job-description')
            
            # Extract description
            desc_elem = await page.query_selector('.job-description')
            description = await desc_elem.inner_text() if desc_elem else ''
            
            # Extract posted date
            date_elem = await page.query_selector('.job-posted-date')
            posted_at = None
            if date_elem:
                date_text = await date_elem.inner_text()
                posted_at = self._parse_date(date_text)
            
            # Extract job type
            type_elem = await page.query_selector('.job-type')
            job_type = await type_elem.inner_text() if type_elem else None
            
            # Extract experience level
            exp_elem = await page.query_selector('.job-experience')
            experience_level = await exp_elem.inner_text() if exp_elem else None
            
            return {
                'description': description,
                'posted_at': posted_at,
                'job_type': job_type,
                'experience_level': experience_level,
                'remote': 'remote' in description.lower()
            }
            
        except Exception as e:
            logger.error(f"Error getting LinkedIn job details: {str(e)}")
            return None
    
    def _parse_date(self, date_text: str) -> datetime:
        """Parse LinkedIn's date format.
        
        Args:
            date_text: Date text from LinkedIn
            
        Returns:
            Parsed datetime object
        """
        try:
            # Handle various LinkedIn date formats
            if 'just now' in date_text.lower():
                return datetime.now()
            elif 'hour' in date_text.lower():
                return datetime.now()
            elif 'day' in date_text.lower():
                return datetime.now()
            else:
                # Try to parse specific date format
                return datetime.strptime(date_text, '%b %d, %Y')
        except Exception:
            return datetime.now() 