"""Feed fetching functionality."""
from typing import List, Dict, Any, Optional, Union
import requests
import feedparser
import json
import logging
from bs4 import BeautifulSoup
from .models import Job, Feed
from .rate_limiter import RateLimiter
import os
from playwright.sync_api import sync_playwright
from dateutil import parser as date_parser
from playwright_stealth import stealth_sync
import random
import time
import pathlib
import threading
import atexit
from datetime import datetime, timedelta
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

# Browser context pool for headless fetching
class BrowserPool:
    """Manages a pool of browser contexts for headless fetching."""
    
    def __init__(self, max_contexts=3, test_mode=False):
        """Initialize the browser pool.
        
        Args:
            max_contexts: Maximum number of browser contexts to keep in the pool
            test_mode: Set to True for testing to avoid blocking operations
        """
        self.max_contexts = max_contexts
        self.contexts = {}  # domain -> (context, last_used_time)
        self.lock = threading.Lock()
        self.playwright = None
        self.browser = None
        self._initialized = False
        self.test_mode = test_mode
        
    def initialize(self):
        """Initialize the browser if not already initialized."""
        if not self._initialized:
            try:
                self.playwright = sync_playwright().start()
                self.browser = self.playwright.chromium.launch(headless=True)
                self._initialized = True
                # Register cleanup on exit
                atexit.register(self.cleanup)
            except Exception as e:
                logger.error(f"Failed to initialize browser pool: {e}")
                raise
    
    def get_context(self, domain, headers=None, cookies=None):
        """Get a browser context for a domain, creating one if necessary.
        
        Args:
            domain: Domain to get context for
            headers: Custom HTTP headers
            cookies: Custom HTTP cookies
            
        Returns:
            Playwright browser context
        """
        self.initialize()
        
        with self.lock:
            # Clean up old contexts if we have too many
            self._cleanup_old_contexts()
            
            # Check if we have a context for this domain
            if domain in self.contexts:
                context, _ = self.contexts[domain]
                self.contexts[domain] = (context, time.time())
                return context
            
            # Standard Chrome user agent - less randomization for consistent identity
            standard_ua = headers.get('User-Agent', "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36") if headers else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            
            # Create a new context
            context = self.browser.new_context(
                user_agent=standard_ua,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                geolocation={"latitude": 40.730610, "longitude": -73.935242},  # NYC
                color_scheme="no-preference",
                device_scale_factor=1
            )
            
            # Load cookies from file if it exists
            cookies_dir = pathlib.Path("cookies")
            cookies_dir.mkdir(exist_ok=True)
            cookies_file = cookies_dir / f"{domain}.json"
            
            if cookies_file.exists():
                try:
                    with open(cookies_file, "r") as f:
                        stored_cookies = json.load(f)
                    context.add_cookies(stored_cookies)
                    logger.info(f"Loaded cookies for {domain}")
                except Exception as e:
                    logger.warning(f"Failed to load cookies for {domain}: {e}")
            
            # Add custom cookies if provided
            if cookies:
                try:
                    custom_cookies = []
                    for k, v in cookies.items():
                        cookie = {
                            "name": k,
                            "value": v,
                            "domain": domain,
                            "path": "/"
                        }
                        custom_cookies.append(cookie)
                    context.add_cookies(custom_cookies)
                    logger.info(f"Added {len(custom_cookies)} custom cookies for {domain}")
                except Exception as e:
                    logger.warning(f"Failed to add custom cookies: {e}")
            
            # Store the context
            self.contexts[domain] = (context, time.time())
            return context
    
    def save_cookies(self, domain):
        """Save cookies for a domain to disk.
        
        Args:
            domain: Domain to save cookies for
        """
        # Skip in test mode to avoid blocking
        if self.test_mode:
            return
            
        # Use a short timeout to avoid deadlocks in tests
        lock_acquired = self.lock.acquire(timeout=0.5)
        if not lock_acquired:
            logger.warning(f"Could not acquire lock to save cookies for {domain}")
            return
            
        try:
            if domain in self.contexts:
                context, _ = self.contexts[domain]
                cookies_dir = pathlib.Path("cookies")
                cookies_dir.mkdir(exist_ok=True)
                cookies_file = cookies_dir / f"{domain}.json"
                
                try:
                    cookies = context.cookies()
                    with open(cookies_file, "w") as f:
                        json.dump(cookies, f)
                    logger.info(f"Saved cookies for {domain}")
                except Exception as e:
                    logger.warning(f"Failed to save cookies for {domain}: {e}")
        finally:
            self.lock.release()
    
    def _cleanup_old_contexts(self):
        """Clean up old contexts if we have too many."""
        if len(self.contexts) <= self.max_contexts:
            return
            
        # Sort contexts by last used time
        sorted_contexts = sorted(self.contexts.items(), key=lambda x: x[1][1])
        
        # Remove oldest contexts
        for domain, (context, _) in sorted_contexts[:len(sorted_contexts) - self.max_contexts]:
            try:
                context.close()
                del self.contexts[domain]
            except Exception as e:
                logger.warning(f"Failed to close context for {domain}: {e}")
    
    def cleanup(self):
        """Clean up all browser contexts and close the browser."""
        if not self._initialized:
            return
            
        # Use a short timeout to avoid deadlocks in tests
        lock_acquired = self.lock.acquire(timeout=0.5)
        if not lock_acquired:
            logger.warning("Could not acquire lock for browser pool cleanup - forcing cleanup")
            # Force cleanup of browser even if lock can't be acquired
            try:
                if self.browser:
                    self.browser.close()
                if self.playwright:
                    self.playwright.stop()
            except Exception as e:
                logger.warning(f"Failed to force close browser: {e}")
            self._initialized = False
            return
            
        try:
            for domain, (context, _) in list(self.contexts.items()):
                try:
                    if not self.test_mode:
                        self.save_cookies(domain)
                    context.close()
                except Exception as e:
                    logger.warning(f"Failed to close context for {domain}: {e}")
            
            self.contexts.clear()
            
            try:
                if self.browser:
                    self.browser.close()
                if self.playwright:
                    self.playwright.stop()
            except Exception as e:
                logger.warning(f"Failed to close browser or playwright: {e}")
            
            self._initialized = False
        finally:
            self.lock.release()

# Create global browser pool
browser_pool = BrowserPool(max_contexts=3)

class Fetcher:
    """Handles fetching jobs from different types of feeds."""
    
    def __init__(self):
        """Initialize the fetcher."""
        self.rate_limiter = RateLimiter()
    
    def fetch(self, feed: Feed, max_retries: int = 3) -> List[Job]:
        """Fetch jobs from a feed, using fetch_method if present."""
        fetch_method = getattr(feed, 'fetch_method', None) or getattr(feed, 'type', None)
        retries = 0
        while retries < max_retries:
            try:
                if feed.rate_limit:
                    self.rate_limiter.wait_if_needed(feed.name, feed.rate_limit)
                logger.info(f"Fetching jobs from {feed.name} using {fetch_method}")
                if fetch_method == "rss":
                    return self._fetch_rss(feed)
                elif fetch_method == "json":
                    return self._fetch_json(feed)
                elif fetch_method == "html":
                    return self._fetch_html(feed)
                elif fetch_method == "headless":
                    return self._fetch_headless(feed)
                else:
                    logger.error(f"Unsupported fetch_method: {fetch_method}")
                    raise ValueError(f"Unsupported fetch_method: {fetch_method}")
            except requests.exceptions.RequestException as e:
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
        """Fetch jobs from an RSS feed."""
        req_kwargs = {}
        if feed.headers:
            req_kwargs['headers'] = feed.headers
            logger.info(f"Using custom headers for {feed.name}: {feed.headers}")
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
        """Fetch jobs from a JSON feed or local file."""
        jobs = []
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
        # Handle both array and object responses
        entries = data if isinstance(data, list) else data.get("jobs", [])
        for entry in entries:
            job = Job(
                id=str(entry.get("id", entry.get("url", ""))),
                title=entry.get("title", ""),
                company=entry.get("company", ""),
                url=entry.get("url", ""),
                source=feed.name,
                date=entry.get("date", "")
            )
            jobs.append(job)
        return jobs
    
    def _fetch_html(self, feed: Feed) -> List[Job]:
        """Fetch jobs from an HTML page using a parser mapping."""
        req_kwargs = {}
        if feed.headers:
            req_kwargs['headers'] = feed.headers
        if feed.cookies:
            req_kwargs['cookies'] = feed.cookies
        response = requests.get(feed.url, **req_kwargs)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        parser_map = {
            "indeed": self._parse_indeed,
            "remoteok": self._parse_remoteok,
            "snaphunt": self._parse_snaphunt,
            "alljobs": self._parse_alljobs,
            "remotive": self._parse_remotive,
            "workingnomads": self._parse_workingnomads,
            "cryptojobslist": self._parse_cryptojobslist,
            "remote3": self._parse_remote3,
            "mindtel": self._parse_mindtel,
            "nodesk": self._parse_nodesk,
            "cryptocurrencyjobs": self._parse_cryptocurrencyjobs,
            "nodesk_substack": self._parse_nodesk_substack,
            "remotehabits": self._parse_remotehabits,
            "jobspresso": self._parse_jobspresso,
            "weworkremotely_support": self._parse_weworkremotely_support,
            # Add more as needed
        }
        parser = parser_map.get(feed.parser)
        if parser:
            return parser(soup, feed)
        else:
            raise ValueError(f"No HTML parser implemented for: {feed.parser}")

    def _parse_indeed(self, soup, feed):
        """Parse jobs from indeed.com with support for multiple HTML structures."""
        jobs = []
        
        # Look for job cards with different possible class names
        card_classes = ["job_seen_beacon", "jobsearch-ResultsList", "tapItem", "result"]
        found_cards = False
        
        for class_name in card_classes:
            job_cards = soup.find_all("div", class_=class_name) or soup.find_all("li", class_=class_name)
            if job_cards:
                found_cards = True
                logger.info(f"Found {len(job_cards)} Indeed job cards with class '{class_name}'")
                
                for card in job_cards:
                    # Try multiple possible title elements
                    title_elem = (
                        card.find("h2", class_=lambda c: c and ("jobTitle" in c or "title" in c)) or
                        card.find("a", class_=lambda c: c and "jobtitle" in c) or
                        card.find("h2", class_="title") or
                        card.select_one("h2 span") or
                        card.find("h2")
                    )
                    
                    # Try multiple company name elements
                    company_elem = (
                        card.find("span", class_=lambda c: c and "companyName" in c) or
                        card.find("div", class_=lambda c: c and "company" in c) or
                        card.find("span", class_="company") or
                        card.find("a", class_="company")
                    )
                    
                    job_id = card.get("data-jk", "")
                    if not job_id:
                        job_id = card.get("id", "")
                        if not job_id:
                            # Try to extract ID from links
                            job_link = card.find("a", href=lambda h: h and "jk=" in h)
                            if job_link:
                                import re
                                match = re.search(r'jk=([a-zA-Z0-9]+)', job_link["href"])
                                if match:
                                    job_id = match.group(1)
                    
                    # Only create job if we have title, company, and some kind of ID
                    if title_elem and company_elem and job_id:
                        job_url = f"https://www.indeed.com/viewjob?jk={job_id}" if job_id else ""
                        if not job_url and job_link and job_link.get("href"):
                            job_url = f"https://www.indeed.com{job_link['href']}" if job_link["href"].startswith("/") else job_link["href"]
                            
                        job = Job(
                            id=job_id,
                            title=title_elem.get_text(strip=True),
                            company=company_elem.get_text(strip=True),
                            url=job_url,
                            source=feed.name,
                            date=""
                        )
                        jobs.append(job)
                        
        # Fall back to generic page table extraction if no cards found
        if not found_cards:
            logger.warning("No job cards found on Indeed using known selectors, trying generic extraction")
            # Just extract any job-like content we can find
            rows = soup.select("table tr")
            for row in rows:
                title_elem = row.find("a", attrs={"data-tn-element": "jobTitle"})
                company_elem = row.find(attrs={"data-tn-component": "companyName"})
                
                if title_elem:
                    company = company_elem.text.strip() if company_elem else "Unknown Company"
                    job_id = title_elem.get("id", "").replace("jl_", "") if title_elem.get("id") else ""
                    job_url = title_elem.get("href", "")
                    if job_url and job_url.startswith("/"):
                        job_url = f"https://www.indeed.com{job_url}"
                    
                    job = Job(
                        id=job_id or job_url,
                        title=title_elem.text.strip(),
                        company=company,
                        url=job_url,
                        source=feed.name,
                        date=""
                    )
                    jobs.append(job)
        
        if not jobs:
            # Check if we're on the robot check page
            if soup.find(text=lambda t: t and ("robot check" in t.lower() or "verify you are a human" in t.lower() or "captcha" in t.lower())):
                logger.warning("Indeed is showing a CAPTCHA/robot verification page")
            else:
                # Log part of the HTML to debug what we're seeing
                text_content = soup.get_text()[:200]
                logger.warning(f"No jobs found on Indeed and no CAPTCHA detected. Page starts with: {text_content}...")
                
        return jobs

    def _parse_remoteok(self, soup, feed):
        jobs = []
        job_cards = soup.find_all("tr", class_="job")
        
        if not job_cards:
            logger.warning(f"No job cards found on RemoteOK using primary selector")
            # Try alternative selectors
            job_cards = (
                soup.find_all("div", class_=lambda c: c and "job" in c) or
                soup.find_all("article", class_=lambda c: c and "job" in c)
            )
        
        logger.info(f"Found {len(job_cards)} job cards on RemoteOK")
            
        for card in job_cards:
            title_elem = (
                card.find("h2", attrs={"itemprop": "title"}) or
                card.find("h3", attrs={"itemprop": "title"}) or
                card.find("div", class_=lambda c: c and "position" in c) or
                card.find(["h2", "h3", "div"], string=lambda s: s and len(s) > 4)  # Any heading with reasonable text
            )
            
            company_elem = (
                card.find("h3", attrs={"itemprop": "name"}) or
                card.find("span", attrs={"itemprop": "name"}) or
                card.find("div", class_=lambda c: c and "company" in c) or
                card.find("span", class_=lambda c: c and "company" in c)
            )
            
            job_id = card.get("data-id", "")
            if not job_id:
                # Look for other possible ID attributes
                job_id = card.get("id", "")
                
                # Try to extract from URL if available
                link = card.find("a", href=True)
                if link and link.get("href", ""):
                    import re
                    match = re.search(r'/([^/]+)$', link["href"])
                    if match:
                        job_id = match.group(1)
            
            if title_elem:  # Only require title element
                job_url = f"https://remoteok.com/remote-jobs/{job_id}" if job_id else ""
                
                # If no job_id was found, try to get complete URL from a link
                link = card.find("a", href=True)
                if not job_url and link and link.get("href", ""):
                    job_url = link["href"]
                    if job_url.startswith("/"):
                        job_url = f"https://remoteok.com{job_url}"
                
                # Use company name if available, otherwise "Unknown Company"
                company_name = company_elem.text.strip() if company_elem else "Unknown Company"
                
                job = Job(
                    id=job_id or title_elem.text.strip(),  # Fallback to title as ID if needed
                    title=title_elem.text.strip(),
                    company=company_name,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_snaphunt(self, soup, feed):
        """Parse jobs from snaphunt.com with robust selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_=lambda c: c and "job" in c) or
            soup.find_all("li", class_=lambda c: c and "job" in c) or
            soup.find_all("article")  # Generic fallback
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on Snaphunt using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on Snaphunt")
        
        for card in job_cards:
            # Try various title element possibilities
            title_elem = (
                card.find("h3", class_="job-title") or
                card.find("h2", class_="job-title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and ("title" in c or "position" in c)) or
                card.find(["h2", "h3", "h4"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company-name") or
                card.find(["div", "span"], class_=lambda c: c and "company" in c) or
                card.find(string=lambda s: s and "at" in s)  # Look for text like "Position at Company"
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem and company_elem and link_elem:
                job_url = link_elem.get("href", "")
                if job_url.startswith("/"):
                    job_url = f"https://snaphunt.com{job_url}"
                    
                company_text = company_elem.text.strip()
                if isinstance(company_elem, str):  # If we found a string like "at Company"
                    import re
                    match = re.search(r'at\s+([^•]+)', company_text)
                    if match:
                        company_text = match.group(1).strip()
                
                job = Job(
                    id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                    title=title_elem.text.strip(),
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_alljobs(self, soup, feed):
        """Parse jobs from alljobs.co.il with robust selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-item") or
            soup.find_all("div", class_=lambda c: c and "job" in c) or
            soup.find_all("li", class_=lambda c: c and "job" in c) or
            soup.find_all(".job-box") or
            soup.select(".job-panels .panel")  # Alternative CSS selector
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on AllJobs using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on AllJobs")
        
        for card in job_cards:
            # Try various title element possibilities
            title_elem = (
                card.find("h2", class_="job-title") or
                card.find("h1", class_="job-title") or
                card.find(["h2", "h3", "h4", "div"], class_=lambda c: c and "title" in c) or
                card.find("a", class_=lambda c: c and "title" in c) or
                card.find(["h2", "h3", "h4"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company-name") or
                card.find(["div", "span"], class_=lambda c: c and "company" in c) or
                card.select_one(".company-details p")  # Alternative selector
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and ("link" in c or "details" in c)) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem and link_elem:
                # If company not found, use fallback
                company_text = company_elem.text.strip() if company_elem else "Unknown Company"
                
                job_url = link_elem.get("href", "")
                if job_url.startswith("/"):
                    job_url = f"https://www.alljobs.co.il{job_url}"
                    
                job = Job(
                    id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                    title=title_elem.text.strip(),
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_remotive(self, soup, feed):
        """Parse jobs from remotive.com with robust selectors."""
        jobs = []
        
        # Try multiple possible job card classes
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("li", class_="job-li") or
            soup.find_all("div", class_="job") or
            soup.find_all("div", class_="ce") or
            soup.find_all("tr[data-ga-job-row]") or  # Possible table format
            soup.select(".job-list-item, .jobs-list li, .jobs-list .item")  # More generic css selectors
        )
        
        if job_cards:
            logger.info(f"Found {len(job_cards)} Remotive job cards")
            
            for card in job_cards:
                # Try multiple possible title elements
                title_elem = (
                    card.find("h2", class_=lambda c: c and ("job-title" in c or "title" in c)) or
                    card.find("div", class_="position") or
                    card.find(["h2", "h3", "div"], class_=["position", "title"]) or
                    card.select_one(".job-info h2, .job-info h3, [data-qa='job-title']") or
                    card.find(["h2", "h3", "h4"])  # Any heading as fallback
                )
                
                # Try multiple company name elements
                company_elem = (
                    card.find(class_=lambda c: c and ("company-name" in c or "company" in c)) or
                    card.find("div", class_="company") or
                    card.select_one(".company span, [data-qa='company-name']") or
                    card.find(string=lambda s: s and " at " in s)  # Text like "Position at Company"
                )
                
                # Try to find link
                link_elem = (
                    card.find("a", class_=lambda c: c and ("job-link" in c or "url" in c)) or
                    card.find("a", href=lambda h: h and ("/remote-jobs/" in h or "/job/" in h)) or
                    card.find("a", href=True)  # Any link
                )
                
                if title_elem:
                    # Get the job URL
                    job_url = link_elem.get("href", "") if link_elem else ""
                    
                    # Add base URL if it's a relative path
                    if job_url and job_url.startswith("/"):
                        job_url = f"https://remotive.com{job_url}"
                        
                    # Get job ID from URL
                    job_id = job_url.split("/")[-1] if job_url else ""
                    
                    # Handle company text extraction
                    company_text = "Unknown Company"
                    if company_elem:
                        if isinstance(company_elem, str):  # Text found with " at Company"
                            import re
                            match = re.search(r'at\s+([^•]+)', company_elem)
                            if match:
                                company_text = match.group(1).strip()
                        else:
                            company_text = company_elem.get_text(strip=True)
                    
                    job = Job(
                        id=job_id or job_url or title_elem.get_text(strip=True),
                        title=title_elem.get_text(strip=True),
                        company=company_text,
                        url=job_url,
                        source=feed.name,
                        date=""
                    )
                    jobs.append(job)
        else:
            # Check if we're on a block page
            if soup.find(text=lambda t: t and any(term in t.lower() for term in ["captcha", "blocked", "rate limit", "security check"])):
                logger.warning("Remotive is showing a block or CAPTCHA page")
            else:
                # Try a generic search for any job data
                job_sections = soup.select("section, .job-section, .jobs-list > div")
                for section in job_sections:
                    title_elem = section.find(["h2", "h3", "h4"])
                    if not title_elem:
                        continue
                        
                    company = "Unknown Company"
                    company_elem = section.find(["span", "div"], string=lambda s: s and len(s) < 50)
                    if company_elem:
                        company = company_elem.text.strip()
                    
                    link = section.find("a", href=True)
                    job_url = link["href"] if link else ""
                    if job_url and job_url.startswith("/"):
                        job_url = f"https://remotive.com{job_url}"
                    
                    job = Job(
                        id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                        title=title_elem.text.strip(),
                        company=company,
                        url=job_url,
                        source=feed.name,
                        date=""
                    )
                    jobs.append(job)
                
                if not jobs:
                    text_content = soup.get_text()[:200]
                    logger.warning(f"No jobs found on Remotive. Page starts with: {text_content}...")
            
        return jobs

    def _parse_workingnomads(self, soup, feed):
        """Parse jobs from workingnomads.com with robust selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_=lambda c: c and "job" in c) or
            soup.find_all("article", class_=lambda c: c and "job" in c) or
            soup.select(".job-list .job, .jobs-container .job-item")
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on WorkingNomads using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on WorkingNomads")
        
        for card in job_cards:
            # Try various title element possibilities
            title_elem = (
                card.find("h2", class_="job-title") or
                card.find("h3", class_="job-title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and "title" in c) or
                card.find("a", class_=lambda c: c and "title" in c) or
                card.find(["h2", "h3", "h4"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company-name") or
                card.find(["div", "span"], class_=lambda c: c and "company" in c) or
                card.find(string=lambda s: s and " at " in s)
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem and link_elem:
                # If company not found, use fallback
                company_text = company_elem.text.strip() if company_elem else "Unknown Company"
                if isinstance(company_elem, str):
                    import re
                    match = re.search(r'at\s+([^•]+)', company_elem)
                    if match:
                        company_text = match.group(1).strip()
                
                job_url = link_elem.get("href", "")
                if job_url.startswith("/"):
                    job_url = f"https://www.workingnomads.com{job_url}"
                    
                job = Job(
                    id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                    title=title_elem.text.strip(),
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_cryptojobslist(self, soup, feed):
        """Parse jobs from cryptojobslist.com with robust selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_=lambda c: c and "job" in c) or
            soup.find_all("article", class_=lambda c: c and "job" in c) or
            soup.select(".job-listing-item, .job-list li")
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on CryptoJobsList using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on CryptoJobsList")
        
        for card in job_cards:
            # Try various title element possibilities
            title_elem = (
                card.find("h2", class_="job-title") or
                card.find("h3", class_="job-title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and "title" in c) or
                card.find("a", class_=lambda c: c and "title" in c) or
                card.find(["h2", "h3", "h4"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company-name") or
                card.find(["div", "span"], class_=lambda c: c and "company" in c)
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem and link_elem:
                # If company not found, use fallback
                company_text = company_elem.text.strip() if company_elem else "Unknown Company"
                
                job_url = link_elem.get("href", "")
                if job_url.startswith("/"):
                    job_url = f"https://cryptojobslist.com{job_url}"
                    
                job = Job(
                    id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                    title=title_elem.text.strip(),
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_remote3(self, soup, feed):
        """Parse jobs from remote3.co with robust selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_=lambda c: c and "job" in c) or
            soup.find_all("article", class_=lambda c: c and "job" in c) or
            soup.select(".job-listing, .jobs-container .job")
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on Remote3 using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on Remote3")
        
        for card in job_cards:
            # Try various title element possibilities
            title_elem = (
                card.find("h2", class_="job-title") or
                card.find("h3", class_="job-title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and "title" in c) or
                card.find("a", class_=lambda c: c and "title" in c) or
                card.find(["h2", "h3", "h4"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company-name") or
                card.find(["div", "span"], class_=lambda c: c and "company" in c)
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem and link_elem:
                # If company not found, use fallback
                company_text = company_elem.text.strip() if company_elem else "Unknown Company"
                
                job_url = link_elem.get("href", "")
                if job_url.startswith("/"):
                    job_url = f"https://www.remote3.co{job_url}"
                    
                job = Job(
                    id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                    title=title_elem.text.strip(),
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_mindtel(self, soup, feed):
        """Parse jobs from mindtel.atsmantra.com with robust selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_=lambda c: c and "job" in c) or
            soup.find_all("div", class_=lambda c: c and "vacancy" in c) or
            soup.select(".job-list .job, .vacancy-item")
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on Mindtel using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on Mindtel")
        
        for card in job_cards:
            # Try various title element possibilities
            title_elem = (
                card.find("h2", class_="job-title") or
                card.find("h3", class_="job-title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and "title" in c) or
                card.find("a", class_=lambda c: c and "title" in c) or
                card.find(["h2", "h3", "h4"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company-name") or
                card.find(["div", "span"], class_=lambda c: c and "company" in c)
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem and link_elem:
                # If company not found, use fallback - for Mindtel, the company is often Mindtel itself
                company_text = company_elem.text.strip() if company_elem else "Mindtel"
                
                job_url = link_elem.get("href", "")
                if job_url.startswith("/"):
                    job_url = f"https://mindtel.atsmantra.com{job_url}"
                    
                job = Job(
                    id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                    title=title_elem.text.strip(),
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_nodesk(self, soup, feed):
        """Parse jobs from nodesk.co with robust selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_=lambda c: c and "job" in c) or
            soup.find_all("article", class_=lambda c: c and "job" in c) or
            soup.select(".job-list .job, .jobs-container .job-item")
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on Nodesk using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on Nodesk")
        
        for card in job_cards:
            # Try various title element possibilities
            title_elem = (
                card.find("h2", class_="job-title") or
                card.find("h3", class_="job-title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and "title" in c) or
                card.find("a", class_=lambda c: c and "title" in c) or
                card.find(["h2", "h3", "h4"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company-name") or
                card.find(["div", "span"], class_=lambda c: c and "company" in c)
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem and link_elem:
                # If company not found, use fallback
                company_text = company_elem.text.strip() if company_elem else "Unknown Company"
                
                job_url = link_elem.get("href", "")
                if job_url.startswith("/"):
                    job_url = f"https://nodesk.co{job_url}"
                    
                job = Job(
                    id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                    title=title_elem.text.strip(),
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_cryptocurrencyjobs(self, soup, feed):
        """Parse jobs from cryptocurrencyjobs.co with robust selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_=lambda c: c and "job" in c) or
            soup.find_all("article", class_=lambda c: c and "job" in c) or
            soup.select(".job-listing, .jobs-container .job-item")
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on CryptocurrencyJobs using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on CryptocurrencyJobs")
        
        for card in job_cards:
            # Try various title element possibilities
            title_elem = (
                card.find("h2", class_="job-title") or
                card.find("h3", class_="job-title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and "title" in c) or
                card.find("a", class_=lambda c: c and "title" in c) or
                card.find(["h2", "h3", "h4"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company-name") or
                card.find(["div", "span"], class_=lambda c: c and "company" in c)
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem and link_elem:
                # If company not found, use fallback
                company_text = company_elem.text.strip() if company_elem else "Unknown Company"
                
                job_url = link_elem.get("href", "")
                if job_url.startswith("/"):
                    job_url = f"https://cryptocurrencyjobs.co{job_url}"
                    
                job = Job(
                    id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                    title=title_elem.text.strip(),
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_nodesk_substack(self, soup, feed):
        """Parse jobs from nodesk.substack.com with robust selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_=lambda c: c and "job" in c) or
            soup.find_all("article", class_=lambda c: c and ("post" in c or "job" in c)) or
            soup.select(".post-preview, .job-listing, .job")
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on Nodesk Substack using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on Nodesk Substack")
        
        for card in job_cards:
            # Try various title element possibilities
            title_elem = (
                card.find("h2", class_="job-title") or
                card.find("h3", class_="job-title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and ("title" in c or "post" in c)) or
                card.find("a", class_=lambda c: c and ("title" in c or "post" in c)) or
                card.find(["h2", "h3", "h4"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company-name") or
                card.find(["div", "span"], class_=lambda c: c and "company" in c) or
                # For substack, we might need to extract from the title
                None
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem and link_elem:
                # For substack, try to extract company from title if not found
                company_text = "Unknown Company"
                if company_elem:
                    company_text = company_elem.text.strip()
                else:
                    # Check if title contains company info (e.g., "Job Title at Company")
                    title_text = title_elem.text.strip()
                    import re
                    match = re.search(r'at\s+([^|•]+)', title_text)
                    if match:
                        company_text = match.group(1).strip()
                
                job_url = link_elem.get("href", "")
                if job_url.startswith("/"):
                    job_url = f"https://nodesk.substack.com{job_url}"
                    
                job = Job(
                    id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                    title=title_elem.text.strip(),
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_remotehabits(self, soup, feed):
        """Parse jobs from remotehabits.com with robust selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_=lambda c: c and "job" in c) or
            soup.find_all("article", class_=lambda c: c and "job" in c) or
            soup.select(".job-listing, .job-preview, .job")
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on RemoteHabits using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on RemoteHabits")
        
        for card in job_cards:
            # Try various title element possibilities
            title_elem = (
                card.find("h2", class_="job-title") or
                card.find("h3", class_="job-title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and "title" in c) or
                card.find("a", class_=lambda c: c and "title" in c) or
                card.find(["h2", "h3", "h4"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company-name") or
                card.find(["div", "span"], class_=lambda c: c and "company" in c)
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem and link_elem:
                # If company not found, use fallback
                company_text = company_elem.text.strip() if company_elem else "Unknown Company"
                
                job_url = link_elem.get("href", "")
                if job_url.startswith("/"):
                    job_url = f"https://remotehabits.com{job_url}"
                    
                job = Job(
                    id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                    title=title_elem.text.strip(),
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_jobspresso(self, soup, feed):
        """Parse jobs from jobspresso.co with robust selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_=lambda c: c and "job" in c) or
            soup.find_all("article", class_=lambda c: c and "job" in c) or
            soup.select(".job-listing, .jobs .job-item")
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on Jobspresso using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on Jobspresso")
        
        for card in job_cards:
            # Try various title element possibilities
            title_elem = (
                card.find("h2", class_="job-title") or
                card.find("h3", class_="job-title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and "title" in c) or
                card.find("a", class_=lambda c: c and "title" in c) or
                card.find(["h2", "h3", "h4"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company-name") or
                card.find(["div", "span"], class_=lambda c: c and "company" in c)
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem and link_elem:
                # If company not found, use fallback
                company_text = company_elem.text.strip() if company_elem else "Unknown Company"
                
                job_url = link_elem.get("href", "")
                if job_url.startswith("/"):
                    job_url = f"https://jobspresso.co{job_url}"
                    
                job = Job(
                    id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                    title=title_elem.text.strip(),
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_weworkremotely_support(self, soup, feed):
        """Parse jobs from weworkremotely.com customer support section with robust selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_=lambda c: c and "job" in c) or
            soup.find_all("li", class_=lambda c: c and "feature" in c) or
            soup.select(".jobs .job, article.job, .feature")
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on WeWorkRemotely using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on WeWorkRemotely")
        
        for card in job_cards:
            # Try various title element possibilities
            title_elem = (
                card.find("h2", class_="job-title") or
                card.find("h3", class_="job-title") or
                card.find("span", class_="title") or
                card.find(["h2", "h3", "h4", "span"], class_=lambda c: c and "title" in c) or
                card.find("a", class_=lambda c: c and "title" in c) or
                card.find(["h2", "h3", "h4", "span"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company") or
                card.find(["div", "span"], class_=lambda c: c and "company" in c)
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem and link_elem:
                # If company not found, use fallback
                company_text = company_elem.text.strip() if company_elem else "Unknown Company"
                
                job_url = link_elem.get("href", "")
                if job_url.startswith("/"):
                    job_url = f"https://weworkremotely.com{job_url}"
                    
                job = Job(
                    id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                    title=title_elem.text.strip(),
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _fetch_headless(self, feed: Feed) -> List[Job]:
        """Fetch jobs from a page requiring JavaScript rendering using Playwright with stealth and evasion."""
        domain = feed.url.split("/")[2]
        html = None
        
        try:
            # Get a browser context from the pool
            context = browser_pool.get_context(domain, headers=feed.headers, cookies=feed.cookies)
            
            # Create a new page in the context
            page = context.new_page()
            stealth_sync(page)  # Apply stealth
            
            try:
                # Visit the page and wait for load
                logger.info(f"Navigating to {feed.url}")
                page.goto(feed.url, wait_until="domcontentloaded", timeout=60000)
                
                # Human-like behavior
                time.sleep(random.uniform(2, 4))  # Initial wait like a human
                
                # Scroll more naturally (diagonal movements, different speeds)
                total_height = page.evaluate("document.body.scrollHeight")
                viewport_height = page.evaluate("window.innerHeight")
                scroll_positions = []
                
                # Calculate a few natural scroll positions (not perfectly equal)
                for i in range(1, min(5, int(total_height/viewport_height) + 1)):
                    target_position = int(i * viewport_height * random.uniform(0.8, 1.0))
                    if target_position > total_height:
                        target_position = total_height
                    scroll_positions.append(target_position)
                
                # Execute the scrolls with natural timing
                for position in scroll_positions:
                    # Random slight horizontal scroll to appear more human
                    horizontal_jitter = random.randint(-10, 10)
                    # Scroll with smooth animation
                    page.evaluate(f"""
                        window.scrollTo({{
                            left: {horizontal_jitter},
                            top: {position},
                            behavior: 'smooth'
                        }});
                    """)
                    # Wait a bit after each scroll
                    time.sleep(random.uniform(1.0, 2.5))
                
                # Perform a few random mouse movements to simulate human behavior
                for _ in range(random.randint(2, 4)):
                    try:
                        x = random.randint(100, 800)
                        y = random.randint(100, 600)
                        page.mouse.move(x, y)
                        time.sleep(random.uniform(0.3, 1.0))
                    except Exception:
                        pass  # Ignore mouse movement failures
                
                # Wait for potential infinite scroll or lazy loading to complete
                time.sleep(random.uniform(1.5, 3.0))
                
                # Save the HTML for debugging regardless of what happens next
                html = page.content()
                debug_dir = pathlib.Path("debug")
                debug_dir.mkdir(exist_ok=True)
                with open(debug_dir / f"{feed.name}_content.html", "w", encoding="utf-8") as f:
                    f.write(html)
                logger.info(f"Saved HTML debug content to {debug_dir}/{feed.name}_content.html")
                
                # Wait for the main job selector to appear with broader selector options
                selector_map = {
                    "indeed": "div.job_seen_beacon, div.jobsearch-ResultsList, div.tapItem, li.result",
                    "remotive": "div.job-card, li.job-li, div.job, div.ce",
                    "remoteok": "tr.job, div.job-container",
                    "workingnomads": "div.job-card, div.job-list",
                    "cryptojobslist": "div.job-card, div.job-listing-item",
                    "jobspresso": "div.job-card, article.job",
                }
                selector = selector_map.get(feed.parser)
                if selector:
                    try:
                        element = page.wait_for_selector(selector, timeout=15000)
                        if element:
                            logger.info(f"Found job elements with selector '{selector}'")
                        
                        # Save cookies after successful page load with content
                        browser_pool.save_cookies(domain)
                        
                    except Exception as e:
                        logger.warning(f"Selector {selector} not found for {feed.name}: {e}")
                        
                # Check for CAPTCHA or security challenges
                if self._detect_security_challenge(page):
                    logger.warning(f"Security challenge detected on {feed.name}")
                
            except Exception as e:
                logger.error(f"Failed to fetch {feed.name} with headless browser: {e}")
                raise
            finally:
                # Close the page but keep the context in the pool
                page.close()
                
        except Exception as e:
            logger.error(f"Error in _fetch_headless for {feed.name}: {e}")
            raise
            
        # Use the same HTML parser logic as _fetch_html
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        parser_map = {
            "indeed": self._parse_indeed,
            "remotive": self._parse_remotive,
            "remoteok": self._parse_remoteok,
            "workingnomads": self._parse_workingnomads,
            "cryptojobslist": self._parse_cryptojobslist,
            "jobspresso": self._parse_jobspresso,
        }
        parser = parser_map.get(feed.parser)
        if parser:
            return parser(soup, feed)
        else:
            raise ValueError(f"No parser implemented for {feed.parser}")
            
    def _detect_security_challenge(self, page):
        """Check if the page contains a security challenge or CAPTCHA.
        
        Args:
            page: Playwright page object
            
        Returns:
            bool: True if a security challenge is detected
        """
        try:
            # Check for common CAPTCHA or security challenge indicators
            challenge_indicators = [
                "captcha", 
                "security check", 
                "bot check", 
                "robot", 
                "human verification",
                "prove you're human",
                "verify you are a human",
                "unusual activity",
                "security challenge",
                "recaptcha"
            ]
            
            # Check body text for these indicators
            body_text = page.evaluate("""() => { 
                return document.body.innerText.toLowerCase(); 
            }""")
            
            for indicator in challenge_indicators:
                if indicator in body_text:
                    return True
            
            # Check for known CAPTCHA elements
            captcha_selectors = [
                "iframe[src*='captcha']",
                "iframe[src*='recaptcha']",
                "div.g-recaptcha",
                "div.h-captcha",
                "div[class*='captcha']",
                "input[name*='captcha']"
            ]
            
            for selector in captcha_selectors:
                if page.query_selector(selector):
                    return True
            
            return False
        except Exception as e:
            logger.warning(f"Error checking for security challenge: {e}")
            return False 