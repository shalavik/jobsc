"""Rate limiting and retry functionality."""
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

class RateLimiter:
    """Handles rate limiting and retries for API requests."""
    
    def __init__(self):
        """Initialize the rate limiter."""
        self.last_request: Dict[str, datetime] = {}
        self.request_count: Dict[str, int] = {}
        self.window_start: Dict[str, datetime] = {}
    
    def wait_if_needed(self, feed_name: str, rate_limit: Dict[str, Any]) -> None:
        """Wait if necessary to respect rate limits.
        
        Args:
            feed_name: Name of the feed
            rate_limit: Rate limit configuration
        """
        now = datetime.now()
        requests_per_minute = rate_limit.get('requests_per_minute', 60)
        retry_after = rate_limit.get('retry_after', 60)
        
        # Initialize window if needed
        if feed_name not in self.window_start:
            self.window_start[feed_name] = now
            self.request_count[feed_name] = 0
        
        # Check if we need to reset the window
        if (now - self.window_start[feed_name]) > timedelta(minutes=1):
            self.window_start[feed_name] = now
            self.request_count[feed_name] = 0
        
        # Check if we've hit the rate limit
        if self.request_count[feed_name] >= requests_per_minute:
            wait_time = 60 - (now - self.window_start[feed_name]).total_seconds()
            if wait_time > 0:
                logger.info(f"Rate limit reached for {feed_name}, waiting {wait_time:.1f} seconds")
                time.sleep(wait_time)
                self.window_start[feed_name] = datetime.now()
                self.request_count[feed_name] = 0
        
        # Check if we need to respect minimum time between requests
        if feed_name in self.last_request:
            time_since_last = (now - self.last_request[feed_name]).total_seconds()
            if time_since_last < retry_after:
                wait_time = retry_after - time_since_last
                logger.info(f"Waiting {wait_time:.1f} seconds between requests for {feed_name}")
                time.sleep(wait_time)
        
        self.last_request[feed_name] = datetime.now()
        self.request_count[feed_name] += 1
    
    def handle_request_exception(self, e: RequestException, feed_name: str, 
                               rate_limit: Dict[str, Any]) -> bool:
        """Handle request exceptions and determine if retry is needed.
        
        Args:
            e: The request exception
            feed_name: Name of the feed
            rate_limit: Rate limit configuration
            
        Returns:
            True if retry should be attempted, False otherwise
        """
        retry_after = rate_limit.get('retry_after', 60)
        
        if hasattr(e.response, 'status_code'):
            if e.response.status_code == 429:  # Too Many Requests
                logger.warning(f"Rate limit exceeded for {feed_name}, waiting {retry_after} seconds")
                time.sleep(retry_after)
                return True
            elif e.response.status_code >= 500:  # Server errors
                logger.warning(f"Server error for {feed_name}, retrying after {retry_after} seconds")
                time.sleep(retry_after)
                return True
            elif e.response.status_code == 403:  # Forbidden
                logger.error(f"Access forbidden for {feed_name}")
                return False
            elif e.response.status_code == 404:  # Not Found
                logger.error(f"Feed not found for {feed_name}")
                return False
        
        logger.error(f"Request failed for {feed_name}: {str(e)}")
        return False 