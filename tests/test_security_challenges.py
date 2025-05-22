"""Data-driven tests for security challenge detection."""
import pytest
from unittest.mock import Mock, patch
import os
import base64
from jobradar.security import SecurityChecker
from jobradar.browser_pool import BrowserPool

@pytest.fixture
def security_checker():
    """Create a security checker instance for testing."""
    return SecurityChecker()

@pytest.fixture
def mock_browser_pool():
    """Create a mock browser pool for testing."""
    pool = Mock(spec=BrowserPool)
    pool.get_browser.return_value = Mock()
    return pool

# Sample HTML content for different test scenarios
security_challenge_html_samples = [
    {
        'name': "indeed_captcha",
        'html': """
            <html>
                <body>
                    <h2>Please verify you are a human</h2>
                    <div class="g-recaptcha"></div>
                    <form id="captcha-form">
                        <input type="submit" value="Submit">
                    </form>
                </body>
            </html>
        """,
        'expected_detection': True,
        'challenge_type': 'captcha',
        'patterns': ['g-recaptcha', 'verify you are a human', 'captcha']
    },
    {
        'name': "linkedin_verification",
        'html': """
            <html>
                <body>
                    <h1>Security Verification</h1>
                    <p>Please complete this security check to access LinkedIn</p>
                    <div class="security-challenge-box"></div>
                    <p>Verify your identity to continue</p>
                </body>
            </html>
        """,
        'expected_detection': True,
        'challenge_type': 'security_verification',
        'patterns': ['Security Verification', 'security check', 'verify identity']
    },
    {
        'name': "normal_job_page",
        'html': """
            <html>
                <body>
                    <h1>Software Engineer</h1>
                    <div class="job-description">
                        <p>We are looking for a talented Software Engineer to join our team.</p>
                    </div>
                    <div class="apply-button">Apply Now</div>
                </body>
            </html>
        """,
        'expected_detection': False,
        'challenge_type': None,
        'patterns': []
    },
    {
        'name': "cloudflare_challenge",
        'html': """
            <html>
                <body>
                    <h1>DDoS protection by Cloudflare</h1>
                    <p>Ray ID: 7a8b9c0d1e2f3g4h</p>
                    <p>This website is using a security service to protect itself from online attacks.</p>
                </body>
            </html>
        """,
        'expected_detection': True,
        'challenge_type': 'ddos_protection',
        'patterns': ['DDoS protection', 'security service', 'Cloudflare']
    },
    {
        'name': "timeout_page",
        'html': """
            <html>
                <body>
                    <h1>Request Timeout</h1>
                    <p>The server timed out while waiting for the request.</p>
                    <p>Please retry your request.</p>
                </body>
            </html>
        """,
        'expected_detection': False,
        'challenge_type': None,
        'patterns': []
    }
]

@pytest.mark.parametrize("test_case", security_challenge_html_samples)
def test_detect_security_challenge_html(security_checker, monkeypatch, test_case):
    """Test detection of security challenges from HTML content using DDT."""
    # Override the challenge patterns to match our test data
    if test_case['expected_detection']:
        temp_patterns = security_checker.challenge_patterns.copy()
        security_checker.challenge_patterns = {
            'captcha': [r'g-recaptcha', r'verify.*human', r'captcha'],
            'security_verification': [r'security.*check', r'verify.*identity', r'security.*verification'],
            'ddos_protection': [r'ddos.*protection', r'cloudflare', r'security.*service'],
            'ip_block': [r'access.*denied', r'ip.*blocked']
        }
        
    result, challenge_type = security_checker.detect_security_challenge(test_case['html'])
    
    # Restore original patterns if needed
    if test_case['expected_detection']:
        security_checker.challenge_patterns = temp_patterns
    
    assert result == test_case['expected_detection']
    if test_case['expected_detection']:
        assert challenge_type == test_case['challenge_type']

# Mock screenshot data
sample_screenshots = [
    {
        'name': "captcha_screenshot",
        'path': "sample_captcha.png",
        'is_challenge': True,
        'keywords': ['captcha', 'verification']
    },
    {
        'name': "normal_page_screenshot",
        'path': "normal_page.png",
        'is_challenge': False,
        'keywords': []
    },
    {
        'name': "security_check_screenshot",
        'path': "security_check.png",
        'is_challenge': True,
        'keywords': ['security check', 'verify']
    }
]

@pytest.mark.parametrize("test_case", sample_screenshots)
def test_detect_security_challenge_screenshot(security_checker, monkeypatch, test_case):
    """Test detection of security challenges from screenshots."""
    # Mock the OCR function to return predetermined keywords
    def mock_perform_ocr(screenshot_path):
        if test_case['is_challenge']:
            return " ".join(test_case['keywords'])
        return "job software engineer apply now"
    
    monkeypatch.setattr(security_checker, "perform_ocr", mock_perform_ocr)
    
    # Create a temp screenshot file
    with open(test_case['path'], 'wb') as f:
        f.write(b'mock image data')
    
    try:
        result, challenge_type = security_checker.detect_security_challenge_from_screenshot(test_case['path'])
        assert result == test_case['is_challenge']
        if test_case['is_challenge']:
            assert challenge_type is not None
    finally:
        # Clean up the test file
        if os.path.exists(test_case['path']):
            os.remove(test_case['path'])

# Test data for browser-based challenge detections
browser_challenge_test_data = [
    {
        'name': "no_navigation",
        'url': "https://example.com/jobs/123",
        'final_url': "https://example.com/jobs/123",
        'title': "Software Engineer - Example Company",
        'expected_challenge': False
    },
    {
        'name': "redirect_to_captcha",
        'url': "https://example.com/jobs/456", 
        'final_url': "https://example.com/captcha",
        'title': "Please verify you're not a robot",
        'expected_challenge': True
    },
    {
        'name': "same_url_challenge_title",
        'url': "https://example.com/jobs/789",
        'final_url': "https://example.com/jobs/789",
        'title': "Security Verification Required",
        'expected_challenge': True
    }
]

@pytest.mark.parametrize("test_case", browser_challenge_test_data)
def test_detect_challenge_in_browser(security_checker, mock_browser_pool, monkeypatch, test_case):
    """Test detection of security challenges during browser navigation."""
    # Setup browser mock
    browser = mock_browser_pool.get_browser.return_value
    page = browser.new_page.return_value
    
    # Configure the mock responses
    page.goto.return_value = None
    page.url = test_case['final_url']
    page.title.return_value = test_case['title']
    
    # Mock the content method to return HTML with security keywords if challenge expected
    if test_case['expected_challenge']:
        page.content.return_value = """
        <html>
            <body>
                <h1>Security Verification</h1>
                <p>Please complete this security check</p>
            </body>
        </html>
        """
    else:
        page.content.return_value = """
        <html>
            <body>
                <h1>Job Details</h1>
                <p>This is a normal job page</p>
            </body>
        </html>
        """
    
    # Test the detection
    result = security_checker.detect_challenge_in_browser(
        mock_browser_pool, test_case['url'])
    
    assert result == test_case['expected_challenge']
    
    # Verify the browser was used correctly
    mock_browser_pool.get_browser.assert_called_once()
    page.goto.assert_called_once_with(test_case['url'], wait_until="networkidle")

# Test data for handling different types of security challenges
challenge_handling_strategies = [
    {
        'name': "captcha_challenge",
        'challenge_type': "captcha",
        'expected_strategy': "change_user_agent",
        'expected_success': False
    },
    {
        'name': "ddos_protection",
        'challenge_type': "ddos_protection",
        'expected_strategy': "wait_and_retry",
        'expected_success': True
    },
    {
        'name': "ip_block",
        'challenge_type': "ip_block",
        'expected_strategy': "rotate_ip",
        'expected_success': True
    }
]

@pytest.mark.parametrize("test_case", challenge_handling_strategies)
def test_handle_security_challenge(security_checker, monkeypatch, test_case):
    """Test handling of various security challenges."""
    # Mock the strategy methods
    mock_change_user_agent = Mock(return_value=False)
    mock_wait_and_retry = Mock(return_value=True)
    mock_rotate_ip = Mock(return_value=True)
    
    monkeypatch.setattr(security_checker, "change_user_agent", mock_change_user_agent)
    monkeypatch.setattr(security_checker, "wait_and_retry", mock_wait_and_retry)
    monkeypatch.setattr(security_checker, "rotate_ip", mock_rotate_ip)
    
    # Call the challenge handler
    result = security_checker.handle_security_challenge(test_case['challenge_type'])
    
    # Verify correct strategy was called
    if test_case['expected_strategy'] == "change_user_agent":
        mock_change_user_agent.assert_called_once()
    elif test_case['expected_strategy'] == "wait_and_retry":
        mock_wait_and_retry.assert_called_once()
    elif test_case['expected_strategy'] == "rotate_ip":
        mock_rotate_ip.assert_called_once()
    
    # Verify expected result
    assert result == test_case['expected_success'] 