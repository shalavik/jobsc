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
import hashlib
import sys
import re

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('[%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

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
        
        # Proxy rotation support
        self.proxies = []
        self.current_proxy_index = 0
        self._load_proxies()
        
    def _load_proxies(self):
        """Load proxies from environment or file."""
        # Try to load from environment first
        proxy_list = os.getenv("PROXY_LIST", "").strip()
        if proxy_list:
            self.proxies = [p.strip() for p in proxy_list.split(",") if p.strip()]
            
        # If no proxies in env, try to load from file
        if not self.proxies:
            proxy_file = pathlib.Path("proxies.txt")
            if proxy_file.exists():
                try:
                    with open(proxy_file, "r") as f:
                        self.proxies = [line.strip() for line in f if line.strip()]
                except Exception as e:
                    logger.warning(f"Failed to load proxies from file: {e}")
        
        logger.info(f"Loaded {len(self.proxies)} proxies")
        
    def get_next_proxy(self):
        """Get the next proxy in rotation."""
        if not self.proxies:
            return None
            
        proxy = self.proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        return proxy
        
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
            
            # Get proxy if available
            proxy = self.get_next_proxy() if "indeed.com" in domain else None
            proxy_config = None
            if proxy:
                proxy_config = {
                    "server": proxy,
                    "username": os.getenv("PROXY_USERNAME", ""),
                    "password": os.getenv("PROXY_PASSWORD", "")
                }
                logger.info(f"Using proxy for {domain}: {proxy}")
            
            # Create a new context with proxy if available
            context = self.browser.new_context(
                user_agent=standard_ua,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                geolocation={"latitude": 40.730610, "longitude": -73.935242},  # NYC
                color_scheme="no-preference",
                device_scale_factor=1,
                proxy=proxy_config
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
            
        # Use a very short timeout to avoid deadlocks
        lock_acquired = self.lock.acquire(timeout=0.1)  # Reduced from 0.5 to 0.1
        if not lock_acquired:
            logger.debug(f"Could not acquire lock to save cookies for {domain} (non-blocking)")
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
                    logger.debug(f"Saved cookies for {domain}")
                except Exception as e:
                    logger.debug(f"Failed to save cookies for {domain}: {e}")
        except Exception as e:
            logger.debug(f"Error saving cookies for {domain}: {e}")
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
                # Try to save cookies before closing (non-blocking)
                try:
                    self.save_cookies(domain)
                except Exception as e:
                    logger.debug(f"Failed to save cookies during cleanup for {domain}: {e}")
                
                context.close()
                del self.contexts[domain]
                logger.debug(f"Cleaned up old context for {domain}")
            except Exception as e:
                logger.warning(f"Failed to close context for {domain}: {e}")
    
    def cleanup(self):
        """Clean up all browser contexts and close the browser."""
        if not self._initialized:
            return
            
        # Use a very short timeout to avoid deadlocks in cleanup
        lock_acquired = self.lock.acquire(timeout=0.05)  # Very short timeout for cleanup
        if not lock_acquired:
            logger.warning("Could not acquire lock for browser pool cleanup - forcing cleanup")
            # Force cleanup without saving cookies to avoid hanging
            try:
                if hasattr(self, 'contexts'):
                    for domain, (context, _) in list(self.contexts.items()):
                        try:
                            context.close()
                        except Exception as e:
                            logger.debug(f"Failed to force close context for {domain}: {e}")
                    self.contexts.clear()
                
                if self.browser:
                    self.browser.close()
                if self.playwright:
                    self.playwright.stop()
            except Exception as e:
                logger.warning(f"Failed to force close browser: {e}")
            self._initialized = False
            return
            
        try:
            # Save cookies for active contexts (with timeout protection)
            active_domains = list(self.contexts.keys())
            for domain in active_domains:
                try:
                    # Only try to save cookies if we're not in test mode
                    if not self.test_mode:
                        # Use a separate thread with timeout to avoid hanging
                        import threading
                        save_thread = threading.Thread(target=self.save_cookies, args=(domain,))
                        save_thread.daemon = True
                        save_thread.start()
                        save_thread.join(timeout=1.0)  # 1 second timeout
                        
                        if save_thread.is_alive():
                            logger.debug(f"Cookie saving timed out for {domain}")
                    
                    # Close context
                    context, _ = self.contexts[domain]
                    context.close()
                except Exception as e:
                    logger.debug(f"Failed to close context for {domain}: {e}")
            
            self.contexts.clear()
            
            try:
                if self.browser:
                    self.browser.close()
                if self.playwright:
                    self.playwright.stop()
            except Exception as e:
                logger.warning(f"Failed to close browser or playwright: {e}")
            
            self._initialized = False
            logger.debug("Browser pool cleanup completed")
        except Exception as e:
            logger.warning(f"Error during browser pool cleanup: {e}")
        finally:
            try:
                self.lock.release()
            except Exception:
                pass  # Lock might already be released or in an invalid state

# Create global browser pool
browser_pool = BrowserPool(max_contexts=3)

class Fetcher:
    """Handles fetching jobs from different types of feeds."""
    
    def __init__(self):
        """Initialize the fetcher."""
        self.rate_limiter = RateLimiter()
    
    def fetch(self, feed: Feed, max_retries: int = 3) -> List[Job]:
        """Fetch jobs from a feed, using fetch_method if present."""
        print(f"[FETCH] Starting fetch for {feed.name} with method {feed.fetch_method}")
        logger.info(f"[FETCH] Starting fetch for {feed.name} with method {feed.fetch_method}")
        fetch_method = getattr(feed, 'fetch_method', None) or getattr(feed, 'type', None)
        print(f"[FETCH] Resolved fetch_method to: {fetch_method}")
        logger.info(f"[FETCH] Resolved fetch_method to: {fetch_method}")
        retries = 0
        while retries < max_retries:
            try:
                if feed.rate_limit:
                    self.rate_limiter.wait_if_needed(feed.name, feed.rate_limit)
                print(f"[FETCH] About to fetch using method: {fetch_method}")
                logger.info(f"[FETCH] About to fetch using method: {fetch_method}")
                if fetch_method == "rss":
                    jobs = self._fetch_rss(feed)
                elif fetch_method == "json":
                    jobs = self._fetch_json(feed)
                elif fetch_method == "html":
                    jobs = self._fetch_html(feed)
                elif fetch_method == "headless":
                    jobs = self._fetch_headless(feed)
                else:
                    print(f"[FETCH] Unsupported fetch_method: {fetch_method}")
                    logger.error(f"[FETCH] Unsupported fetch_method: {fetch_method}")
                    raise ValueError(f"Unsupported fetch_method: {fetch_method}")
                print(f"[FETCH] Parsed {len(jobs)} jobs for {feed.name}")
                logger.info(f"[FETCH] Parsed {len(jobs)} jobs for {feed.name}")
                return jobs
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
        """Fetch jobs from a JSON feed or local file.
        
        Args:
            feed: Feed configuration object
            
        Returns:
            List of Job objects
            
        Raises:
            ValueError: If the JSON structure is invalid
            requests.RequestException: If the request fails
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
        except requests.RequestException as e:
            logger.error(f"Request failed for {feed.name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing {feed.name}: {e}")
            raise
    
    def _fetch_html(self, feed: Feed) -> List[Job]:
        """Fetch jobs from HTML source."""
        try:
            response = requests.get(
                feed.url,
                headers=feed.headers,
                cookies=feed.cookies,
                timeout=30
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Map feed parser to appropriate parsing function
            parser_map = {
                "indeed": self._parse_indeed,
                "remoteok": self._parse_remoteok,
                "snaphunt": self._parse_snaphunt,
                "alljobs": self._parse_alljobs,
                "remotive": self._parse_remotive,
                "workingnomads": self._parse_workingnomads,
                "cryptocurrencyjobs": self._parse_cryptocurrencyjobs,
                "nodesk_substack": self._parse_nodesk_substack,
                "remotehabits": self._parse_remotehabits,
                "jobspresso": self._parse_jobspresso,
                "weworkremotely_support": self._parse_weworkremotely_support
            }
            
            if feed.parser in parser_map:
                return parser_map[feed.parser](soup, feed)
            else:
                logger.warning(f"No parser found for {feed.parser}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching HTML from {feed.url}: {str(e)}")
            return []

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
                card.find(["h2", "h3", "h4"], string=lambda s: s and len(s) > 4)  # Any heading with reasonable text
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
        """Parse jobs from snaphunt.com with improved React app handling."""
        jobs = []
        
        # Check if this is the React app loading page
        if "window.__PRELOADED_STATE__" in str(soup):
            logger.info("Detected Snaphunt React app, extracting from preloaded state")
            
            # Try to extract job data from the preloaded state
            script_tags = soup.find_all("script")
            for script in script_tags:
                if script.string and "window.__PRELOADED_STATE__" in script.string:
                    try:
                        # Extract the JSON data
                        script_content = script.string
                        start = script_content.find("window.__PRELOADED_STATE__ = ") + len("window.__PRELOADED_STATE__ = ")
                        end = script_content.find(";", start)
                        json_str = script_content[start:end]
                        
                        import json
                        data = json.loads(json_str)
                        
                        # Extract jobs from the state
                        if "jobs" in data and "jobs" in data["jobs"]:
                            job_list = data["jobs"]["jobs"]
                            for job_data in job_list:
                                if isinstance(job_data, dict):
                                    job = Job(
                                        id=job_data.get("jobId", ""),
                                        title=job_data.get("jobTitle", ""),
                                        company=job_data.get("companyName", "Unknown Company"),
                                        url=f"https://snaphunt.com/jobs/{job_data.get('jobId', '')}",
                                        source=feed.name,
                                        date=job_data.get("createdAt", "")
                                    )
                                    jobs.append(job)
                        
                        # Also check seoJob for featured job
                        if "seoJobManager" in data and "seoJob" in data["seoJobManager"]:
                            seo_job = data["seoJobManager"]["seoJob"]
                            if seo_job:
                                job = Job(
                                    id=seo_job.get("jobId", ""),
                                    title=seo_job.get("jobTitle", ""),
                                    company="Unknown Company",
                                    url=f"https://snaphunt.com/jobs/{seo_job.get('jobId', '')}",
                                    source=feed.name,
                                    date=seo_job.get("createdAt", "")
                                )
                                jobs.append(job)
                                
                    except Exception as e:
                        logger.error(f"Error parsing Snaphunt preloaded state: {e}")
                        
            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs from Snaphunt preloaded state")
                return jobs
        
        # Fallback to traditional parsing if React state extraction fails
        logger.warning("Falling back to traditional Snaphunt parsing")
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_=lambda c: c and "job" in c.lower()) or
            soup.find_all("article", class_=lambda c: c and "job" in c.lower()) or
            soup.find_all("li", class_=lambda c: c and "job" in c.lower())
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on Snaphunt. Page contains {len(soup.find_all('div'))} divs")
            # Debug: show some div classes
            divs_with_classes = [div.get('class') for div in soup.find_all('div') if div.get('class')]
            logger.debug(f"Found {len(divs_with_classes)} divs with classes on Snaphunt")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on Snaphunt")
        
        for i, card in enumerate(job_cards):
            try:
                # Extract job title
                title_elem = (
                    card.find("h2", class_="job-title") or
                    card.find("h3", class_="job-title") or
                    card.find(["h1", "h2", "h3", "h4"], class_=lambda c: c and "title" in c) or
                    card.find("a", class_=lambda c: c and "title" in c) or
                    card.find(["h1", "h2", "h3", "h4"])
                )
                
                if not title_elem:
                    continue
                    
                title_text = title_elem.get_text(strip=True)
                if not title_text or len(title_text) < 3:
                    continue
                
                # Extract company name
                company_elem = (
                    card.find("div", class_="company-name") or
                    card.find("span", class_="company-name") or
                    card.find(["div", "span", "p"], class_=lambda c: c and "company" in c) or
                    card.find("div", class_="employer")
                )
                
                company_text = company_elem.get_text(strip=True) if company_elem else "Unknown Company"
                
                # Extract job URL
                link_elem = (
                    card.find("a", class_="job-link") or
                    card.find("a", href=True) or
                    title_elem.find("a", href=True) if title_elem.name == "a" else title_elem
                )
                
                job_url = ""
                if link_elem and link_elem.get("href"):
                    job_url = link_elem.get("href", "")
                    if job_url.startswith("/"):
                        job_url = f"https://snaphunt.com{job_url}"
                    elif not job_url.startswith("http"):
                        job_url = f"https://snaphunt.com/{job_url}"
                
                # Create job ID
                job_id = job_url.split("/")[-1] if job_url else f"snaphunt_{hash(title_text)}_{i}"
                
                job = Job(
                    id=job_id,
                    title=title_text,
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
                
            except Exception as e:
                logger.debug(f"Error parsing Snaphunt card {i}: {e}")
                continue
        
        logger.info(f"Successfully parsed {len(jobs)} jobs from Snaphunt")
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
        """Parse jobs from remotive.com with updated selectors (2024)."""
        jobs = []
        # Find all job cards by the new class (multiple background variants)
        # Use a set to avoid duplicates
        job_cards_set = set()
        for card in (soup.find_all("div", class_="job-tile remotive-bg-sand-light") +
                     soup.find_all("div", class_="job-tile remotive-bg-light") +
                     soup.find_all("div", class_="job-tile")):
            job_cards_set.add(card)
        job_cards = list(job_cards_set)
        allowed_location_keywords = ["worldwide", "global", "remote", "anywhere", "", "usa", "uk", "canada", "india", "emea", "apac", "thailand", "south africa", "philippines", "netherlands", "spain", "australia"]
        allowed_categories = ["customer service", "customer support"]
        if job_cards:
            logger.info(f"Found {len(job_cards)} Remotive job cards (2024 structure)")
            for card in job_cards:
                # Title and company
                title_elem = card.find("a", class_="remotive-url-visit")
                if not title_elem:
                    continue
                # Look for spans with remotive-bold class or empty class
                title_spans = title_elem.find_all("span", class_="remotive-bold")
                if not title_spans:
                    # Fallback to spans with empty class or any span
                    title_spans = title_elem.find_all("span", class_="") or title_elem.find_all("span")
                if not title_spans:
                    continue
                title_text = title_spans[0].get_text(strip=True)
                # Company: look for the company name (skip the "•" separator)
                company_text = "Unknown Company"
                # Try to find company in the visible desktop span (3rd span, skipping title and "•")
                if len(title_spans) >= 3:
                    company_text = title_spans[2].get_text(strip=True)
                else:
                    # Try fallback to mobile-only span
                    company_fallback = title_elem.find("span", class_="tw-block md:tw-hidden")
                    if company_fallback:
                        company_text = company_fallback.get_text(strip=True)
                job_url = title_elem.get("href", "")
                if job_url and job_url.startswith("/"):
                    job_url = f"https://remotive.com{job_url}"
                job_id = job_url.split("/")[-1] if job_url else title_text

                # Gather all category tags
                category_spans = card.find_all("span", class_="job-tile-category")
                categories = [a.get_text(strip=True).lower() for span in category_spans for a in span.find_all("a")]
                has_customer = any(any(allowed in cat for allowed in allowed_categories) for cat in categories)

                # Gather all location tags
                location_spans = card.find_all("span", class_="job-tile-location")
                locations = [span.get_text(strip=True).lower() for span in location_spans]
                has_allowed_location = any(
                    any(keyword in loc for keyword in allowed_location_keywords)
                    for loc in locations
                ) or not locations  # Accept if no location tags

                if not has_customer:
                    logger.debug(f"Filtered out job '{title_text}' at '{company_text}': missing 'Customer Service' category")
                    continue
                if not has_allowed_location:
                    logger.debug(f"Filtered out job '{title_text}' at '{company_text}': missing allowed location")
                    continue
                job = Job(
                    id=job_id,
                    title=title_text,
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
            logger.info(f"Parsed {len(jobs)} filtered Remotive jobs (Customer Service/Support + allowed location). Example jobs: {jobs[:3]}")
        else:
            logger.warning("No job cards found on Remotive using updated selectors (2024). Fallback to generic extraction.")
        return jobs

    def _parse_workingnomads(self, soup, feed):
        """Parse jobs from workingnomads.com with enhanced selectors and filtering."""
        jobs = []
        
        # Enhanced selectors for WorkingNomads
        job_cards = (
            # Primary selectors
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_="job-listing") or
            soup.find_all("div", class_="job-item") or
            soup.find_all("article", class_="job") or
            
            # Alternative selectors
            soup.find_all("div", class_="job-wrapper") or
            soup.find_all("div", class_="job-post") or
            soup.find_all("li", class_="job") or
            soup.find_all("tr", class_="job") or  # Table rows
            
            # Generic job containers with improved filters
            soup.find_all("div", class_=lambda c: c and "job" in c.lower() and "ad" not in c.lower()) or
            soup.find_all("article", class_=lambda c: c and "job" in c.lower()) or
            soup.find_all("li", class_=lambda c: c and "listing" in c.lower()) or
            
            # Table-based layouts (common on WorkingNomads)
            soup.select("table tr:has(td)") or
            soup.select("tbody tr") or
            
            # Fallback to any structured content
            soup.find_all("div", attrs={"data-job": True}) or
            soup.find_all("div", attrs={"data-id": True})
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on WorkingNomads using enhanced selectors")
            # Try even broader selectors as last resort
            job_cards = soup.find_all("tr") or soup.find_all("div", class_=True)
            if job_cards:
                # Filter for elements that might contain job data
                job_cards = [card for card in job_cards if self._might_be_job_card(card)]
                logger.info(f"Found {len(job_cards)} potential job cards using fallback selectors")
            else:
                return jobs
        else:
            logger.info(f"Found {len(job_cards)} job cards on WorkingNomads")
        
        for card in job_cards:
            try:
                # Enhanced job extraction with multiple fallback strategies
                job_data = self._extract_workingnomads_job(card)
                
                if job_data and self._is_valid_workingnomads_job(job_data):
                    job = Job(
                        id=job_data.get("url", "") or f"workingnomads_{hash(job_data.get('title', ''))}",
                        title=job_data.get("title", "").strip(),
                        company=job_data.get("company", "Unknown Company").strip(),
                        url=job_data.get("url", ""),
                        source=feed.name,
                        date=""
                    )
                    jobs.append(job)
                    logger.debug(f"WorkingNomads: Added job - {job.title} at {job.company}")
                
            except Exception as e:
                logger.warning(f"WorkingNomads: Error parsing job card: {e}")
                continue
        
        logger.info(f"WorkingNomads: Successfully parsed {len(jobs)} jobs")
        return jobs
    
    def _might_be_job_card(self, element):
        """Check if an element might be a job card based on content patterns."""
        try:
            text = element.get_text().lower() if element else ""
            
            # Must contain job-like terms
            job_indicators = ["developer", "engineer", "designer", "manager", "analyst", "specialist", 
                             "coordinator", "director", "lead", "senior", "junior", "intern",
                             "remote", "full-time", "part-time", "contract", "freelance"]
            
            has_job_indicator = any(indicator in text for indicator in job_indicators)
            
            # Should have reasonable length (not just a header or footer)
            has_content = len(text.strip()) > 20
            
            # Exclude navigation, ads, and other non-job content
            exclude_terms = ["cookie", "privacy", "terms", "navigation", "menu", "footer", 
                           "header", "sidebar", "advertisement", "powered by"]
            
            is_excluded = any(term in text for term in exclude_terms)
            
            return has_job_indicator and has_content and not is_excluded
            
        except Exception:
            return False
    
    def _extract_workingnomads_job(self, card):
        """Extract job data from a WorkingNomads job card with multiple strategies."""
        job_data = {}
        
        try:
            # Strategy 1: Look for specific selectors
            title_elem = (
                card.find("h3") or 
                card.find("h2") or 
                card.find("h4") or
                card.find("a", class_=lambda c: c and "title" in c.lower()) or
                card.find(class_=lambda c: c and "title" in c.lower()) or
                card.find("strong") or
                card.find("b")
            )
            
            if title_elem:
                job_data["title"] = title_elem.get_text().strip()
            
            # Strategy 2: Look for company information
            company_elem = (
                card.find(class_=lambda c: c and "company" in c.lower()) or
                card.find("span", class_=lambda c: c and "employer" in c.lower()) or
                card.find("div", class_=lambda c: c and "company" in c.lower())
            )
            
            if company_elem:
                job_data["company"] = company_elem.get_text().strip()
            
            # Strategy 3: Look for location (often "Remote" for this site)
            location_elem = (
                card.find(class_=lambda c: c and "location" in c.lower()) or
                card.find("span", class_=lambda c: c and "remote" in c.lower())
            )
            
            if location_elem:
                job_data["location"] = location_elem.get_text().strip()
            else:
                job_data["location"] = "Remote"  # Default for WorkingNomads
            
            # Strategy 4: Look for links
            link_elem = card.find("a", href=True)
            if link_elem and link_elem.get("href"):
                href = link_elem.get("href")
                if href.startswith("/"):
                    job_data["url"] = f"https://workingnomads.com{href}"
                elif href.startswith("http"):
                    job_data["url"] = href
                else:
                    job_data["url"] = f"https://workingnomads.com/{href}"
            
            # Strategy 5: Extract description from remaining text
            description_text = card.get_text().strip()
            if description_text and len(description_text) > 50:
                # Clean up the description
                lines = [line.strip() for line in description_text.split('\n') if line.strip()]
                job_data["description"] = ' '.join(lines[:5])  # First 5 lines
            
            # Strategy 6: Look for salary information
            salary_patterns = [
                r'\$[\d,]+(?:\s*-\s*\$[\d,]+)?',
                r'[\d,]+k?(?:\s*-\s*[\d,]+k?)?',
                r'salary.*?\$[\d,]+',
                r'compensation.*?\$[\d,]+'
            ]
            
            for pattern in salary_patterns:
                import re
                match = re.search(pattern, description_text, re.IGNORECASE)
                if match:
                    job_data["salary"] = match.group(0).strip()
                    break
            
            # Strategy 7: Determine employment type
            employment_indicators = {
                "full-time": ["full-time", "fulltime", "full time"],
                "part-time": ["part-time", "parttime", "part time"],
                "contract": ["contract", "contractor", "freelance"],
                "intern": ["intern", "internship", "entry level"]
            }
            
            text_lower = description_text.lower()
            for emp_type, indicators in employment_indicators.items():
                if any(indicator in text_lower for indicator in indicators):
                    job_data["employment_type"] = emp_type.title()
                    break
            
            # Strategy 8: Extract tags from content
            tech_keywords = [
                "python", "javascript", "react", "node", "java", "golang", "rust",
                "frontend", "backend", "fullstack", "devops", "ui/ux", "design",
                "data", "machine learning", "ai", "blockchain", "web3", "crypto"
            ]
            
            tags = []
            for keyword in tech_keywords:
                if keyword in text_lower:
                    tags.append(keyword.title())
            
            job_data["tags"] = tags[:5]  # Limit to 5 tags
            
            return job_data
            
        except Exception as e:
            logger.warning(f"Error extracting WorkingNomads job data: {e}")
            return {}
    
    def _is_valid_workingnomads_job(self, job_data):
        """Validate that the extracted job data meets quality criteria."""
        try:
            # Must have a title
            if not job_data.get("title") or len(job_data["title"]) < 3:
                return False
            
            # Title should not be generic website content
            invalid_titles = [
                "home", "about", "contact", "privacy", "terms", "login", "register",
                "menu", "navigation", "footer", "header", "sidebar", "advertisement",
                "cookie", "subscribe", "newsletter", "follow us", "social media"
            ]
            
            title_lower = job_data["title"].lower()
            if any(invalid in title_lower for invalid in invalid_titles):
                return False
            
            # Should have some reasonable content
            if job_data.get("description") and len(job_data["description"]) < 20:
                return False
            
            # Company name validation (if present)
            if job_data.get("company"):
                company_lower = job_data["company"].lower()
                invalid_companies = ["workingnomads", "copyright", "all rights", "contact", "about"]
                if any(invalid in company_lower for invalid in invalid_companies):
                    job_data["company"] = ""  # Clear invalid company name
            
            return True
            
        except Exception as e:
            logger.warning(f"Error validating WorkingNomads job: {e}")
            return False

    def _parse_cryptocurrencyjobs(self, soup, feed):
        """Parse jobs from cryptocurrencyjobs.co with robust selectors."""
        jobs = []
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
            title_elem = (
                card.find("h2", class_="job-title") or
                card.find("h3", class_="job-title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and "title" in c) or
                card.find("a", class_=lambda c: c and "title" in c) or
                card.find(["h2", "h3", "h4"]) or
                card.select_one("a.job-link")
            )
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company-name") or
                card.find(["div", "span"], class_=lambda c: c and "company" in c) or
                card.find("span", class_="company")
            )
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)
            )
            if title_elem and link_elem:
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
        """Parse jobs from nodesk.substack.com newsletter post with job listings."""
        jobs = []

        # Find the "Remote Jobs" section in the Substack post
        # Look for section headers that contain "Remote Jobs" or "Featured Jobs" or "Latest Jobs"
        job_sections = []
        
        # Find headings that might indicate job sections
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
            heading_text = heading.get_text(strip=True).lower()
            if any(keyword in heading_text for keyword in ['remote jobs', 'featured jobs', 'latest jobs', 'jobs']):
                logger.debug(f"[Nodesk Parser] Found job section heading: '{heading.get_text()}'")
                job_sections.append(heading)

        if not job_sections:
            logger.warning("[Nodesk Parser] No job section headers found")
            return jobs

        # For each job section, find the job listings that follow
        for section_heading in job_sections:
            logger.debug(f"[Nodesk Parser] Processing section: {section_heading.get_text()}")
            
            # Find the next sibling elements until we hit another heading or end of content
            current = section_heading.next_sibling
            while current:
                if current.name and current.name.lower() in ['h1', 'h2', 'h3', 'h4']:
                    # Stop if we hit another heading
                    break
                    
                if current.name == 'ul':
                    # Found a list - extract job items
                    job_items = current.find_all('li')
                    logger.debug(f"[Nodesk Parser] Found {len(job_items)} job items in list")
                    
                    for item in job_items:
                        # Try to extract title from <strong><a> tag and company/location from <span>
                        title_elem = item.find("strong")
                        if title_elem:
                            title_link = title_elem.find("a")
                            if title_link:
                                title = title_link.get_text(strip=True)
                                job_url = title_link.get("href", "")
                                
                                # Find the span with company and location info
                                span_elem = item.find("span")
                                if span_elem:
                                    span_text = span_elem.get_text(strip=True)
                                    logger.debug(f"[Nodesk Parser] Processing job: '{title}' with span: '{span_text}'")
                                    
                                    # Parse span text: " at Company - Location" or " at Company"
                                    match = re.match(r"\s*at\s+(.+?)(?:\s*-\s*(.+))?$", span_text)
                                    if match:
                                        company = match.group(1).strip()
                                        location = match.group(2).strip() if match.group(2) else "Remote"
                                        
                                        # Clean up company name (remove extra text after hyphens)
                                        if ' - ' in company:
                                            company = company.split(' - ')[0].strip()
                                        
                                        job = Job(
                                            id=job_url or f"{title}-{company}",
                                            title=title,
                                            company=company,
                                            url=job_url,
                                            source=feed.name,
                                            date="",
                                            location=location
                                        )
                                        jobs.append(job)
                                        logger.debug(f"[Nodesk Parser] Added job: {title} at {company}")
                                    else:
                                        logger.debug(f"[Nodesk Parser] Could not parse span format: {span_text}")
                                else:
                                    logger.debug(f"[Nodesk Parser] No span found for job: {title}")
                            else:
                                logger.debug(f"[Nodesk Parser] No link found in strong tag")
                        else:
                            # Fallback to original text parsing for different formats
                            text = item.get_text(strip=True)
                            if not text:
                                continue
                                
                            logger.debug(f"[Nodesk Parser] Fallback processing job item: '{text[:100]}...'")
                            
                            # Parse job format: "Title at Company - Location" or "Title at Company"
                            # Handle cases where there's no space before "at"
                            match = re.match(r"(.+?)(?:\s+)?at\s+(.+?)(?:\s*-\s*(.+))?$", text)
                            if match:
                                title = match.group(1).strip()
                                company = match.group(2).strip()
                                location = match.group(3).strip() if match.group(3) else "Remote"
                                
                                # Clean up company name (remove extra text after hyphens)
                                if ' - ' in company:
                                    company = company.split(' - ')[0].strip()
                                
                                # Try to get job URL if available
                                link_elem = item.find("a")
                                job_url = ""
                                if link_elem:
                                    job_url = link_elem.get("href", "")
                                    if job_url and not job_url.startswith('http'):
                                        job_url = f"https://nodesk.substack.com{job_url}"
                                
                                job = Job(
                                    id=job_url or f"{title}-{company}",
                                    title=title,
                                    company=company,
                                    url=job_url,
                                    source=feed.name,
                                    date="",
                                    location=location
                                )
                                jobs.append(job)
                                logger.debug(f"[Nodesk Parser] Added job (fallback): {title} at {company}")
                            else:
                                logger.debug(f"[Nodesk Parser] Could not parse job format: {text}")
                
                current = current.next_sibling

        logger.info(f"[Nodesk Parser] Successfully parsed {len(jobs)} jobs from Nodesk Substack")
        return jobs

    def _parse_remotehabits(self, soup, feed):
        """Parse jobs from remotehabits.com with robust selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_=lambda c: c and "job" in c) or
            soup.find_all("article", class_=lambda c: c and "job" in c) or
            soup.select(".job-listing, .job-preview, .job, .job-block, .job-row")
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
                card.find(["div", "span"], class_=lambda c: c and "company" in c) or
                card.find("span", class_="company")
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
        """Parse jobs from jobspresso.co with actual HTML structure and robust fallbacks."""
        jobs = []

        # Try both <li class="job_listing"> and <div class="job-card"> selectors
        job_cards = soup.find_all("li", class_="job_listing")
        if not job_cards:
            job_cards = soup.find_all("div", class_="job-card")

        if not job_cards:
            logger.warning(f"No job cards found on Jobspresso using known selectors")
            return jobs

        logger.info(f"Found {len(job_cards)} job cards on Jobspresso")

        for card in job_cards:
            # Try to get the job URL
            link_elem = card.find("a", class_="job_listing-clickbox") or card.find("a", class_="job-link") or card.find("a", href=True)
            job_url = link_elem.get("href", "") if link_elem else ""
            if job_url and job_url.startswith("/"):
                job_url = f"https://jobspresso.co{job_url}"
            if not job_url:
                continue

            # Try to get the job title
            title_elem = card.find("h3", class_="job_listing-title") or card.find("h2", class_="job-title") or card.find("h3", class_="job-title")
            if not title_elem:
                # Fallback: any h2/h3 in the card
                title_elem = card.find(["h2", "h3"])
            if not title_elem:
                continue
            title_text = title_elem.get_text(strip=True)

            # Try to get the company name
            company_elem = card.find("div", class_="job_listing-company") or card.find("div", class_="company-name")
            company_text = "Unknown Company"
            if company_elem:
                strong_elem = company_elem.find("strong")
                if strong_elem:
                    company_text = strong_elem.get_text(strip=True)
                else:
                    company_text = company_elem.get_text(strip=True)

            # Create unique job ID from URL
            job_id = job_url.split("/")[-2] if job_url.endswith("/") else job_url.split("/")[-1]
            if not job_id:
                import hashlib
                job_id = hashlib.md5((title_text + company_text).encode("utf-8")).hexdigest()[:8]

            job = Job(
                id=job_id,
                title=title_text,
                company=company_text,
                url=job_url,
                source=feed.name,
                date=""
            )
            jobs.append(job)

        logger.info(f"Successfully parsed {len(jobs)} jobs from Jobspresso")
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

    def _parse_linkedin(self, soup, feed):
        """Parse jobs from LinkedIn with enhanced selectors and unique ID generation."""
        jobs = []
        seen_ids = set()  # Track seen IDs to avoid duplicates
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="job-card-container") or
            soup.find_all("li", class_="jobs-search-results__list-item") or
            soup.find_all("div", class_="job-card") or
            soup.find_all("article", class_=lambda c: c and "job" in c) or
            soup.select(".jobs-search__results-list li, .job-card, [data-entity-urn*='job']")
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on LinkedIn using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on LinkedIn")
        
        for i, card in enumerate(job_cards):
            # Try various title element possibilities
            title_elem = (
                card.find("h3", class_="job-card-list__title") or
                card.find("a", class_="job-card-list__title-link") or
                card.find("h4", class_="job-card-container__title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and "title" in c) or
                card.find("a", class_=lambda c: c and "title" in c) or
                card.find(["h2", "h3", "h4"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("h4", class_="job-card-container__company-name") or
                card.find("a", class_="job-card-container__company-link") or
                card.find("span", class_="job-card-list__company-name") or
                card.find(["div", "span", "a"], class_=lambda c: c and "company" in c) or
                card.find("span", class_="company")
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-card-list__title-link") or
                card.find("a", class_="job-card-container__title-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem:  # LinkedIn often requires login, so we might not get links
                # Extract job URL if available
                job_url = ""
                if link_elem and link_elem.get("href"):
                    job_url = link_elem.get("href", "")
                    if job_url.startswith("/"):
                        job_url = f"https://www.linkedin.com{job_url}"
                
                # Use company name if available, otherwise "Unknown Company"
                company_text = company_elem.text.strip() if company_elem else "Unknown Company"
                title_text = title_elem.text.strip()
                
                # Enhanced job ID generation with multiple fallback strategies
                job_id = ""
                
                # Strategy 1: Extract from LinkedIn URL patterns
                if job_url:
                    import re
                    # Try multiple LinkedIn URL patterns
                    patterns = [
                        r'/jobs/view/(\d+)',  # Standard job view URL
                        r'jobId=(\d+)',       # Job ID parameter
                        r'currentJobId=(\d+)', # Current job ID parameter
                        r'job-(\d+)',         # Job with dash
                        r'jobs-(\d+)',        # Jobs with dash
                        r'/(\d+)/?$',         # Numeric ID at end of URL
                        r'refId=([^&]+)',     # Reference ID
                        r'trackingId=([^&]+)' # Tracking ID
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, job_url)
                        if match:
                            job_id = match.group(1)
                            break
                    
                    # If no pattern matched, use the full URL path as ID
                    if not job_id:
                        # Clean URL to create ID
                        url_parts = job_url.replace("https://www.linkedin.com", "").strip("/")
                        job_id = url_parts.replace("/", "-").replace("?", "-").replace("&", "-")
                        # Limit length and clean up
                        job_id = job_id[:100]
                
                # Strategy 2: Create ID from title + company if no URL ID found
                if not job_id:
                    import hashlib
                    # Create a hash from title + company + position to ensure uniqueness
                    unique_string = f"{title_text}_{company_text}_{i}"
                    job_id = hashlib.md5(unique_string.encode('utf-8')).hexdigest()[:16]
                
                # Strategy 3: Ensure uniqueness by adding suffix if needed
                original_job_id = job_id
                counter = 1
                while job_id in seen_ids:
                    job_id = f"{original_job_id}_{counter}"
                    counter += 1
                
                # Add to seen IDs
                seen_ids.add(job_id)
                
                job = Job(
                    id=job_id,
                    title=title_text,
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        
        logger.info(f"Successfully parsed {len(jobs)} unique jobs from LinkedIn")
        return jobs

    def _parse_glassdoor(self, soup, feed):
        """Parse jobs from Glassdoor with enhanced selectors."""
        jobs = []
        
        # Try multiple selectors for job cards
        job_cards = (
            soup.find_all("div", class_="react-job-listing") or
            soup.find_all("li", class_="job-tile") or
            soup.find_all("div", class_="job-search-card") or
            soup.find_all("article", class_="jobCard") or
            soup.find_all("div", attrs={"data-test": "job-listing"}) or
            soup.select(".job-tile, .jobCard, [data-test='job-listing']")
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on Glassdoor using known selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on Glassdoor")
        
        for card in job_cards:
            # Try various title element possibilities
            title_elem = (
                card.find("a", class_="job-title-link") or
                card.find("h2", class_="job-title") or
                card.find("h3", class_="job-title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and "title" in c) or
                card.find("a", attrs={"data-test": "job-title"}) or
                card.find(["h2", "h3", "h4"])  # Any heading
            )
            
            # Try various company element possibilities
            company_elem = (
                card.find("div", class_="company-name") or
                card.find("span", class_="company-name") or
                card.find("a", class_="company-link") or
                card.find(["div", "span", "a"], class_=lambda c: c and "company" in c) or
                card.find("span", class_="employer")
            )
            
            # Try various link element possibilities
            link_elem = (
                card.find("a", class_="job-title-link") or
                card.find("a", attrs={"data-test": "job-title"}) or
                card.find("a", class_=lambda c: c and "job" in c) or
                card.find("a", href=True)  # Any link
            )
            
            if title_elem:
                # Extract job URL if available
                job_url = ""
                if link_elem and link_elem.get("href"):
                    job_url = link_elem.get("href", "")
                    if job_url.startswith("/"):
                        job_url = f"https://www.glassdoor.com{job_url}"
                
                # Use company name if available, otherwise "Unknown Company"
                company_text = company_elem.text.strip() if company_elem else "Unknown Company"
                
                # Create job ID from URL or title
                job_id = ""
                if job_url:
                    # Extract job ID from Glassdoor URL
                    import re
                    match = re.search(r'jobListingId=(\d+)', job_url)
                    if match:
                        job_id = match.group(1)
                    else:
                        job_id = job_url.split("/")[-1]
                else:
                    job_id = title_elem.text.strip()
                
                job = Job(
                    id=job_id,
                    title=title_elem.text.strip(),
                    company=company_text,
                    url=job_url,
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_remote3(self, soup, feed):
        """Parse jobs from remote3.co, filtering for 'Customer Support' and 'Worldwide'."""
        jobs = []
        # Enhanced selectors for Remote3
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("div", class_="job-listing") or
            soup.find_all("div", class_="job-item") or
            soup.find_all("article", class_=lambda c: c and "job" in c) or
            soup.find_all("li", class_=lambda c: c and "job" in c) or
            soup.select(".position-card, [data-testid='job-card'], .listing-item")
        )
        
        if not job_cards:
            logger.warning(f"No job cards found on Remote3 using enhanced selectors")
            return jobs
            
        logger.info(f"Found {len(job_cards)} job cards on Remote3")
        
        for card in job_cards:
            # Title - try multiple selectors
            title_elem = (
                card.find(["h2", "h3"], class_="job-title") or
                card.find(["h2", "h3", "h4"], class_=lambda c: c and "title" in c) or
                card.find("a", class_=lambda c: c and "title" in c) or
                card.find(["h2", "h3", "h4"])
            )
            
            # Company - try multiple selectors
            company_elem = (
                card.find(["div", "span"], class_="company-name") or
                card.find(["div", "span", "a"], class_=lambda c: c and "company" in c) or
                card.find("span", class_="company")
            )
            
            # Link - try multiple selectors
            link_elem = (
                card.find("a", class_="job-link") or
                card.find("a", class_=lambda c: c and "link" in c) or
                card.find("a", href=True)
            )
            
            if not title_elem:
                continue
                
            # Look for category and location indicators
            card_text = card.get_text().lower()
            
            # Check for customer support category
            has_customer_support = any(keyword in card_text for keyword in [
                "customer support", "customer service", "support specialist", 
                "help desk", "technical support", "client support"
            ])
            
            # Check for worldwide/remote location
            has_worldwide = any(keyword in card_text for keyword in [
                "worldwide", "global", "remote", "anywhere", "international"
            ])
            
            # Only keep jobs with both customer support and worldwide
            if not (has_customer_support and has_worldwide):
                continue
                
            job_url = ""
            if link_elem and link_elem.get("href"):
                job_url = link_elem.get("href", "")
                if job_url.startswith("/"):
                    job_url = f"https://www.remote3.co{job_url}"
                    
            company_text = company_elem.text.strip() if company_elem else "Unknown Company"
            
            job = Job(
                id=job_url.split("/")[-1] if job_url else title_elem.text.strip(),
                title=title_elem.text.strip(),
                company=company_text,
                url=job_url,
                source=feed.name,
                date="",
                location="Worldwide",
                is_remote=True
            )
            jobs.append(job)
        return jobs

    def _fetch_headless(self, feed: Feed) -> List[Job]:
        domain = feed.url.split("/")[2]
        html = None
        max_retries = 3
        retry_delay = 3  # Reduced from 5 to 3 seconds
        
        # Enhanced retry logic for problematic sites
        if "indeed.com" in domain:
            max_retries = 5  # More retries for Indeed due to CAPTCHA
            retry_delay = 10  # Longer delays to avoid triggering more blocks
        elif "snaphunt.com" in domain:
            max_retries = 2  # Fewer retries but longer waits
            retry_delay = 5
        elif "remote3.co" in domain:
            # Check if the main URL is working, try alternative if not
            alternative_urls = [
                feed.url,
                feed.url.replace("remote-web3-jobs", "jobs"),
                feed.url.replace("remote-web3-jobs", "remote-jobs"),
                "https://www.remote3.co/jobs"
            ]
        
        for attempt in range(max_retries):
            try:
                print(f"[HEADLESS] Starting fetch for {feed.url} (attempt {attempt + 1}/{max_retries})")
                logger.info(f"[HEADLESS] Starting fetch for {feed.url} (attempt {attempt + 1}/{max_retries})")
                
                # Enhanced browser context configuration for different sites
                context_options = {}
                if "indeed.com" in domain:
                    # Use more realistic browser configuration for Indeed
                    context_options = {
                        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "viewport": {"width": 1366, "height": 768},  # More common resolution
                        "locale": "en-US",
                        "timezone_id": "America/New_York",
                        "geolocation": {"latitude": 40.7128, "longitude": -74.0060},  # NYC
                        "permissions": ["geolocation"],
                        "color_scheme": "light",
                        "device_scale_factor": 1,
                        "extra_http_headers": {
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                            "Accept-Language": "en-US,en;q=0.5",
                            "Accept-Encoding": "gzip, deflate, br",
                            "DNT": "1",
                            "Connection": "keep-alive",
                            "Upgrade-Insecure-Requests": "1",
                        }
                    }
                
                context = browser_pool.get_context(domain, headers=feed.headers, cookies=feed.cookies)
                page = context.new_page()
                stealth_sync(page)
                
                # Site-specific enhancements
                if "indeed.com" in domain:
                    # Add random mouse movements to appear more human-like
                    self._simulate_human_behavior(page)
                    
                    # Add random delays before navigation
                    time.sleep(random.uniform(2, 4))
                
                try:
                    current_url = feed.url
                    
                    # Remote3 URL fallback logic
                    if "remote3.co" in domain and attempt > 0:
                        if attempt < len(alternative_urls):
                            current_url = alternative_urls[attempt]
                            print(f"[HEADLESS] Trying alternative URL for Remote3: {current_url}")
                            logger.info(f"[HEADLESS] Trying alternative URL for Remote3: {current_url}")
                    
                    print(f"[HEADLESS] Navigating to {current_url}")
                    logger.info(f"[HEADLESS] Navigating to {current_url}")
                    
                    # Enhanced timeout strategies based on site
                    timeout_ms = 45000  # Default timeout
                    if "indeed.com" in domain:
                        timeout_ms = 60000  # Longer for Indeed due to anti-bot measures
                    elif "snaphunt.com" in domain:
                        timeout_ms = 90000  # Much longer for JavaScript-heavy Snaphunt
                    elif "linkedin.com" in domain:
                        timeout_ms = 30000  # Shorter for LinkedIn due to frequent blocking
                    elif "remote3.co" in domain:
                        timeout_ms = 30000  # Shorter for potentially broken sites
                    
                    # Enhanced navigation with multiple wait strategies
                    try:
                        if "snaphunt.com" in domain:
                            # For Snaphunt, use domcontentloaded first, then wait for network
                            page.goto(current_url, wait_until="domcontentloaded", timeout=timeout_ms)
                            print(f"[HEADLESS] DOM loaded for Snaphunt, waiting for network...")
                            logger.info(f"[HEADLESS] DOM loaded for Snaphunt, waiting for network...")
                            try:
                                page.wait_for_load_state("networkidle", timeout=60000)
                            except Exception:
                                print(f"[HEADLESS] Network idle timeout for Snaphunt, continuing...")
                                logger.warning(f"[HEADLESS] Network idle timeout for Snaphunt, continuing...")
                        else:
                            # Standard navigation for other sites
                            page.goto(current_url, wait_until="networkidle", timeout=timeout_ms)
                    except Exception as nav_error:
                        # Fallback navigation strategy
                        print(f"[HEADLESS] Primary navigation failed, trying fallback: {nav_error}")
                        logger.warning(f"[HEADLESS] Primary navigation failed, trying fallback: {nav_error}")
                        page.goto(current_url, wait_until="domcontentloaded", timeout=timeout_ms)
                    
                    print(f"[HEADLESS] Navigation complete for {current_url}")
                    logger.info(f"[HEADLESS] Navigation complete for {current_url}")
                    
                    # Site-specific wait strategies
                    if "indeed.com" in domain:
                        # For Indeed, wait longer and check for CAPTCHA
                        time.sleep(random.uniform(8, 12))  # Longer human-like delay
                        
                        # Simulate more human behavior after page load
                        self._simulate_human_behavior(page)
                        
                        # Check for CAPTCHA or security challenges
                        if self._detect_security_challenge(page):
                            print(f"[HEADLESS] CAPTCHA detected on Indeed attempt {attempt + 1}")
                            logger.warning(f"[HEADLESS] CAPTCHA detected on Indeed attempt {attempt + 1}")
                            
                            # Try to handle CAPTCHA if possible
                            try:
                                # Look for common CAPTCHA iframes
                                captcha_iframe = page.query_selector("iframe[src*='captcha'], iframe[src*='challenge']")
                                if captcha_iframe:
                                    # Switch to iframe context
                                    frame = page.frame_locator("iframe[src*='captcha'], iframe[src*='challenge']")
                                    
                                    # Try to find and click the checkbox
                                    checkbox = frame.locator("[role='checkbox'], .recaptcha-checkbox, .h-captcha")
                                    if checkbox:
                                        checkbox.click()
                                        time.sleep(random.uniform(2, 4))
                                        
                                        # Check if CAPTCHA was solved
                                        if not self._detect_security_challenge(page):
                                            print(f"[HEADLESS] CAPTCHA solved on Indeed attempt {attempt + 1}")
                                            logger.info(f"[HEADLESS] CAPTCHA solved on Indeed attempt {attempt + 1}")
                                            continue
                            except Exception as e:
                                print(f"[HEADLESS] Failed to handle CAPTCHA: {e}")
                                logger.warning(f"[HEADLESS] Failed to handle CAPTCHA: {e}")
                            
                            if attempt < max_retries - 1:
                                time.sleep(retry_delay * 2)  # Wait longer before retry
                                continue
                            else:
                                print(f"[HEADLESS] Max retries reached for Indeed with CAPTCHA")
                                logger.error(f"[HEADLESS] Max retries reached for Indeed with CAPTCHA")
                                raise ValueError("Indeed blocked with CAPTCHA after max retries")
                    
                    elif "snaphunt.com" in domain:
                        # For Snaphunt, wait much longer for React to load
                        print(f"[HEADLESS] Waiting for Snaphunt React app to load...")
                        logger.info(f"[HEADLESS] Waiting for Snaphunt React app to load...")
                        time.sleep(random.uniform(20, 30))  # Even longer wait for SPA
                        
                        # Try to wait for specific React elements with longer timeout
                        try:
                            page.wait_for_function(
                                "document.querySelector('[data-testid=\"job-card\"], .job-card, .job-listing, .MuiCard-root') !== null || document.querySelectorAll('div').length > 200",
                                timeout=45000  # Increased from 30000
                            )
                            print(f"[HEADLESS] React content detected on Snaphunt")
                            logger.info(f"[HEADLESS] React content detected on Snaphunt")
                        except Exception:
                            print(f"[HEADLESS] React content wait timeout, trying API detection...")
                            logger.warning(f"[HEADLESS] React content wait timeout, trying API detection...")
                            
                            # Try to detect API calls
                            try:
                                api_data = page.evaluate("""() => {
                                    // Look for common API patterns in network requests
                                    const scripts = Array.from(document.scripts);
                                    for (let script of scripts) {
                                        if (script.src && (script.src.includes('api') || script.src.includes('jobs'))) {
                                            return script.src;
                                        }
                                    }
                                    
                                    // Look for fetch/xhr patterns in page source
                                    const pageText = document.documentElement.innerHTML;
                                    const apiMatches = pageText.match(/(?:fetch|axios|xhr).*?['"`]([^'"`]*(?:api|jobs)[^'"`]*)['"`]/gi);
                                    if (apiMatches && apiMatches.length > 0) {
                                        return apiMatches[0];
                                    }
                                    
                                    return null;
                                }""")
                                
                                if api_data:
                                    print(f"[HEADLESS] Detected potential API endpoint: {api_data}")
                                    logger.info(f"[HEADLESS] Detected potential API endpoint: {api_data}")
                            except Exception as e:
                                print(f"[HEADLESS] API detection failed: {e}")
                                logger.warning(f"[HEADLESS] API detection failed: {e}")
                        
                        # Additional wait for dynamic content
                        time.sleep(random.uniform(10, 15))  # Increased from 5-8
                        
                        # Try scrolling to trigger lazy loading
                        try:
                            page.evaluate("""() => {
                                window.scrollTo(0, document.body.scrollHeight / 2);
                                setTimeout(() => {
                                    window.scrollTo(0, document.body.scrollHeight);
                                }, 2000);
                            }""")
                            time.sleep(5)  # Wait for scroll-triggered content
                        except Exception:
                            pass
                    
                    elif "remote3.co" in domain:
                        # For Remote3, shorter wait and quick error detection
                        time.sleep(random.uniform(3, 5))
                        
                        # Check for application errors
                        error_text = page.evaluate("document.body.innerText")
                        if "application error" in error_text.lower() or "exception has occurred" in error_text.lower():
                            print(f"[HEADLESS] Remote3 application error detected")
                            logger.warning(f"[HEADLESS] Remote3 application error detected")
                            if attempt < max_retries - 1:
                                continue  # Try alternative URL
                            else:
                                raise ValueError("Remote3 application error persists")
                    
                    elif "workingnomads.com" in domain:
                        # For WorkingNomads, standard wait
                        time.sleep(random.uniform(4, 6))
                    else:
                        # Standard wait for other sites
                        time.sleep(random.uniform(2, 4))
                    
                    # Enhanced content detection
                    if "example.com" not in current_url:
                        # Enhanced site-specific selectors
                        site_selectors = {
                            "snaphunt.com": [
                                ".job-card",
                                "[data-testid='job-card']",
                                "[data-cy='job-card']",
                                ".job-listing",
                                ".card",
                                ".position-card",
                                "div[class*='job']",
                                "article[class*='job']",
                                ".listing-item",
                                "div[role='listitem']",
                                ".MuiCard-root",  # Material-UI cards
                                "[class*='JobCard']",  # React component names
                                "[class*='JobListing']"
                            ],
                            "indeed.com": [
                                ".job_seen_beacon",
                                ".jobsearch-ResultsList",
                                ".tapItem",
                                ".result",
                                "[data-jk]",
                                ".jobsearch-SerpJobCard",
                                ".job_seen_beacon"
                            ],
                            "linkedin.com": [
                                ".job-card-container",
                                ".job-card-list__entity",
                                ".jobs-search-results__list-item",
                                ".job-card",
                                ".jobs-search__results-list li"
                            ],
                            "glassdoor.com": [
                                ".react-job-listing",
                                ".job-search-card",
                                "[data-test='job-listing']",
                                ".jobCard",
                                ".job-tile"
                            ],
                            "workingnomads.com": [
                                ".job-card",
                                ".job-listing",
                                ".job-item",
                                ".job-wrapper",
                                ".job-post",
                                "article.job",
                                "tr",  # Table rows are common
                                ".job-row"
                            ],
                            "remote3.co": [
                                ".job-card",
                                ".job-listing",
                                ".job-item",
                                ".position-card",
                                "[data-testid='job-card']",
                                "[class*='Job']"
                            ]
                        }
                        
                        # Get site-specific selectors or use defaults
                        selectors = site_selectors.get(domain, [".job-card", ".job-listing", ".job"])
                        selector_str = ", ".join(selectors)
                        
                        print(f"[HEADLESS] Waiting for selectors: {selector_str[:100]}...")
                        logger.info(f"[HEADLESS] Waiting for selectors: {selector_str[:100]}...")
                        
                        # Multiple wait strategies with site-specific timeouts
                        selector_found = False
                        wait_timeout = 15000  # Default
                        if "snaphunt.com" in domain:
                            wait_timeout = 30000  # Longer for SPA
                        elif "indeed.com" in domain:
                            wait_timeout = 20000  # Longer for anti-bot sites
                        
                        try:
                            page.wait_for_selector(selector_str, timeout=wait_timeout)
                            selector_found = True
                            print(f"[HEADLESS] Found job selectors on {domain}")
                            logger.info(f"[HEADLESS] Found job selectors on {domain}")
                        except Exception as e:
                            print(f"[HEADLESS] Selector wait failed: {e}")
                            logger.warning(f"[HEADLESS] Selector wait failed: {e}")
                            
                            # Alternative content detection strategies
                            try:
                                # Wait for substantial content
                                page.wait_for_function(
                                    "document.body.innerText.length > 5000",
                                    timeout=10000
                                )
                                print(f"[HEADLESS] Substantial content loaded for {domain}")
                                logger.info(f"[HEADLESS] Substantial content loaded for {domain}")
                            except Exception as e:
                                print(f"[HEADLESS] Content wait failed: {e}")
                                logger.warning(f"[HEADLESS] Content wait failed: {e}")
                            
                            # Final wait for any dynamic content
                            time.sleep(random.uniform(2, 4))
                    
                    # Check for security challenges one more time
                    if self._detect_security_challenge(page):
                        print(f"[HEADLESS] Security challenge detected on {domain}")
                        logger.warning(f"[HEADLESS] Security challenge detected on {domain}")
                        if attempt < max_retries - 1:
                            print(f"[HEADLESS] Retrying after security challenge...")
                            logger.info(f"[HEADLESS] Retrying after security challenge...")
                            time.sleep(retry_delay * 2)
                            continue
                    
                    print(f"[HEADLESS] Getting page content for {current_url}")
                    logger.info(f"[HEADLESS] Getting page content for {current_url}")
                    
                    # Final wait for any remaining dynamic content
                    time.sleep(random.uniform(1, 2))
                    
                    # Get the final page content
                    html = page.content()
                    
                    print(f"[HEADLESS] Got page content for {current_url} ({len(html)} chars)")
                    logger.info(f"[HEADLESS] Got page content for {current_url} ({len(html)} chars)")
                    
                    # Enhanced content validation
                    if len(html) < 5000:
                        print(f"[HEADLESS] Content too small ({len(html)} chars), may be blocked")
                        logger.warning(f"[HEADLESS] Content too small ({len(html)} chars), may be blocked")
                        if attempt < max_retries - 1:
                            continue
                    
                    # Save debug HTML (non-blocking)
                    try:
                        debug_dir = pathlib.Path("debug")
                        debug_dir.mkdir(exist_ok=True)
                        debug_file = debug_dir / f"{feed.name}_content.html"
                        
                        with open(debug_file, "w", encoding="utf-8") as f:
                            f.write(html)
                        print(f"[HEADLESS] Saved debug HTML to {debug_file}")
                        logger.info(f"[HEADLESS] Saved debug HTML to {debug_file}")
                    except Exception as e:
                        print(f"[HEADLESS] Failed to save debug HTML: {e}")
                        logger.warning(f"[HEADLESS] Failed to save debug HTML: {e}")
                    
                    # If we got here successfully, break the retry loop
                    break
                    
                except Exception as e:
                    print(f"[HEADLESS] Exception during navigation for {current_url}: {e}")
                    logger.error(f"[HEADLESS] Exception during navigation for {current_url}: {e}")
                    if attempt < max_retries - 1:
                        print(f"[HEADLESS] Retrying after error...")
                        logger.info(f"[HEADLESS] Retrying after error...")
                        time.sleep(retry_delay)
                        continue
                    raise
                finally:
                    try:
                        page.close()
                    except Exception as e:
                        logger.warning(f"Failed to close page: {e}")
                    
            except Exception as e:
                print(f"[HEADLESS] Error in _fetch_headless for {feed.name}: {e}")
                logger.error(f"[HEADLESS] Error in _fetch_headless for {feed.name}: {e}")
                if attempt < max_retries - 1:
                    print(f"[HEADLESS] Retrying after error...")
                    logger.info(f"[HEADLESS] Retrying after error...")
                    time.sleep(retry_delay)
                    continue
                raise
        
        if not html:
            raise ValueError(f"Failed to fetch content from {feed.url} after {max_retries} attempts")
            
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        
        # Enhanced parser map with new parsers
        parser_map = {
            "indeed": self._parse_indeed,
            "remotive": self._parse_remotive,
            "remoteok": self._parse_remoteok,
            "workingnomads": self._parse_workingnomads,
            "cryptocurrencyjobs": self._parse_cryptocurrencyjobs,
            "nodesk_substack": self._parse_nodesk_substack,
            "remotehabits": self._parse_remotehabits,
            "jobspresso": self._parse_jobspresso,
            "remote3": self._parse_remote3,
            "snaphunt": self._parse_snaphunt,
            "linkedin": self._parse_linkedin,
            "glassdoor": self._parse_glassdoor,
        }
        
        parser = parser_map.get(feed.parser)
        if parser:
            try:
                jobs = parser(soup, feed)
                print(f"[HEADLESS] Parser returned {len(jobs)} jobs for {feed.name}")
                logger.info(f"[HEADLESS] Parser returned {len(jobs)} jobs for {feed.name}")
                return jobs
            except Exception as e:
                print(f"[HEADLESS] Parser error for {feed.name}: {e}")
                logger.error(f"[HEADLESS] Parser error for {feed.name}: {e}")
                return []
        else:
            raise ValueError(f"No parser implemented for {feed.parser}")
            
    def _detect_security_challenge(self, page) -> bool:
        """Detect if the page contains a security challenge or CAPTCHA.
        
        Args:
            page: Playwright page object
            
        Returns:
            bool: True if security challenge detected, False otherwise
        """
        try:
            # Get page text content
            page_text = page.evaluate("document.body.innerText").lower()
            
            # Get page HTML for more specific checks
            page_html = page.content().lower()
            
            # Common security challenge indicators
            security_indicators = [
                "just a moment",
                "checking your browser",
                "security check",
                "captcha",
                "prove you are human",
                "verify you are human",
                "robot check",
                "unusual traffic",
                "suspicious activity",
                "please wait",
                "cloudflare",
                "distil",
                "imperva",
                "akamai",
                "challenge",
                "verification",
                "security verification",
                "human verification",
                "bot detection",
                "access denied"
            ]
            
            # Check for security challenge text
            for indicator in security_indicators:
                if indicator in page_text:
                    logger.warning(f"Security challenge detected: {indicator}")
                    return True
                    
            # Check for common CAPTCHA elements
            captcha_selectors = [
                "iframe[src*='captcha']",
                "iframe[src*='challenge']",
                "iframe[src*='recaptcha']",
                "iframe[src*='hcaptcha']",
                "iframe[src*='security']",
                "iframe[src*='verify']",
                "iframe[src*='cloudflare']",
                "iframe[src*='distil']",
                "iframe[src*='imperva']",
                "iframe[src*='akamai']",
                "iframe[src*='challenge']",
                "iframe[src*='verification']",
                "iframe[src*='bot']",
                "iframe[src*='human']",
                "iframe[src*='security']"
            ]
            
            for selector in captcha_selectors:
                if page.query_selector(selector):
                    logger.warning(f"CAPTCHA iframe detected: {selector}")
                    return True
                    
            # Check for common CAPTCHA scripts
            script_sources = page.evaluate("""() => {
                return Array.from(document.scripts).map(s => s.src);
            }""")
            
            captcha_script_indicators = [
                "captcha",
                "recaptcha",
                "hcaptcha",
                "cloudflare",
                "distil",
                "imperva",
                "akamai",
                "challenge",
                "verification",
                "bot",
                "human",
                "security"
            ]
            
            for script in script_sources:
                if any(indicator in script.lower() for indicator in captcha_script_indicators):
                    logger.warning(f"CAPTCHA script detected: {script}")
                    return True
                    
            # Check for common CAPTCHA images
            image_sources = page.evaluate("""() => {
                return Array.from(document.images).map(img => img.src);
            }""")
            
            captcha_image_indicators = [
                "captcha",
                "challenge",
                "verify",
                "security",
                "robot",
                "human",
                "bot"
            ]
            
            for img in image_sources:
                if any(indicator in img.lower() for indicator in captcha_image_indicators):
                    logger.warning(f"CAPTCHA image detected: {img}")
                    return True
                    
            # Check for common CAPTCHA forms
            form_actions = page.evaluate("""() => {
                return Array.from(document.forms).map(form => form.action);
            }""")
            
            captcha_form_indicators = [
                "captcha",
                "challenge",
                "verify",
                "security",
                "robot",
                "human",
                "bot"
            ]
            
            for action in form_actions:
                if any(indicator in action.lower() for indicator in captcha_form_indicators):
                    logger.warning(f"CAPTCHA form detected: {action}")
                    return True
                    
            return False
            
        except Exception as e:
            logger.error(f"Error detecting security challenge: {e}")
            return False
            
    def _simulate_human_behavior(self, page):
        """Simulate human-like behavior to avoid detection.
        
        Args:
            page: Playwright page object
        """
        try:
            # Random mouse movements
            page.evaluate("""() => {
                // Add random mouse movements
                const events = [];
                for (let i = 0; i < 10; i++) {
                    events.push({
                        type: 'mousemove',
                        x: Math.random() * window.innerWidth,
                        y: Math.random() * window.innerHeight,
                        timestamp: Date.now() + i * 100
                    });
                }
                
                // Simulate mouse events
                events.forEach(event => {
                    const mouseEvent = new MouseEvent(event.type, {
                        clientX: event.x,
                        clientY: event.y,
                        bubbles: true,
                        cancelable: true
                    });
                    document.dispatchEvent(mouseEvent);
                });
                
                // Add random scrolling
                const scrollAmount = Math.random() * 100;
                window.scrollBy(0, scrollAmount);
                
                // Add random pauses
                const pause = Math.random() * 1000;
                return new Promise(resolve => setTimeout(resolve, pause));
            }""")
            
            # Random typing simulation
            page.evaluate("""() => {
                // Simulate random typing in any input fields
                const inputs = document.querySelectorAll('input[type="text"], input[type="search"], textarea');
                inputs.forEach(input => {
                    if (Math.random() > 0.5) {  // 50% chance to interact with each input
                        input.focus();
                        const text = "test" + Math.random().toString(36).substring(7);
                        input.value = text;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                });
            }""")
            
            # Random clicks on non-interactive elements
            page.evaluate("""() => {
                // Find non-interactive elements
                const elements = document.querySelectorAll('div, span, p');
                const randomElement = elements[Math.floor(Math.random() * elements.length)];
                if (randomElement) {
                    randomElement.click();
                }
            }""")
            
            # Add random delays
            time.sleep(random.uniform(1, 3))
            
        except Exception as e:
            logger.warning(f"Error simulating human behavior: {e}")

if __name__ == "__main__":
    print("[WARNING] Running jobradar/fetchers.py directly does NOT fetch from all sources.")
    print("Use: python -m jobradar.cli fetch  # to fetch from all job boards") 