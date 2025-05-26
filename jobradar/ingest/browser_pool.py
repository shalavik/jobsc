"""Browser pool management for headless browsing."""
import logging
import time
import random
from typing import Dict, Any, List, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext

logger = logging.getLogger(__name__)

class BrowserPool:
    """Manages a pool of browser contexts for headless browsing."""
    
    def __init__(self, max_contexts: int = 3, context_lifetime: int = 600):
        """Initialize the browser pool.
        
        Args:
            max_contexts: Maximum number of browser contexts to keep in the pool
            context_lifetime: Lifetime of a browser context in seconds before rotation
        """
        self.max_contexts = max_contexts
        self.context_lifetime = context_lifetime
        self.browsers: List[Browser] = []
        self.contexts: Dict[str, Dict[str, Any]] = {}
        self.user_agents: List[str] = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36 Edg/91.0.864.41"
        ]
        self.playwright = None
        self.started = False
        
    def start(self) -> None:
        """Start the browser pool."""
        if self.started:
            return
            
        logger.info("Starting browser pool")
        self.playwright = sync_playwright().start()
        self.started = True
    
    def stop(self) -> None:
        """Stop the browser pool and release all resources."""
        if not self.started:
            return
            
        logger.info("Stopping browser pool")
        
        # Close all contexts
        for context_id, context_data in self.contexts.items():
            try:
                context_data['context'].close()
            except Exception as e:
                logger.error(f"Error closing browser context {context_id}: {str(e)}")
        
        # Close all browsers
        for browser in self.browsers:
            try:
                browser.close()
            except Exception as e:
                logger.error(f"Error closing browser: {str(e)}")
        
        # Stop playwright
        if self.playwright:
            self.playwright.stop()
            
        self.browsers = []
        self.contexts = {}
        self.playwright = None
        self.started = False
    
    def get_browser(self) -> Browser:
        """Get a browser instance.
        
        Returns:
            A browser instance
        """
        if not self.started:
            self.start()
            
        # Return an existing browser or create a new one
        if not self.browsers:
            browser = self._create_browser()
            self.browsers.append(browser)
            
        return self.browsers[0]
    
    def _create_browser(self) -> Browser:
        """Create a new browser instance.
        
        Returns:
            A new browser instance
        """
        if not self.playwright:
            raise RuntimeError("Browser pool not started")
            
        logger.info("Creating new browser instance")
        
        # Launch browser with stealth options
        browser = self.playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-web-security',
                '--disable-features=IsolateOrigins',
                '--disable-site-isolation-trials',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-setuid-sandbox',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--single-process',
                '--disable-gpu'
            ]
        )
        
        return browser
    
    def get_context(self, context_id: str = "default") -> BrowserContext:
        """Get a browser context.
        
        Args:
            context_id: Identifier for the context
            
        Returns:
            Browser context
        """
        # Create context if it doesn't exist or is expired
        if context_id not in self.contexts or self._is_context_expired(context_id):
            self._create_or_rotate_context(context_id)
            
        return self.contexts[context_id]['context']
    
    def _create_or_rotate_context(self, context_id: str) -> None:
        """Create a new context or rotate an existing one.
        
        Args:
            context_id: Identifier for the context
        """
        browser = self.get_browser()
        
        # Close the old context if it exists
        if context_id in self.contexts:
            try:
                self.contexts[context_id]['context'].close()
            except Exception as e:
                logger.error(f"Error closing browser context {context_id}: {str(e)}")
        
        # Enforce max contexts limit by closing oldest contexts
        if len(self.contexts) >= self.max_contexts:
            oldest_context_id = min(
                self.contexts.keys(),
                key=lambda k: self.contexts[k]['created_at']
            )
            try:
                self.contexts[oldest_context_id]['context'].close()
                del self.contexts[oldest_context_id]
            except Exception as e:
                logger.error(f"Error closing oldest browser context: {str(e)}")
        
        # Select a random user agent
        user_agent = random.choice(self.user_agents)
        
        # Create new context with stealth settings
        logger.info(f"Creating new browser context with ID {context_id}")
        context = browser.new_context(
            user_agent=user_agent,
            viewport={'width': random.randint(1024, 1280), 'height': random.randint(768, 900)},
            device_scale_factor=random.choice([1, 2]),
            java_script_enabled=True,
            has_touch=random.choice([True, False]),
            locale=random.choice(['en-US', 'en-GB', 'en-CA']),
            timezone_id=random.choice(['America/New_York', 'Europe/London', 'Asia/Tokyo']),
            permissions=['geolocation']
        )
        
        # Apply stealth scripts to make the browser harder to detect
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'es']
            });
            
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {
                        0: {type: "application/x-google-chrome-pdf"},
                        description: "Portable Document Format",
                        filename: "internal-pdf-viewer",
                        length: 1,
                        name: "Chrome PDF Plugin"
                    }
                ]
            });
        """)
        
        # Store the context with its creation timestamp
        self.contexts[context_id] = {
            'context': context,
            'created_at': time.time(),
            'user_agent': user_agent
        }
    
    def _is_context_expired(self, context_id: str) -> bool:
        """Check if a context has expired.
        
        Args:
            context_id: Identifier for the context
            
        Returns:
            True if the context has expired, False otherwise
        """
        if context_id not in self.contexts:
            return True
            
        context_data = self.contexts[context_id]
        age = time.time() - context_data['created_at']
        
        return age > self.context_lifetime 