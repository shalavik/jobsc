"""Main orchestration logic for jobradar."""
from pathlib import Path
from typing import List, Dict, Any
import os
import logging
from .config import load_feeds
from .fetchers import Fetcher
from .filters import keyword_match, dedupe
from .db import SQLiteSeenStore
from .notifiers import TelegramNotifier, EmailNotifier
from .models import Job
import yaml

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

def fetch_jobs(feeds: List[Any]) -> List[Job]:
    """Fetch jobs from a list of feeds.
    
    Args:
        feeds: List of Feed objects
        
    Returns:
        List of Job objects
    """
    jobs: List[Job] = []
    for feed in feeds:
        try:
            fetched = Fetcher.fetch(feed)
            jobs.extend(fetched)
            logging.info("Fetched %d jobs from %s", len(fetched), feed.name)
        except Exception as e:
            logging.error("Failed to fetch from %s: %s", feed.name, e)
    
    # Deduplicate jobs
    jobs = dedupe(jobs)
    return jobs

def run(feeds_path: Path = Path("feeds.yml"), db_path: Path = Path("seen.db"), keywords: List[str] = None, config_path: Path = Path("projectrules")) -> None:
    """Main entry point for the jobradar aggregator.
    Args:
        feeds_path: Path to feeds.yml
        db_path: Path to SQLite DB for seen jobs
        keywords: List of keywords to filter jobs
        config_path: Path to projectrules
    """
    # 1. Load feeds
    logging.info("Loading feeds from %s", feeds_path)
    feeds = load_feeds(feeds_path)

    # 2. Fetch jobs from all feeds
    jobs: List[Job] = []
    for feed in feeds:
        try:
            fetched = Fetcher.fetch(feed)
            jobs.extend(fetched)
            logging.info("Fetched %d jobs from %s", len(fetched), feed.name)
        except Exception as e:
            logging.error("Failed to fetch from %s: %s", feed.name, e)

    # 3. Filter by keywords
    if keywords:
        jobs = [job for job in jobs if keyword_match(job, keywords)]
        logging.info("%d jobs after keyword filtering", len(jobs))

    # 4. Dedupe
    jobs = dedupe(jobs)
    logging.info("%d jobs after deduplication", len(jobs))

    # 5. Filter out seen jobs
    seen_store = SQLiteSeenStore(db_path)
    new_jobs = seen_store.filter_seen(jobs)
    logging.info("%d new jobs after filtering seen", len(new_jobs))

    # 6. Persist new jobs as seen
    seen_store.mark_seen(new_jobs)

    # 7. Notify (console + Telegram + Email)
    if not new_jobs:
        print("No new jobs")
        return

    for job in new_jobs:
        print(f"{job.title} at {job.company} [{job.source}] - {job.url}")

    # Load notification config
    try:
        with open("projectrules", "r") as f:
            config = yaml.safe_load(f)
        email_config = config.get("notifications", {}).get("email", {})
    except Exception:
        email_config = {}

    # Telegram notification
    if os.getenv("TG_TOKEN") and os.getenv("TG_CHAT_ID"):
        try:
            notifier = TelegramNotifier()
            notifier.notify(new_jobs)
            logging.info("Sent Telegram notification")
        except Exception as e:
            logging.error("Failed to send Telegram notification: %s", e)

    # Email notification
    if email_config.get("enabled", False):
        try:
            email_notifier = EmailNotifier(email_config)
            email_notifier.notify(new_jobs)
            logging.info("Sent email notification")
        except Exception as e:
            logging.error("Failed to send email notification: %s", e) 