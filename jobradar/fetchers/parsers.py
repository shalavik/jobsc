"""Site-specific HTML parsers for job extraction.

This module contains HTML parsing logic for various job sites,
organized into a single HTMLParsers class that routes to the appropriate
parser based on the feed URL.
"""

from typing import List, Optional, Dict, Any
import logging
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag

from ..models import Job, Feed

logger = logging.getLogger(__name__)


class HTMLParsers:
    """Collection of site-specific HTML parsers for job extraction."""
    
    def parse_jobs(self, soup: BeautifulSoup, feed: Feed) -> List[Job]:
        """Parse jobs from HTML using the appropriate site-specific parser.
        
        Args:
            soup: BeautifulSoup object of the HTML page
            feed: Feed configuration object
            
        Returns:
            List of Job objects
        """
        # Determine which parser to use based on the URL
        url = feed.url.lower()
        
        if 'indeed.com' in url:
            return self._parse_indeed(soup, feed)
        elif 'remoteok.io' in url:
            return self._parse_remoteok(soup, feed)
        elif 'snaphunt.com' in url:
            return self._parse_snaphunt(soup, feed)
        elif 'alljobs.lv' in url:
            return self._parse_alljobs(soup, feed)
        elif 'remotive.io' in url:
            return self._parse_remotive(soup, feed)
        elif 'workingnomads.co' in url:
            return self._parse_workingnomads(soup, feed)
        elif 'cryptocurrencyjobs.co' in url:
            return self._parse_cryptocurrencyjobs(soup, feed)
        elif 'nodesk.substack.com' in url:
            return self._parse_nodesk_substack(soup, feed)
        elif 'remotehabits.com' in url:
            return self._parse_remotehabits(soup, feed)
        elif 'jobspresso.co' in url:
            return self._parse_jobspresso(soup, feed)
        elif 'weworkremotely.com' in url and 'support' in url:
            return self._parse_weworkremotely_support(soup, feed)
        elif 'linkedin.com' in url:
            return self._parse_linkedin(soup, feed)
        elif 'glassdoor.com' in url:
            return self._parse_glassdoor(soup, feed)
        elif 'remote3.co' in url:
            return self._parse_remote3(soup, feed)
        else:
            logger.warning(f"No specific parser found for {url}, using generic parser")
            return self._parse_generic(soup, feed)
    
    def _parse_indeed(self, soup: BeautifulSoup, feed: Feed) -> List[Job]:
        """Parse Indeed job listings."""
        jobs = []
        
        # Indeed uses multiple possible selectors for job cards
        job_selectors = [
            'div[data-jk]',  # Standard job cards
            '.jobsearch-SerpJobCard',  # Alternative selector
            '.slider_container .slider_item',  # Slider format
            '.job_seen_beacon'  # Another format
        ]
        
        job_cards = []
        for selector in job_selectors:
            cards = soup.select(selector)
            if cards:
                job_cards = cards
                logger.info(f"Found {len(cards)} job cards using selector: {selector}")
                break
        
        if not job_cards:
            logger.warning(f"No job cards found for Indeed feed {feed.name}")
            return jobs
        
        for card in job_cards:
            try:
                # Extract job ID
                job_id = card.get('data-jk', '')
                
                # Extract title
                title_elem = card.select_one('h2 a span[title], .jobTitle a span[title], [data-testid="job-title"]')
                title = title_elem.get('title', '') if title_elem else ''
                
                # Extract company
                company_elem = card.select_one('.companyName, [data-testid="company-name"]')
                company = company_elem.get_text(strip=True) if company_elem else ''
                
                # Extract URL
                link_elem = card.select_one('h2 a, .jobTitle a')
                url = ''
                if link_elem:
                    href = link_elem.get('href', '')
                    if href.startswith('/'):
                        url = urljoin('https://indeed.com', href)
                    else:
                        url = href
                
                # Extract location (optional)
                location_elem = card.select_one('[data-testid="job-location"], .companyLocation')
                location = location_elem.get_text(strip=True) if location_elem else ''
                
                if title and company:
                    job = Job(
                        id=job_id or url,
                        title=title,
                        company=company,
                        url=url,
                        source=feed.name,
                        location=location
                    )
                    jobs.append(job)
                    logger.debug(f"Parsed Indeed job: {title} at {company}")
                    
            except Exception as e:
                logger.warning(f"Error parsing Indeed job card: {e}")
                continue
        
        logger.info(f"Successfully parsed {len(jobs)} jobs from Indeed")
        return jobs
    
    def _parse_remoteok(self, soup: BeautifulSoup, feed: Feed) -> List[Job]:
        """Parse RemoteOK job listings."""
        jobs = []
        
        # RemoteOK uses table rows for job listings
        job_rows = soup.select('tr.job')
        logger.info(f"Found {len(job_rows)} job rows in RemoteOK")
        
        for row in job_rows:
            try:
                # Extract job ID
                job_id = row.get('data-id', '')
                
                # Extract title
                title_elem = row.select_one('.company h2')
                title = title_elem.get_text(strip=True) if title_elem else ''
                
                # Extract company
                company_elem = row.select_one('.company h3')
                company = company_elem.get_text(strip=True) if company_elem else ''
                
                # Extract URL
                link_elem = row.select_one('td.company a')
                url = ''
                if link_elem:
                    href = link_elem.get('href', '')
                    if href.startswith('/'):
                        url = urljoin('https://remoteok.io', href)
                    else:
                        url = href
                
                # Extract tags/skills
                tag_elements = row.select('.tags .tag')
                tags = [tag.get_text(strip=True) for tag in tag_elements]
                
                if title:
                    job = Job(
                        id=job_id or url,
                        title=title,
                        company=company or 'Remote Company',
                        url=url,
                        source=feed.name,
                        skills=', '.join(tags) if tags else ''
                    )
                    jobs.append(job)
                    logger.debug(f"Parsed RemoteOK job: {title}")
                    
            except Exception as e:
                logger.warning(f"Error parsing RemoteOK job: {e}")
                continue
        
        logger.info(f"Successfully parsed {len(jobs)} jobs from RemoteOK")
        return jobs
    
    def _parse_generic(self, soup: BeautifulSoup, feed: Feed) -> List[Job]:
        """Generic HTML parser for unknown sites."""
        jobs = []
        
        # Try to find job-like elements using common patterns
        potential_selectors = [
            '.job', '.job-item', '.job-listing', '.job-card',
            '.position', '.vacancy', '.listing',
            'article', '.post', '.entry'
        ]
        
        for selector in potential_selectors:
            elements = soup.select(selector)
            if elements:
                logger.info(f"Found {len(elements)} potential job elements using selector: {selector}")
                
                for i, elem in enumerate(elements[:20]):  # Limit to first 20
                    try:
                        # Try to extract title from common patterns
                        title = ''
                        title_selectors = ['h1', 'h2', 'h3', '.title', '.job-title', 'a']
                        for title_sel in title_selectors:
                            title_elem = elem.select_one(title_sel)
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                                if len(title) > 10:  # Reasonable title length
                                    break
                        
                        # Try to extract link
                        url = ''
                        link_elem = elem.select_one('a')
                        if link_elem:
                            href = link_elem.get('href', '')
                            if href:
                                url = urljoin(feed.url, href)
                        
                        if title:
                            job = Job(
                                id=url or f"{feed.name}_{i}",
                                title=title,
                                company='Unknown Company',
                                url=url,
                                source=feed.name
                            )
                            jobs.append(job)
                            
                    except Exception as e:
                        logger.debug(f"Error parsing generic element: {e}")
                        continue
                
                if jobs:
                    break
        
        logger.info(f"Generic parser found {len(jobs)} jobs")
        return jobs
    
    # Additional site-specific parsers would go here...
    # For brevity, I'll add a few more key ones
    
    def _parse_workingnomads(self, soup: BeautifulSoup, feed: Feed) -> List[Job]:
        """Parse WorkingNomads job listings."""
        jobs = []
        
        # Look for job cards
        job_cards = soup.select('.job-item, .job, article')
        
        for card in job_cards:
            try:
                if not self._might_be_job_card(card):
                    continue
                    
                job_data = self._extract_workingnomads_job(card)
                
                if self._is_valid_workingnomads_job(job_data):
                    job = Job(
                        id=job_data.get('url', '') or job_data.get('title', ''),
                        title=job_data.get('title', ''),
                        company=job_data.get('company', ''),
                        url=job_data.get('url', ''),
                        source=feed.name,
                        location=job_data.get('location', ''),
                        description=job_data.get('description', '')
                    )
                    jobs.append(job)
                    
            except Exception as e:
                logger.warning(f"Error parsing WorkingNomads job: {e}")
                continue
        
        logger.info(f"Successfully parsed {len(jobs)} jobs from WorkingNomads")
        return jobs
    
    def _might_be_job_card(self, element: Tag) -> bool:
        """Check if an element might be a job card."""
        # Simple heuristic: check if it contains typical job-related text
        text = element.get_text().lower()
        job_indicators = ['remote', 'job', 'position', 'developer', 'engineer', 'manager', 'apply']
        return any(indicator in text for indicator in job_indicators) and len(text) > 50
    
    def _extract_workingnomads_job(self, card: Tag) -> Dict[str, str]:
        """Extract job data from a WorkingNomads job card."""
        job_data = {}
        
        # Extract title
        title_elem = card.select_one('h2, h3, .job-title, .title')
        if title_elem:
            job_data['title'] = title_elem.get_text(strip=True)
        
        # Extract company
        company_elem = card.select_one('.company, .employer')
        if company_elem:
            job_data['company'] = company_elem.get_text(strip=True)
        
        # Extract URL
        link_elem = card.select_one('a')
        if link_elem:
            href = link_elem.get('href', '')
            if href.startswith('/'):
                job_data['url'] = urljoin('https://workingnomads.co', href)
            else:
                job_data['url'] = href
        
        # Extract location
        location_elem = card.select_one('.location')
        if location_elem:
            job_data['location'] = location_elem.get_text(strip=True)
        
        return job_data
    
    def _is_valid_workingnomads_job(self, job_data: Dict[str, str]) -> bool:
        """Validate that job data is complete enough."""
        return bool(job_data.get('title')) and len(job_data.get('title', '')) > 3 