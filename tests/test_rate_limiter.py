"""Tests for the rate limiter functionality."""
import pytest
import time
from datetime import datetime, timedelta
from requests.exceptions import RequestException
from jobradar.rate_limiter import RateLimiter

@pytest.fixture
def rate_limiter():
    """Create a rate limiter instance for testing."""
    return RateLimiter()

@pytest.fixture
def rate_limit_config():
    """Create a sample rate limit configuration."""
    return {
        'requests_per_minute': 2,
        'retry_after': 1
    }

def test_wait_if_needed_respects_rate_limit(rate_limiter, rate_limit_config):
    """Test that wait_if_needed respects the rate limit."""
    feed_name = "test_feed"
    # Use a high requests_per_minute to avoid enforced wait
    high_rate_limit = {'requests_per_minute': 100, 'retry_after': 1}
    low_rate_limit = {'requests_per_minute': 1, 'retry_after': 1}

    # First request with high rate limit should not wait
    start_time = time.time()
    rate_limiter.wait_if_needed(feed_name, high_rate_limit)
    first_request_time = time.time() - start_time
    assert first_request_time < 0.1  # Should be almost instant

    # Second request with low rate limit should wait
    start_time = time.time()
    rate_limiter.wait_if_needed(feed_name, low_rate_limit)
    second_request_time = time.time() - start_time
    assert second_request_time >= 1.0  # Should wait at least 1 second

def test_wait_if_needed_respects_retry_after(rate_limiter, rate_limit_config):
    """Test that wait_if_needed respects the retry_after setting."""
    feed_name = "test_feed"
    
    # First request
    rate_limiter.wait_if_needed(feed_name, rate_limit_config)
    
    # Second request should wait for retry_after
    start_time = time.time()
    rate_limiter.wait_if_needed(feed_name, rate_limit_config)
    wait_time = time.time() - start_time
    assert wait_time >= rate_limit_config['retry_after']

def test_handle_request_exception_rate_limit(rate_limiter, rate_limit_config):
    """Test handling of rate limit exceptions."""
    feed_name = "test_feed"
    
    # Create a mock exception with status code 429
    class MockResponse:
        def __init__(self):
            self.status_code = 429
    
    class MockException(RequestException):
        def __init__(self):
            self.response = MockResponse()
    
    # Should retry for rate limit
    assert rate_limiter.handle_request_exception(MockException(), feed_name, rate_limit_config) is True

def test_handle_request_exception_server_error(rate_limiter, rate_limit_config):
    """Test handling of server error exceptions."""
    feed_name = "test_feed"
    
    # Create a mock exception with status code 500
    class MockResponse:
        def __init__(self):
            self.status_code = 500
    
    class MockException(RequestException):
        def __init__(self):
            self.response = MockResponse()
    
    # Should retry for server error
    assert rate_limiter.handle_request_exception(MockException(), feed_name, rate_limit_config) is True

def test_handle_request_exception_forbidden(rate_limiter, rate_limit_config):
    """Test handling of forbidden exceptions."""
    feed_name = "test_feed"
    
    # Create a mock exception with status code 403
    class MockResponse:
        def __init__(self):
            self.status_code = 403
    
    class MockException(RequestException):
        def __init__(self):
            self.response = MockResponse()
    
    # Should not retry for forbidden
    assert rate_limiter.handle_request_exception(MockException(), feed_name, rate_limit_config) is False

def test_handle_request_exception_not_found(rate_limiter, rate_limit_config):
    """Test handling of not found exceptions."""
    feed_name = "test_feed"
    
    # Create a mock exception with status code 404
    class MockResponse:
        def __init__(self):
            self.status_code = 404
    
    class MockException(RequestException):
        def __init__(self):
            self.response = MockResponse()
    
    # Should not retry for not found
    assert rate_limiter.handle_request_exception(MockException(), feed_name, rate_limit_config) is False 