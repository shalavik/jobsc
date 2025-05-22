"""Data-driven tests for error handling functionality."""
import pytest
import logging
from unittest.mock import Mock, patch, call
import requests
from playwright.sync_api import Error as PlaywrightError
from jobradar.error_handling import ErrorHandler

@pytest.fixture
def error_handler():
    """Create an error handler instance for testing."""
    handler = ErrorHandler()
    handler.testing_mode = True  # Enable testing mode for predictable backoff
    return handler

# Test data for different types of errors
error_scenarios = [
    {
        'name': "http_timeout",
        'error': requests.exceptions.Timeout("Connection timed out"),
        'feed_name': "indeed",
        'expected_retry': True,
        'expected_log_level': "warning"
    },
    {
        'name': "http_connection_error",
        'error': requests.exceptions.ConnectionError("Connection refused"),
        'feed_name': "linkedin",
        'expected_retry': True,
        'expected_log_level': "warning"
    },
    {
        'name': "http_too_many_redirects",
        'error': requests.exceptions.TooManyRedirects("Too many redirects"),
        'feed_name': "glassdoor",
        'expected_retry': False,
        'expected_log_level': "error"
    },
    {
        'name': "playwright_timeout",
        'error': PlaywrightError("Timeout 30000ms exceeded"),
        'feed_name': "monster",
        'expected_retry': True,
        'expected_log_level': "warning"
    },
    {
        'name': "playwright_navigation",
        'error': PlaywrightError("Navigation failed: net::ERR_CONNECTION_REFUSED"),
        'feed_name': "ziprecruiter",
        'expected_retry': True,
        'expected_log_level': "warning"
    },
    {
        'name': "generic_exception",
        'error': Exception("Unknown error occurred"),
        'feed_name': "dice",
        'expected_retry': False,
        'expected_log_level': "error"
    },
    {
        'name': "value_error",
        'error': ValueError("Invalid value"),
        'feed_name': "github-jobs",
        'expected_retry': False,
        'expected_log_level': "error"
    }
]

@pytest.mark.parametrize("test_case", error_scenarios)
def test_handle_error(error_handler, monkeypatch, test_case, caplog):
    """Test error handling for different types of errors using DDT."""
    # Configure logger
    caplog.set_level(logging.DEBUG)
    
    # Mock time.sleep to avoid actual waiting
    monkeypatch.setattr("time.sleep", lambda x: None)
    
    # Call the error handler
    result = error_handler.handle_error(
        test_case['error'],
        test_case['feed_name'],
        retry_count=1,
        max_retries=3
    )
    
    # Check if retry decision is correct
    assert result == test_case['expected_retry']
    
    # Check if the correct log level was used
    expected_level = getattr(logging, test_case['expected_log_level'].upper())
    assert any(record.levelno == expected_level for record in caplog.records)
    
    # Check if feed name is mentioned in the log
    assert any(test_case['feed_name'] in record.message for record in caplog.records)
    
    # Check error message is in the log rather than error type
    error_message = str(test_case['error'])
    assert any(error_message in record.message for record in caplog.records)

# Test data for specific HTTP error status codes
http_error_status_codes = [
    {
        'name': "not_found_404",
        'status_code': 404,
        'feed_name': "indeed",
        'expected_retry': False,
        'expected_log_level': "error"
    },
    {
        'name': "server_error_500",
        'status_code': 500,
        'feed_name': "linkedin",
        'expected_retry': True,
        'expected_log_level': "warning"
    },
    {
        'name': "forbidden_403",
        'status_code': 403,
        'feed_name': "glassdoor",
        'expected_retry': False,
        'expected_log_level': "error"
    },
    {
        'name': "too_many_requests_429",
        'status_code': 429,
        'feed_name': "monster",
        'expected_retry': True,
        'expected_log_level': "warning"
    },
    {
        'name': "bad_gateway_502",
        'status_code': 502,
        'feed_name': "ziprecruiter",
        'expected_retry': True,
        'expected_log_level': "warning"
    }
]

@pytest.mark.parametrize("test_case", http_error_status_codes)
def test_handle_http_error(error_handler, monkeypatch, test_case, caplog):
    """Test handling of HTTP error status codes using DDT."""
    # Configure logger
    caplog.set_level(logging.DEBUG)
    
    # Mock time.sleep to avoid actual waiting
    monkeypatch.setattr("time.sleep", lambda x: None)
    
    # Create a mock response with the given status code
    mock_response = Mock()
    mock_response.status_code = test_case['status_code']
    
    # Call the HTTP error handler
    result = error_handler.handle_http_error(
        mock_response,
        test_case['feed_name']
    )
    
    # Check if retry decision is correct
    assert result == test_case['expected_retry']
    
    # Check if the correct log level was used
    expected_level = getattr(logging, test_case['expected_log_level'].upper())
    assert any(record.levelno == expected_level for record in caplog.records)
    
    # Check if feed name and status code are mentioned in the log
    assert any(test_case['feed_name'] in record.message for record in caplog.records)
    assert any(str(test_case['status_code']) in record.message for record in caplog.records)

# Test data for retry scenarios - now with exact expected values
retry_scenarios = [
    {
        'name': "first_retry",
        'retry_count': 1,
        'max_retries': 3,
        'expected_retry': True,
        'expected_backoff_range': (10, 10)  # First retry, base backoff * 2^1 (no jitter)
    },
    {
        'name': "second_retry",
        'retry_count': 2,
        'max_retries': 3,
        'expected_retry': True,
        'expected_backoff_range': (20, 20)  # Second retry, base backoff * 2^2 (no jitter)
    },
    {
        'name': "max_retries_reached",
        'retry_count': 3,
        'max_retries': 3,
        'expected_retry': False,
        'expected_backoff_range': (0, 0)  # No backoff as no retry
    },
    {
        'name': "beyond_max_retries",
        'retry_count': 4,
        'max_retries': 3,
        'expected_retry': False,
        'expected_backoff_range': (0, 0)  # No backoff as no retry
    }
]

@pytest.mark.parametrize("test_case", retry_scenarios)
def test_retry_with_backoff(error_handler, monkeypatch, test_case, caplog):
    """Test retry mechanism with exponential backoff using DDT."""
    # Configure logger
    caplog.set_level(logging.DEBUG)
    
    # Mock sleep function to avoid actual waiting
    mock_sleep = Mock()
    monkeypatch.setattr("time.sleep", mock_sleep)
    
    # Call the retry function
    error = requests.exceptions.Timeout("Connection timed out")
    feed_name = "test_feed"
    
    result = error_handler.handle_error(
        error,
        feed_name,
        retry_count=test_case['retry_count'],
        max_retries=test_case['max_retries']
    )
    
    # Check if retry decision is correct
    assert result == test_case['expected_retry']
    
    # Check if correct backoff was applied
    min_backoff, max_backoff = test_case['expected_backoff_range']
    if min_backoff > 0:
        mock_sleep.assert_called_once()
        actual_backoff = mock_sleep.call_args[0][0]
        assert min_backoff <= actual_backoff <= max_backoff, \
            f"Expected backoff between {min_backoff} and {max_backoff}, got {actual_backoff}"
    else:
        mock_sleep.assert_not_called()

# Test data for notification scenarios
notification_thresholds = [
    {
        'name': "below_error_threshold",
        'error_count': 2,
        'threshold': 5,
        'expected_notification': False
    },
    {
        'name': "at_error_threshold",
        'error_count': 5,
        'threshold': 5,
        'expected_notification': True
    },
    {
        'name': "above_error_threshold",
        'error_count': 7,
        'threshold': 5,
        'expected_notification': True
    }
]

@pytest.mark.parametrize("test_case", notification_thresholds)
def test_error_notifications(error_handler, monkeypatch, test_case):
    """Test error notification threshold functionality using DDT."""
    # Mock the notification function
    mock_notify = Mock()
    monkeypatch.setattr(error_handler, "send_notification", mock_notify)
    
    # Set up the error counts
    feed_name = "test_feed"
    error_handler.error_counts = {feed_name: test_case['error_count']}
    
    # Call the check_notification_threshold function
    error_handler.check_notification_threshold(feed_name, test_case['threshold'])
    
    # Check if notification was sent correctly
    if test_case['expected_notification']:
        mock_notify.assert_called_once()
        assert feed_name in mock_notify.call_args[0][0]
        assert str(test_case['error_count']) in mock_notify.call_args[0][0]
    else:
        mock_notify.assert_not_called() 