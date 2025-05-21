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

logger = logging.getLogger(__name__)

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
        if feed.cookies:
            req_kwargs['cookies'] = feed.cookies
        response = requests.get(feed.url, **req_kwargs)
        response.raise_for_status()
        
        parsed = feedparser.parse(response.text)
        jobs = []
        
        for entry in parsed.entries:
            # Try to parse the date robustly
            raw_date = entry.get("published", "")
            parsed_date = raw_date
            if raw_date:
                try:
                    parsed_date = date_parser.parse(raw_date).isoformat()
                except Exception:
                    parsed_date = raw_date  # fallback to original string
            job = Job(
                id=entry.get("id", entry.get("link", "")),
                title=entry.get("title", ""),
                company=entry.get("company", ""),
                url=entry.get("link", ""),
                source=feed.name,
                date=parsed_date
            )
            jobs.append(job)
        
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
        jobs = []
        job_cards = soup.find_all("div", class_="job_seen_beacon")
        for card in job_cards:
            title_elem = card.find("h2", class_="jobTitle")
            company_elem = card.find("span", class_="companyName")
            if title_elem and company_elem:
                job = Job(
                    id=card.get("data-jk", ""),
                    title=title_elem.text.strip(),
                    company=company_elem.text.strip(),
                    url=f"https://www.indeed.com/viewjob?jk={card.get('data-jk', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
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
                    url=f"https://remotive.com{link_elem.get('href', '')}",
                    source=feed.name,
                    date=""
                )
                jobs.append(job)
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
        """Fetch jobs from a page requiring JavaScript rendering using Playwright."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(feed.url, wait_until="networkidle")
            html = page.content()
            browser.close()
        # Use the same HTML parser logic as _fetch_html
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
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