"""Browser context pool management for headless fetching.

This module provides the BrowserPool class which manages Playwright browser
contexts for efficient web scraping with proxy rotation and cookie persistence.
"""

from typing import Dict, Tuple, Optional, Any
import os
import json
import time
import logging
import pathlib
import threading
import atexit
from playwright.sync_api import sync_playwright, BrowserContext, Browser, Playwright

logger = logging.getLogger(__name__)


class BrowserPool:
    """Manages a pool of browser contexts for headless fetching.
    
    Features:
    - Browser context pooling for efficiency
    - Proxy rotation support
    - Cookie persistence per domain
    - Automatic cleanup of old contexts
    """
    
    def __init__(self, max_contexts: int = 3, test_mode: bool = False) -> None:
        """Initialize the browser pool.
        
        Args:
            max_contexts: Maximum number of browser contexts to keep in the pool
            test_mode: Set to True for testing to avoid blocking operations
        """
        self.max_contexts = max_contexts
        self.contexts: Dict[str, Tuple[BrowserContext, float]] = {}  # domain -> (context, last_used_time)
        self.lock = threading.Lock()
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self._initialized = False
        self.test_mode = test_mode
        
        # Proxy rotation support
        self.proxies: list[str] = []
        self.current_proxy_index = 0
        self._load_proxies()
        
    def _load_proxies(self) -> None:
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
        
    def get_next_proxy(self) -> Optional[str]:
        """Get the next proxy in rotation.
        
        Returns:
            Next proxy URL or None if no proxies available
        """
        if not self.proxies:
            return None
            
        proxy = self.proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        return proxy
        
    def initialize(self) -> None:
        """Initialize the browser if not already initialized.
        
        Raises:
            Exception: If browser initialization fails
        """
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
    
    def get_context(self, domain: str, headers: Optional[Dict[str, str]] = None, 
                   cookies: Optional[Dict[str, str]] = None) -> BrowserContext:
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
            standard_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            if headers and 'User-Agent' in headers:
                standard_ua = headers['User-Agent']
            
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
    
    def save_cookies(self, domain: str) -> None:
        """Save cookies for a domain to disk.
        
        Args:
            domain: Domain to save cookies for
        """
        # Skip in test mode to avoid blocking
        if self.test_mode:
            return
            
        # Use a very short timeout to avoid deadlocks
        lock_acquired = self.lock.acquire(timeout=0.1)
        if not lock_acquired:
            logger.debug(f"Could not acquire lock to save cookies for {domain} (non-blocking)")
            return
            
        try:
            if domain in self.contexts:
                context, _ = self.contexts[domain]
                cookies = context.cookies()
                cookies_dir = pathlib.Path("cookies")
                cookies_dir.mkdir(exist_ok=True)
                cookies_file = cookies_dir / f"{domain}.json"
                
                with open(cookies_file, "w") as f:
                    json.dump(cookies, f, indent=2)
                logger.info(f"Saved {len(cookies)} cookies for {domain}")
        except Exception as e:
            logger.warning(f"Failed to save cookies for {domain}: {e}")
        finally:
            self.lock.release()
    
    def _cleanup_old_contexts(self) -> None:
        """Clean up contexts that haven't been used recently."""
        if len(self.contexts) <= self.max_contexts:
            return
            
        # Find the oldest context
        oldest_time = float('inf')
        oldest_domain = None
        
        for domain, (_, last_used) in self.contexts.items():
            if last_used < oldest_time:
                oldest_time = last_used
                oldest_domain = domain
        
        # Close and remove the oldest context
        if oldest_domain:
            try:
                context, _ = self.contexts[oldest_domain]
                context.close()
                del self.contexts[oldest_domain]
                logger.info(f"Cleaned up old context for {oldest_domain}")
            except Exception as e:
                logger.warning(f"Error cleaning up context for {oldest_domain}: {e}")
    
    def cleanup(self) -> None:
        """Clean up all browser resources."""
        try:
            # Close all contexts first
            for domain, (context, _) in self.contexts.items():
                try:
                    context.close()
                except Exception as e:
                    logger.warning(f"Error closing context for {domain}: {e}")
            
            # Close browser and playwright
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
                
            logger.info("Browser pool cleanup completed")
        except Exception as e:
            logger.error(f"Error during browser pool cleanup: {e}")
        finally:
            self._initialized = False
            self.contexts.clear() 