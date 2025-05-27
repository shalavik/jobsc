"""Headless browser fetching with advanced automation.

This module provides the HeadlessFetcher class which uses Playwright
for sophisticated job scraping that requires JavaScript execution,
user interaction simulation, and security challenge handling.
"""

from typing import List, Optional, Dict, Any
import logging
import time
import random
import re
from urllib.parse import urlparse
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_sync
from bs4 import BeautifulSoup

from ..models import Job, Feed
from .browser_pool import BrowserPool
from .parsers import HTMLParsers

logger = logging.getLogger(__name__)


class HeadlessFetcher:
    """Advanced headless browser automation for job fetching.
    
    Features:
    - JavaScript execution
    - User behavior simulation
    - Security challenge detection and handling
    - Dynamic content loading
    - Cookie and session management
    """
    
    def __init__(self, browser_pool: BrowserPool) -> None:
        """Initialize the headless fetcher.
        
        Args:
            browser_pool: Shared browser pool instance
        """
        self.browser_pool = browser_pool
        self.html_parsers = HTMLParsers()
    
    def fetch(self, feed: Feed) -> List[Job]:
        """Fetch jobs using headless browser automation.
        
        Args:
            feed: Feed configuration object
            
        Returns:
            List of Job objects
        """
        logger.info(f"Starting headless fetch for {feed.name}")
        
        # Extract domain for browser context
        domain = urlparse(feed.url).netloc
        
        # Get browser context
        context = self.browser_pool.get_context(
            domain=domain,
            headers=feed.headers,
            cookies=feed.cookies
        )
        
        page = context.new_page()
        
        try:
            # Apply stealth to avoid detection
            stealth_sync(page)
            
            # Navigate to the page
            logger.info(f"Navigating to {feed.url}")
            page.goto(feed.url, wait_until='networkidle', timeout=30000)
            
            # Check for security challenges
            if self._detect_security_challenge(page):
                logger.warning(f"Security challenge detected for {feed.url}")
                if not self._handle_security_challenge(page, feed):
                    logger.error(f"Failed to handle security challenge for {feed.url}")
                    return []
            
            # Simulate human behavior
            self._simulate_human_behavior(page)
            
            # Wait for content to load
            page.wait_for_timeout(2000)
            
            # Handle dynamic loading if needed
            self._handle_dynamic_loading(page, feed)
            
            # Get final HTML content
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Save cookies for future use
            self.browser_pool.save_cookies(domain)
            
            # Parse jobs using site-specific parsers
            jobs = self.html_parsers.parse_jobs(soup, feed)
            
            logger.info(f"Headless fetch completed: {len(jobs)} jobs from {feed.name}")
            return jobs
            
        except PlaywrightTimeoutError:
            logger.error(f"Timeout loading {feed.url}")
            return []
        except Exception as e:
            logger.error(f"Error in headless fetch for {feed.url}: {e}")
            return []
        finally:
            try:
                page.close()
            except Exception as e:
                logger.warning(f"Error closing page: {e}")
    
    def _detect_security_challenge(self, page: Page) -> bool:
        """Detect if the page contains security challenges.
        
        Args:
            page: Playwright page object
            
        Returns:
            True if security challenge detected
        """
        try:
            # Wait a moment for any challenges to appear
            page.wait_for_timeout(2000)
            
            # Check for common security challenge indicators
            challenge_selectors = [
                'iframe[src*="captcha"]',
                'iframe[src*="recaptcha"]',
                '[data-sitekey]',  # reCAPTCHA
                '.cf-challenge',  # Cloudflare
                '#challenge-form',  # Generic challenge
                '.challenge-container',
                '[id*="captcha"]',
                '[class*="captcha"]'
            ]
            
            for selector in challenge_selectors:
                if page.query_selector(selector):
                    logger.info(f"Security challenge detected: {selector}")
                    return True
            
            # Check page title and content for challenge indicators
            title = page.title().lower()
            challenge_keywords = ['challenge', 'captcha', 'verification', 'security check', 'blocked']
            
            if any(keyword in title for keyword in challenge_keywords):
                logger.info(f"Security challenge detected in title: {title}")
                return True
            
            # Check for challenge-related text content
            page_text = page.text_content('body').lower()
            if any(keyword in page_text for keyword in challenge_keywords):
                logger.info("Security challenge detected in page content")
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Error detecting security challenge: {e}")
            return False
    
    def _handle_security_challenge(self, page: Page, feed: Feed) -> bool:
        """Attempt to handle security challenges.
        
        Args:
            page: Playwright page object
            feed: Feed configuration object
            
        Returns:
            True if challenge was successfully handled
        """
        try:
            logger.info("Attempting to handle security challenge")
            
            # For Cloudflare challenges, wait longer
            cf_challenge = page.query_selector('.cf-challenge')
            if cf_challenge:
                logger.info("Cloudflare challenge detected, waiting for automatic resolution")
                page.wait_for_timeout(10000)
                
                # Check if challenge was resolved
                if not page.query_selector('.cf-challenge'):
                    logger.info("Cloudflare challenge resolved")
                    return True
            
            # For other challenges, try basic interactions
            # Look for buttons that might complete the challenge
            continue_buttons = page.query_selector_all('button, input[type="submit"], a')
            
            for button in continue_buttons:
                button_text = button.text_content().lower()
                if any(word in button_text for word in ['continue', 'proceed', 'verify', 'submit']):
                    logger.info(f"Attempting to click continue button: {button_text}")
                    button.click()
                    page.wait_for_timeout(3000)
                    
                    # Check if we're past the challenge
                    if not self._detect_security_challenge(page):
                        logger.info("Challenge resolved by clicking continue button")
                        return True
                    break
            
            # If still challenged, try waiting longer
            logger.info("Waiting for challenge to resolve automatically")
            page.wait_for_timeout(15000)
            
            return not self._detect_security_challenge(page)
            
        except Exception as e:
            logger.error(f"Error handling security challenge: {e}")
            return False
    
    def _simulate_human_behavior(self, page: Page) -> None:
        """Simulate human-like behavior on the page.
        
        Args:
            page: Playwright page object
        """
        try:
            # Random mouse movements
            for _ in range(random.randint(2, 5)):
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                page.mouse.move(x, y)
                page.wait_for_timeout(random.randint(100, 500))
            
            # Random scroll
            scroll_distance = random.randint(200, 800)
            page.evaluate(f"window.scrollTo(0, {scroll_distance})")
            page.wait_for_timeout(random.randint(500, 1500))
            
            # Scroll back up a bit
            scroll_up = random.randint(100, scroll_distance // 2)
            page.evaluate(f"window.scrollTo(0, {scroll_distance - scroll_up})")
            page.wait_for_timeout(random.randint(300, 1000))
            
        except Exception as e:
            logger.debug(f"Error simulating human behavior: {e}")
    
    def _handle_dynamic_loading(self, page: Page, feed: Feed) -> None:
        """Handle dynamic content loading.
        
        Args:
            page: Playwright page object
            feed: Feed configuration object
        """
        try:
            # Look for "Load More" buttons
            load_more_selectors = [
                'button:has-text("Load More")',
                'button:has-text("Show More")',
                'a:has-text("Load More")',
                '.load-more',
                '.show-more',
                '[data-testid*="load"]'
            ]
            
            for selector in load_more_selectors:
                try:
                    load_button = page.query_selector(selector)
                    if load_button and load_button.is_visible():
                        logger.info(f"Clicking load more button: {selector}")
                        load_button.click()
                        page.wait_for_timeout(3000)
                        break
                except Exception as e:
                    logger.debug(f"Error with load more button {selector}: {e}")
                    continue
            
            # Handle infinite scroll
            if 'indeed.com' in feed.url or 'linkedin.com' in feed.url:
                logger.info("Handling infinite scroll")
                for _ in range(3):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)
            
        except Exception as e:
            logger.debug(f"Error handling dynamic loading: {e}") 