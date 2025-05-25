"""Main orchestration logic for jobradar."""
from pathlib import Path
from typing import List, Dict, Any, Optional
import os
import logging
from .config import load_feeds, get_config
from .fetchers import Fetcher
from .filters import keyword_match, dedupe, JobFilter
from .models import Job, Feed
from .database import Database
from .smart_matcher import SmartTitleMatcher
from .rate_limiter import RateLimiter
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

    # 5. Notify (console)
    if not jobs:
        print("No new jobs")
        return

    for job in jobs:
        print(f"{job.title} at {job.company} [{job.source}] - {job.url}")

    # Load notification config
    try:
        with open("projectrules", "r") as f:
            config = yaml.safe_load(f)
        email_config = config.get("notifications", {}).get("email", {})
    except Exception:
        email_config = {}

    # Optional notifications (only if modules are available)
    try:
        from .notifiers import TelegramNotifier, EmailNotifier
        
        # Telegram notification
        if os.getenv("TG_TOKEN") and os.getenv("TG_CHAT_ID"):
            try:
                notifier = TelegramNotifier()
                notifier.notify(jobs)
                logging.info("Sent Telegram notification")
            except Exception as e:
                logging.error("Failed to send Telegram notification: %s", e)

        # Email notification
        if email_config.get("enabled", False):
            try:
                email_notifier = EmailNotifier(email_config)
                email_notifier.notify(jobs)
                logging.info("Sent email notification")
            except Exception as e:
                logging.error("Failed to send email notification: %s", e)
    except ImportError:
        logging.warning("Notification modules not available")


class JobRadar:
    """Main orchestration class for the JobRadar application.
    
    This class integrates all components of the job aggregation system:
    - Fetching jobs from multiple sources
    - Smart matching and filtering
    - Database persistence
    - Rate limiting
    - Notifications
    """
    
    def __init__(self, 
                 db_url: str = "sqlite:///jobs.db",
                 feeds_path: Optional[Path] = None,
                 config_path: Optional[Path] = None):
        """Initialize JobRadar with all components.
        
        Args:
            db_url: Database connection URL
            feeds_path: Path to feeds configuration file
            config_path: Path to application configuration file
        """
        self.logger = logging.getLogger(__name__)
        
        # Initialize core components
        self.database = Database(db_url)
        self.fetcher = Fetcher()
        self.smart_matcher = SmartTitleMatcher()
        self.rate_limiter = RateLimiter()
        
        # Configuration
        self.feeds_path = feeds_path or Path("feeds.yml")
        self.config_path = config_path or Path("projectrules")
        self.feeds: List[Feed] = []
        self.job_filter: Optional[JobFilter] = None
        
        # Load configuration if available
        self._load_configuration()
    
    def _load_configuration(self) -> None:
        """Load feeds and application configuration."""
        try:
            if self.feeds_path.exists():
                self.feeds = load_feeds(self.feeds_path)
                self.logger.info(f"Loaded {len(self.feeds)} feeds from {self.feeds_path}")
            
            if self.config_path.exists():
                config = get_config(self.config_path)
                # Initialize job filter if filter config is available
                if 'filters' in config:
                    from .filters import FilterConfig
                    filter_config = FilterConfig(**config['filters'])
                    self.job_filter = JobFilter(filter_config)
                    self.logger.info("Loaded job filter configuration")
        except Exception as e:
            self.logger.warning(f"Could not load configuration: {e}")
    
    def fetch_all_jobs(self) -> List[Job]:
        """Fetch jobs from all configured feeds.
        
        Returns:
            List[Job]: All fetched jobs
        """
        all_jobs: List[Job] = []
        
        for feed in self.feeds:
            try:
                jobs = self.fetcher.fetch(feed)
                all_jobs.extend(jobs)
                self.logger.info(f"Fetched {len(jobs)} jobs from {feed.name}")
            except Exception as e:
                self.logger.error(f"Failed to fetch from {feed.name}: {e}")
        
        return all_jobs
    
    def process_jobs(self, jobs: List[Job]) -> List[Job]:
        """Process jobs through smart matching and filtering.
        
        Args:
            jobs: Raw jobs to process
            
        Returns:
            List[Job]: Processed and filtered jobs
        """
        if not jobs:
            return []
        
        # Smart matching - filter for relevant jobs
        relevant_jobs = self.smart_matcher.filter_jobs(jobs)
        self.logger.info(f"Smart matcher found {len(relevant_jobs)} relevant jobs from {len(jobs)} total")
        
        # Apply additional filters if configured
        if self.job_filter:
            filtered_jobs = []
            for job in relevant_jobs:
                if (self.job_filter.matches_keywords(job) and 
                    self.job_filter.matches_location(job) and 
                    self.job_filter.matches_salary(job)):
                    filtered_jobs.append(job)
            self.logger.info(f"Job filter passed {len(filtered_jobs)} jobs from {len(relevant_jobs)}")
            return filtered_jobs
        
        return relevant_jobs
    
    def save_jobs(self, jobs: List[Job]) -> int:
        """Save jobs to the database.
        
        Args:
            jobs: Jobs to save
            
        Returns:
            int: Number of jobs successfully saved
        """
        if not jobs:
            return 0
        
        saved_count = self.database.add_jobs(jobs)
        self.logger.info(f"Saved {saved_count} jobs to database")
        return saved_count
    
    def run_pipeline(self) -> Dict[str, Any]:
        """Run the complete job processing pipeline.
        
        Returns:
            Dict[str, Any]: Pipeline execution results
        """
        results = {
            'fetched_count': 0,
            'processed_count': 0,
            'saved_count': 0,
            'errors': []
        }
        
        try:
            # 1. Fetch all jobs
            all_jobs = self.fetch_all_jobs()
            results['fetched_count'] = len(all_jobs)
            
            # 2. Process jobs (smart matching + filtering)
            processed_jobs = self.process_jobs(all_jobs)
            results['processed_count'] = len(processed_jobs)
            
            # 3. Save to database
            saved_count = self.save_jobs(processed_jobs)
            results['saved_count'] = saved_count
            
            self.logger.info(f"Pipeline completed: {results}")
            
        except Exception as e:
            error_msg = f"Pipeline error: {e}"
            self.logger.error(error_msg)
            results['errors'].append(error_msg)
        
        return results
    
    def search_jobs(self, filters: Dict[str, Any], limit: int = 100) -> List[Job]:
        """Search for jobs in the database.
        
        Args:
            filters: Search filters
            limit: Maximum number of results
            
        Returns:
            List[Job]: Matching jobs
        """
        job_models = self.database.search_jobs(filters, limit=limit)
        
        # Convert JobModel objects back to Job objects
        jobs = []
        for model in job_models:
            job = Job(
                id=model.id,
                title=model.title,
                company=model.company,
                url=model.url,
                source=model.source,
                date=model.date.isoformat() if model.date else "",
                location=model.location or "",
                salary=model.salary or "",
                job_type=model.job_type or "",
                description=model.description or "",
                is_remote=model.is_remote,
                experience_level=model.experience_level or "",
                skills=model.skills or []
            )
            jobs.append(job)
        
        return jobs
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the job database.
        
        Returns:
            Dict[str, Any]: Database statistics
        """
        return {
            'total_jobs': self.database.count_jobs(),
            'sources': self.database.get_unique_values('source'),
            'companies': len(self.database.get_unique_values('company')),
            'locations': len(self.database.get_unique_values('location')),
            'recent_jobs': len(self.database.get_recent_jobs(days=7))
        } 