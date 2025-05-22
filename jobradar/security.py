"""Security challenge detection and handling for job scraping."""
import logging
import time
import random
import re
from typing import Tuple, Optional, Any, Dict

logger = logging.getLogger(__name__)

class SecurityChecker:
    """Handles detection and resolution of security challenges during scraping."""
    
    def __init__(self):
        """Initialize the security checker."""
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:88.0) Gecko/20100101 Firefox/88.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
        ]
        
        # Patterns for detecting different types of security challenges
        self.challenge_patterns = {
            'captcha': [
                r'captcha', r'verify.*(human|robot)', r'g-recaptcha', 
                r'security.*verification', r'puzzle', r'challenge'
            ],
            'security_verification': [
                r'security.*check', r'verify.*identity', r'verification',
                r'security.*challenge'
            ],
            'ddos_protection': [
                r'ddos.*protection', r'cloudflare', r'protection.*online.*attacks',
                r'security.*service'
            ],
            'ip_block': [
                r'access.*denied', r'ip.*blocked', r'too.*many.*requests',
                r'rate.*limit.*exceeded'
            ]
        }
    
    def detect_security_challenge(self, html: str) -> Tuple[bool, Optional[str]]:
        """Detect if the HTML contains a security challenge.
        
        Args:
            html: The HTML content to check
            
        Returns:
            Tuple of (is_challenge, challenge_type)
        """
        html = html.lower()
        
        for challenge_type, patterns in self.challenge_patterns.items():
            for pattern in patterns:
                if re.search(pattern, html):
                    logger.warning(f"Detected {challenge_type} security challenge")
                    return True, challenge_type
        
        return False, None
    
    def detect_security_challenge_from_screenshot(self, screenshot_path: str) -> Tuple[bool, Optional[str]]:
        """Detect security challenges from a screenshot using OCR.
        
        Args:
            screenshot_path: Path to the screenshot file
            
        Returns:
            Tuple of (is_challenge, challenge_type)
        """
        # In a real implementation, this would use an OCR library
        # For the test, we'll simulate OCR by returning predetermined text
        text = self.perform_ocr(screenshot_path)
        
        # Check the extracted text for security challenge patterns
        text = text.lower()
        for challenge_type, patterns in self.challenge_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    logger.warning(f"Detected {challenge_type} security challenge from screenshot")
                    return True, challenge_type
        
        return False, None
    
    def perform_ocr(self, screenshot_path: str) -> str:
        """Perform OCR on a screenshot to extract text.
        
        Args:
            screenshot_path: Path to the screenshot file
            
        Returns:
            Extracted text
        """
        # This is a mock implementation - in a real system, we'd use pytesseract or similar
        logger.info(f"Performing OCR on {screenshot_path}")
        return "This is placeholder text from OCR"
    
    def detect_challenge_in_browser(self, browser_pool: Any, url: str) -> bool:
        """Check if a URL leads to a security challenge page.
        
        Args:
            browser_pool: Browser pool to get a browser context
            url: URL to navigate to
            
        Returns:
            True if security challenge detected, False otherwise
        """
        browser = browser_pool.get_browser()
        page = browser.new_page()
        
        try:
            page.goto(url, wait_until="networkidle")
            
            # Check if we were redirected to a different URL
            if url not in page.url:
                logger.warning(f"Redirect detected: {url} -> {page.url}")
                
                # Check if the new URL or page title contains security challenge keywords
                title = page.title()
                if any(keyword in title.lower() for keyword in 
                       ['captcha', 'security', 'verify', 'robot', 'human']):
                    logger.warning(f"Security challenge detected in page title: {title}")
                    return True
            
            # Take screenshot for potential analysis
            # screenshot_path = f"security_check_{int(time.time())}.png"
            # page.screenshot(path=screenshot_path)
            # result, _ = self.detect_security_challenge_from_screenshot(screenshot_path)
            
            # Check page content 
            content = page.content()
            result, _ = self.detect_security_challenge(content)
            
            return result
            
        except Exception as e:
            logger.error(f"Error during security check navigation: {str(e)}")
            return False
        finally:
            page.close()
    
    def handle_security_challenge(self, challenge_type: str) -> bool:
        """Handle a detected security challenge.
        
        Args:
            challenge_type: Type of security challenge detected
            
        Returns:
            True if successfully handled, False otherwise
        """
        logger.warning(f"Handling {challenge_type} security challenge")
        
        if challenge_type == 'captcha':
            return self.change_user_agent()
        elif challenge_type == 'ddos_protection':
            return self.wait_and_retry()
        elif challenge_type == 'ip_block':
            return self.rotate_ip()
        else:
            return self.wait_and_retry()
    
    def change_user_agent(self) -> bool:
        """Change the user agent to avoid detection.
        
        Returns:
            True if successful, False otherwise
        """
        # In a real implementation, this would select a new user agent
        # For now, we'll just return False to indicate captchas can't be handled
        logger.info("Changing user agent")
        return False
    
    def wait_and_retry(self) -> bool:
        """Wait and retry after a cooldown period.
        
        Returns:
            True if successful, False otherwise
        """
        wait_time = random.randint(30, 120)
        logger.info(f"Waiting {wait_time} seconds before retrying")
        time.sleep(wait_time)
        return True
    
    def rotate_ip(self) -> bool:
        """Rotate the IP address to avoid IP-based blocks.
        
        Returns:
            True if successful, False otherwise
        """
        # In a real implementation, this would use a proxy service
        # For now, we'll just return True to simulate success
        logger.info("Rotating IP address")
        return True 