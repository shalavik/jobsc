"""Feed fetching functionality."""
from typing import List, Dict, Any
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

logger = logging.getLogger(__name__)

# Browser context pool for headless fetching
class BrowserPool:
    """Manages a pool of browser contexts for headless fetching."""
    
    def __init__(self, max_contexts=3):
        """Initialize the browser pool.
        
        Args:
            max_contexts: Maximum number of browser contexts to keep in the pool
        """
        self.max_contexts = max_contexts
        self.contexts = {}  # domain -> (context, last_used_time)
        self.lock = threading.Lock()
        self.playwright = None
        self.browser = None
        self._initialized = False
        
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
        with self.lock:
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
            
        with self.lock:
            for domain, (context, _) in list(self.contexts.items()):
                try:
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
            "seek": self._parse_seek,
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
        for card in job_cards:
            title_elem = card.find("h2", attrs={"itemprop": "title"})
            company_elem = card.find("h3", attrs={"itemprop": "name"})
            if title_elem and company_elem:
                job = Job(
                    id=card.get("data-id", ""),
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://remoteok.com/remote-jobs/{card.get('data-id', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_snaphunt(self, soup, feed):
        """Parse jobs from snaphunt.com."""
        jobs = []
        job_cards = soup.find_all("div", class_="job-card")
        for card in job_cards:
            title_elem = card.find("h3", class_="job-title")
            company_elem = card.find("div", class_="company-name")
            link_elem = card.find("a", class_="job-link")
            
            if title_elem and company_elem and link_elem:
                job = Job(
                    id=link_elem.get("href", "").split("/")[-1],
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://snaphunt.com{link_elem.get('href', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_alljobs(self, soup, feed):
        """Parse jobs from alljobs.co.il."""
        jobs = []
        job_cards = soup.find_all("div", class_="job-item")
        for card in job_cards:
            title_elem = card.find("h2", class_="job-title")
            company_elem = card.find("div", class_="company-name")
            link_elem = card.find("a", class_="job-link")
            
            if title_elem and company_elem and link_elem:
                job = Job(
                    id=link_elem.get("href", "").split("/")[-1],
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://www.alljobs.co.il{link_elem.get('href', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_remotive(self, soup, feed):
        """Parse jobs from remotive.com."""
        jobs = []
        
        # Try multiple possible job card classes
        job_cards = (
            soup.find_all("div", class_="job-card") or
            soup.find_all("li", class_="job-li") or
            soup.find_all("div", class_="job")
        )
        
        if job_cards:
            logger.info(f"Found {len(job_cards)} Remotive job cards")
            
            for card in job_cards:
                # Try multiple possible title elements
                title_elem = (
                    card.find("h2", class_=lambda c: c and ("job-title" in c or "title" in c)) or
                    card.find("div", class_="position") or
                    card.find(["h2", "h3", "div"], class_=["position", "title"]) or
                    card.select_one(".job-info h2, .job-info h3")
                )
                
                # Try multiple company name elements
                company_elem = (
                    card.find(class_=lambda c: c and ("company-name" in c or "company" in c)) or
                    card.find("div", class_="company") or
                    card.select_one(".company span")
                )
                
                # Try to find link
                link_elem = (
                    card.find("a", class_=lambda c: c and ("job-link" in c or "url" in c)) or
                    card.find("a", href=lambda h: h and ("/remote-jobs/" in h or "/job/" in h)) or
                    card.find("a")
                )
                
                if title_elem and company_elem and link_elem:
                    # Get the job URL
                    job_url = link_elem.get("href", "")
                    # Add base URL if it's a relative path
                    if job_url.startswith("/"):
                        job_url = f"https://remotive.com{job_url}"
                        
                    # Get job ID from URL
                    job_id = job_url.split("/")[-1] if job_url else ""
                    
                    job = Job(
                        id=job_id or job_url,
                        title=title_elem.get_text(strip=True),
                        company=company_elem.get_text(strip=True),
                        url=job_url,
                        source=feed.name,
                        date=""
                    )
                    jobs.append(job)
        else:
            # Check if we're on a block page
            if soup.find(text=lambda t: t and ("captcha" in t.lower() or "blocked" in t.lower() or "rate limit" in t.lower())):
                logger.warning("Remotive is showing a block or CAPTCHA page")
            else:
                # Try a generic search for any job data
                titles = soup.find_all(["h2", "h3"], string=lambda s: s and len(s) > 5)
                for title in titles:
                    parent = title.parent
                    company = ""
                    for sibling in parent.find_all_next():
                        if "company" in sibling.get("class", []):
                            company = sibling.text.strip()
                            break
                    
                    if company:
                        job = Job(
                            id=title.text.strip(),
                            title=title.text.strip(),
                            company=company,
                            url="https://remotive.com/remote-jobs/software-dev",
                            source=feed.name,
                            date=""
                        )
                        jobs.append(job)
                
                if not jobs:
                    text_content = soup.get_text()[:200]
                    logger.warning(f"No jobs found on Remotive. Page starts with: {text_content}...")
            
        return jobs

    def _parse_workingnomads(self, soup, feed):
        """Parse jobs from workingnomads.com."""
        jobs = []
        job_cards = soup.find_all("div", class_="job-card")
        for card in job_cards:
            title_elem = card.find("h2", class_="job-title")
            company_elem = card.find("div", class_="company-name")
            link_elem = card.find("a", class_="job-link")
            
            if title_elem and company_elem and link_elem:
                job = Job(
                    id=link_elem.get("href", "").split("/")[-1],
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://www.workingnomads.com{link_elem.get('href', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_cryptojobslist(self, soup, feed):
        """Parse jobs from cryptojobslist.com."""
        jobs = []
        job_cards = soup.find_all("div", class_="job-card")
        for card in job_cards:
            title_elem = card.find("h2", class_="job-title")
            company_elem = card.find("div", class_="company-name")
            link_elem = card.find("a", class_="job-link")
            
            if title_elem and company_elem and link_elem:
                job = Job(
                    id=link_elem.get("href", "").split("/")[-1],
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://cryptojobslist.com{link_elem.get('href', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_remote3(self, soup, feed):
        """Parse jobs from remote3.co."""
        jobs = []
        job_cards = soup.find_all("div", class_="job-card")
        for card in job_cards:
            title_elem = card.find("h2", class_="job-title")
            company_elem = card.find("div", class_="company-name")
            link_elem = card.find("a", class_="job-link")
            
            if title_elem and company_elem and link_elem:
                job = Job(
                    id=link_elem.get("href", "").split("/")[-1],
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://www.remote3.co{link_elem.get('href', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_mindtel(self, soup, feed):
        """Parse jobs from mindtel.atsmantra.com."""
        jobs = []
        job_cards = soup.find_all("div", class_="job-card")
        for card in job_cards:
            title_elem = card.find("h2", class_="job-title")
            company_elem = card.find("div", class_="company-name")
            link_elem = card.find("a", class_="job-link")
            
            if title_elem and company_elem and link_elem:
                job = Job(
                    id=link_elem.get("href", "").split("/")[-1],
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://mindtel.atsmantra.com{link_elem.get('href', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_nodesk(self, soup, feed):
        """Parse jobs from nodesk.co."""
        jobs = []
        job_cards = soup.find_all("div", class_="job-card")
        for card in job_cards:
            title_elem = card.find("h2", class_="job-title")
            company_elem = card.find("div", class_="company-name")
            link_elem = card.find("a", class_="job-link")
            
            if title_elem and company_elem and link_elem:
                job = Job(
                    id=link_elem.get("href", "").split("/")[-1],
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://nodesk.co{link_elem.get('href', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_cryptocurrencyjobs(self, soup, feed):
        """Parse jobs from cryptocurrencyjobs.co."""
        jobs = []
        job_cards = soup.find_all("div", class_="job-card")
        for card in job_cards:
            title_elem = card.find("h2", class_="job-title")
            company_elem = card.find("div", class_="company-name")
            link_elem = card.find("a", class_="job-link")
            
            if title_elem and company_elem and link_elem:
                job = Job(
                    id=link_elem.get("href", "").split("/")[-1],
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://cryptocurrencyjobs.co{link_elem.get('href', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_nodesk_substack(self, soup, feed):
        """Parse jobs from nodesk.substack.com."""
        jobs = []
        job_cards = soup.find_all("div", class_="job-card")
        for card in job_cards:
            title_elem = card.find("h2", class_="job-title")
            company_elem = card.find("div", class_="company-name")
            link_elem = card.find("a", class_="job-link")
            
            if title_elem and company_elem and link_elem:
                job = Job(
                    id=link_elem.get("href", "").split("/")[-1],
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://nodesk.substack.com{link_elem.get('href', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_remotehabits(self, soup, feed):
        """Parse jobs from remotehabits.com."""
        jobs = []
        job_cards = soup.find_all("div", class_="job-card")
        for card in job_cards:
            title_elem = card.find("h2", class_="job-title")
            company_elem = card.find("div", class_="company-name")
            link_elem = card.find("a", class_="job-link")
            
            if title_elem and company_elem and link_elem:
                job = Job(
                    id=link_elem.get("href", "").split("/")[-1],
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://remotehabits.com{link_elem.get('href', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_jobspresso(self, soup, feed):
        """Parse jobs from jobspresso.co."""
        jobs = []
        job_cards = soup.find_all("div", class_="job-card")
        for card in job_cards:
            title_elem = card.find("h2", class_="job-title")
            company_elem = card.find("div", class_="company-name")
            link_elem = card.find("a", class_="job-link")
            
            if title_elem and company_elem and link_elem:
                job = Job(
                    id=link_elem.get("href", "").split("/")[-1],
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://jobspresso.co{link_elem.get('href', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_weworkremotely_support(self, soup, feed):
        """Parse jobs from weworkremotely.com customer support section."""
        jobs = []
        job_cards = soup.find_all("div", class_="job-card")
        for card in job_cards:
            title_elem = card.find("h2", class_="job-title")
            company_elem = card.find("div", class_="company-name")
            link_elem = card.find("a", class_="job-link")
            
            if title_elem and company_elem and link_elem:
                job = Job(
                    id=link_elem.get("href", "").split("/")[-1],
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://weworkremotely.com{link_elem.get('href', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
        return jobs

    def _parse_seek(self, soup, feed):
        """Parse jobs from seek.com."""
        jobs = []
        job_cards = soup.find_all("div", class_="job-card")
        for card in job_cards:
            title_elem = card.find("h2", class_="job-title")
            company_elem = card.find("div", class_="company-name")
            link_elem = card.find("a", class_="job-link")
            
            if title_elem and company_elem and link_elem:
                job = Job(
                    id=link_elem.get("href", "").split("/")[-1],
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://www.seek.com{link_elem.get('href', '')}",
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
                
                # Scroll more naturally
                for _ in range(3):
                    # Scroll down with natural speed
                    page.evaluate("window.scrollTo({top: window.scrollY + 400, behavior: 'smooth'})")
                    time.sleep(random.uniform(1.5, 3))
                
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
                    "remotive": "div.job-card, li.job-li, div.job, div.ce",  # Adding more potential selectors
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
        }
        parser = parser_map.get(feed.parser)
        if parser:
            return parser(soup, feed)
        else:
            raise ValueError(f"No parser implemented for {feed.parser}") 