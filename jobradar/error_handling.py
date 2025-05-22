"""Error handling and retry logic for job scraping."""
import logging
import time
import random
import requests
from typing import Any, Dict, Optional
from playwright.sync_api import Error as PlaywrightError

logger = logging.getLogger(__name__)

class ErrorHandler:
    """Handles errors and implements retry logic for job scraping."""
    
    def __init__(self):
        """Initialize the error handler."""
        self.error_counts: Dict[str, int] = {}
        self.base_backoff_time = 5  # Base backoff time in seconds
        self.testing_mode = False  # Set to True to disable jitter in tests
    
    def handle_error(self, error: Exception, feed_name: str, 
                    retry_count: int = 0, max_retries: int = 3) -> bool:
        """Handle errors and determine if retry is needed.
        
        Args:
            error: The exception that occurred
            feed_name: Name of the feed
            retry_count: Current retry count
            max_retries: Maximum retry attempts
            
        Returns:
            True if retry should be attempted, False otherwise
        """
        # Increment error count for this feed
        if feed_name not in self.error_counts:
            self.error_counts[feed_name] = 0
        self.error_counts[feed_name] += 1
        
        # Check if max retries exceeded
        if retry_count >= max_retries:
            logger.error(f"Max retries ({max_retries}) exceeded for {feed_name}")
            return False
        
        # Handle different types of errors
        if isinstance(error, requests.exceptions.Timeout):
            logger.warning(f"Timeout error for {feed_name}: {str(error)}")
            self._apply_backoff(retry_count)
            return True
            
        elif isinstance(error, requests.exceptions.ConnectionError):
            logger.warning(f"Connection error for {feed_name}: {str(error)}")
            self._apply_backoff(retry_count)
            return True
            
        elif isinstance(error, requests.exceptions.TooManyRedirects):
            logger.error(f"Too many redirects for {feed_name}: {str(error)}")
            return False
            
        elif isinstance(error, PlaywrightError):
            # Handle Playwright specific errors
            error_message = str(error).lower()
            if "timeout" in error_message or "navigation" in error_message:
                logger.warning(f"Playwright error for {feed_name}: {str(error)}")
                self._apply_backoff(retry_count)
                return True
            else:
                logger.error(f"Unhandled Playwright error for {feed_name}: {str(error)}")
                return False
                
        else:
            # Generic error handling
            logger.error(f"Unhandled error for {feed_name}: {type(error).__name__}: {str(error)}")
            return False
    
    def handle_http_error(self, response: requests.Response, feed_name: str) -> bool:
        """Handle HTTP error responses.
        
        Args:
            response: The HTTP response
            feed_name: Name of the feed
            
        Returns:
            True if retry should be attempted, False otherwise
        """
        status_code = response.status_code
        
        # Increment error count for this feed
        if feed_name not in self.error_counts:
            self.error_counts[feed_name] = 0
        self.error_counts[feed_name] += 1
        
        # Handle different HTTP status codes
        if status_code == 429:  # Too Many Requests
            logger.warning(f"Rate limit exceeded (429) for {feed_name}")
            time.sleep(60)  # Wait longer for rate limit errors
            return True
            
        elif status_code >= 500:  # Server errors
            logger.warning(f"Server error ({status_code}) for {feed_name}")
            time.sleep(self.base_backoff_time)
            return True
            
        elif status_code == 403:  # Forbidden
            logger.error(f"Access forbidden (403) for {feed_name}")
            return False
            
        elif status_code == 404:  # Not Found
            logger.error(f"Resource not found (404) for {feed_name}")
            return False
            
        else:  # Other client errors
            logger.error(f"HTTP error ({status_code}) for {feed_name}")
            return False
    
    def _apply_backoff(self, retry_count: int) -> None:
        """Apply exponential backoff with jitter.
        
        Args:
            retry_count: Current retry count
        """
        # Calculate backoff time with exponential increase
        backoff_time = self.base_backoff_time * (2 ** retry_count)
        
        # Add jitter (random variation) to avoid thundering herd problem
        # Skip jitter in testing mode for predictable results
        if self.testing_mode:
            jitter = 0
        else:
            jitter = random.uniform(0, 0.3 * backoff_time)
            
        total_backoff = backoff_time + jitter
        
        logger.info(f"Applying backoff: waiting {total_backoff:.2f} seconds before retry")
        time.sleep(total_backoff)
    
    def check_notification_threshold(self, feed_name: str, threshold: int = 5) -> None:
        """Check if error count has reached notification threshold.
        
        Args:
            feed_name: Name of the feed
            threshold: Error count threshold for notification
        """
        error_count = self.error_counts.get(feed_name, 0)
        
        if error_count >= threshold:
            message = f"High error rate detected for {feed_name}: {error_count} errors"
            logger.critical(message)
            self.send_notification(message)
    
    def send_notification(self, message: str) -> None:
        """Send notification about errors.
        
        Args:
            message: Notification message
        """
        # In a real implementation, this would send an email or push notification
        logger.info(f"Sending notification: {message}")
        # Implementation could use smtplib, requests to webhook, etc. 