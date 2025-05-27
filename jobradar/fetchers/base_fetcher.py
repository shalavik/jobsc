"""Core job fetching functionality.

This module contains the main Fetcher class which handles fetching jobs from
different types of feeds (RSS, JSON, HTML) with proper error handling and
rate limiting.
"""

from typing import List, Dict, Any, Optional
import os
import json
import logging
import requests
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from requests.exceptions import RequestException

from ..models import Job, Feed
from ..rate_limiter import RateLimiter
from .browser_pool import BrowserPool
from .parsers import HTMLParsers
from .headless import HeadlessFetcher

logger = logging.getLogger(__name__)


class Fetcher:
    """Handles fetching jobs from different types of feeds.
    
    Features:
    - RSS feed parsing
    - JSON API consumption
    - HTML scraping with site-specific parsers
    - Headless browser automation
    - Rate limiting and error handling
    """
    
    def __init__(self) -> None:
        """Initialize the fetcher with rate limiter and browser pool."""
        self.rate_limiter = RateLimiter()
        self.browser_pool = BrowserPool()
        self.html_parsers = HTMLParsers()
        self.headless_fetcher = HeadlessFetcher(self.browser_pool)
    
    def fetch(self, feed: Feed, max_retries: int = 3) -> List[Job]:
        """Fetch jobs from a feed using the appropriate method.
        
        Args:
            feed: Feed configuration object
            max_retries: Maximum number of retry attempts
            
        Returns:
            List of Job objects
            
        Raises:
            ValueError: If fetch method is unsupported
            RequestException: If network requests fail after retries
        """
        logger.info(f"Starting fetch for {feed.name} with method {feed.fetch_method}")
        
        fetch_method = getattr(feed, 'fetch_method', None) or getattr(feed, 'type', None)
        logger.info(f"Resolved fetch_method to: {fetch_method}")
        
        retries = 0
        while retries < max_retries:
            try:
                if feed.rate_limit:
                    self.rate_limiter.wait_if_needed(feed.name, feed.rate_limit)
                
                logger.info(f"Fetching using method: {fetch_method}")
                
                if fetch_method == "rss":
                    jobs = self._fetch_rss(feed)
                elif fetch_method == "json":
                    jobs = self._fetch_json(feed)
                elif fetch_method == "html":
                    jobs = self._fetch_html(feed)
                elif fetch_method == "headless":
                    jobs = self.headless_fetcher.fetch(feed)
                else:
                    logger.error(f"Unsupported fetch_method: {fetch_method}")
                    raise ValueError(f"Unsupported fetch_method: {fetch_method}")
                
                logger.info(f"Successfully fetched {len(jobs)} jobs from {feed.name}")
                return jobs
                
            except RequestException as e:
                retries += 1
                logger.error(f"RequestException for {feed.name}: {e}")
                if retries >= max_retries:
                    logger.error(f"Max retries exceeded for {feed.name}")
                    raise
                if not feed.rate_limit or not self.rate_limiter.handle_request_exception(e, feed.name, feed.rate_limit):
                    raise
            except Exception as e:
                logger.error(f"Error fetching from {feed.name}: {e}")
                raise
    
    def _fetch_rss(self, feed: Feed) -> List[Job]:
        """Fetch jobs from an RSS feed.
        
        Args:
            feed: Feed configuration object
            
        Returns:
            List of Job objects
        """
        req_kwargs = {}
        if feed.headers:
            req_kwargs['headers'] = feed.headers
            logger.info(f"Using custom headers for {feed.name}")
        if feed.cookies:
            req_kwargs['cookies'] = feed.cookies
        
        logger.info(f"Fetching RSS from {feed.url}")
        response = requests.get(feed.url, **req_kwargs)
        response.raise_for_status()
        
        parsed = feedparser.parse(response.text)
        jobs = []
        
        logger.info(f"Found {len(parsed.entries)} entries in RSS feed from {feed.name}")
        
        for entry in parsed.entries:
            # Try to parse the date robustly
            raw_date = entry.get("published", "")
            parsed_date = raw_date
            if raw_date:
                try:
                    parsed_date = date_parser.parse(raw_date).isoformat()
                except Exception:
                    parsed_date = raw_date  # fallback to original string
            
            # Extract company name - try different possible locations
            company = ""
            # 1. Check for a 'company' field directly in the entry
            if 'company' in entry:
                company = entry.company
            # 2. Fallback to author if company not found
            elif 'author' in entry:
                company = entry.author
            # 3. Use source title as last resort
            elif hasattr(entry, 'source') and hasattr(entry.source, 'title'):
                company = entry.source.title
            
            logger.debug(f"Processing entry: {entry.get('title', '')} from {company}")
            
            job = Job(
                id=entry.get("id", entry.get("link", "")),
                title=entry.get("title", ""),
                company=company,
                url=entry.get("link", ""),
                source=feed.name,
                date=parsed_date
            )
            jobs.append(job)
        
        logger.info(f"Created {len(jobs)} job objects from {feed.name}")
        return jobs
    
    def _fetch_json(self, feed: Feed) -> List[Job]:
        """Fetch jobs from a JSON feed or local file.
        
        Args:
            feed: Feed configuration object
            
        Returns:
            List of Job objects
            
        Raises:
            ValueError: If the JSON structure is invalid
            RequestException: If the request fails
        """
        jobs = []
        try:
            # If the URL is a local file, load from disk
            if os.path.isfile(feed.url):
                with open(feed.url, 'r') as f:
                    data = json.load(f)
            else:
                req_kwargs = {}
                if feed.headers:
                    req_kwargs['headers'] = feed.headers
                if feed.cookies:
                    req_kwargs['cookies'] = feed.cookies
                response = requests.get(feed.url, **req_kwargs)
                response.raise_for_status()
                data = response.json()
            
            # Handle different JSON structures
            entries = []
            if isinstance(data, list):
                entries = data
            elif isinstance(data, dict):
                # Try common keys for job listings
                for key in ['jobs', 'results', 'items', 'data', 'listings']:
                    if key in data:
                        entries = data[key]
                        break
                if not entries:
                    logger.warning(f"No job entries found in JSON response for {feed.name}")
                    return jobs
            
            logger.info(f"Found {len(entries)} entries in JSON feed from {feed.name}")
            
            for entry in entries:
                try:
                    # Try to extract job details with fallbacks
                    job_id = str(entry.get('id', entry.get('job_id', entry.get('slug', ''))))
                    title = entry.get('title', entry.get('name', entry.get('position', '')))
                    company = entry.get('company', entry.get('company_name', entry.get('employer', 'Unknown Company')))
                    url = entry.get('url', entry.get('link', entry.get('apply_url', '')))
                    
                    # Handle relative URLs
                    if url and url.startswith('/'):
                        base_url = feed.url.split('/')[0:3]  # Get scheme and domain
                        url = '/'.join(base_url) + url
                    
                    # Parse date if available
                    date = entry.get('date', entry.get('published_at', entry.get('created_at', '')))
                    if date:
                        try:
                            date = date_parser.parse(date).isoformat()
                        except Exception:
                            pass  # Keep original date string if parsing fails
                    
                    # Create job object if we have at least a title
                    if title:
                        job = Job(
                            id=job_id or url or title,  # Use title as last resort for ID
                            title=title,
                            company=company,
                            url=url,
                            source=feed.name,
                            date=date
                        )
                        jobs.append(job)
                        logger.debug(f"Created job: {title} at {company}")
                    else:
                        logger.warning(f"Skipping entry without title in {feed.name}")
                        
                except Exception as e:
                    logger.error(f"Error processing entry in {feed.name}: {e}")
                    continue
            
            logger.info(f"Successfully processed {len(jobs)} jobs from {feed.name}")
            return jobs
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from {feed.name}: {e}")
            raise ValueError(f"Invalid JSON response from {feed.name}")
        except RequestException as e:
            logger.error(f"Request failed for {feed.name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing {feed.name}: {e}")
            raise
    
    def _fetch_html(self, feed: Feed) -> List[Job]:
        """Fetch jobs from an HTML page using site-specific parsers.
        
        Args:
            feed: Feed configuration object
            
        Returns:
            List of Job objects
        """
        req_kwargs = {}
        if feed.headers:
            req_kwargs['headers'] = feed.headers
        if feed.cookies:
            req_kwargs['cookies'] = feed.cookies
        
        logger.info(f"Fetching HTML from {feed.url}")
        response = requests.get(feed.url, **req_kwargs)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Use site-specific parser
        return self.html_parsers.parse_jobs(soup, feed) 