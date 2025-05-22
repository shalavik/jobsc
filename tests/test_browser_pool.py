"""Tests for BrowserPool functionality."""
import pytest
import time
import pathlib
from unittest.mock import MagicMock, Mock, patch, PropertyMock
from jobradar.fetchers import BrowserPool
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext
import threading

class MockPlaywright:
    def __init__(self):
        self.chromium = MagicMock()

    def start(self):
        return self

    def stop(self):
        pass

class MockBrowser:
    def __init__(self):
        self.contexts = []

    def new_context(self, **kwargs):
        context = MagicMock()
        self.contexts.append(context)
        return context

    def close(self):
        pass

class MockLock:
    def __init__(self):
        self.acquired = False
        
    def acquire(self, timeout=None):
        self.acquired = True
        return True
        
    def release(self):
        self.acquired = False
        
    def __enter__(self):
        self.acquire()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False

@pytest.fixture
def mock_sync_playwright():
    return MockPlaywright()

@pytest.fixture
def mock_browser():
    return MockBrowser()

@pytest.fixture
def browser_pool():
    """Create a browser pool for testing."""
    with patch('jobradar.fetchers.sync_playwright', return_value=MockPlaywright()):
        pool = BrowserPool(max_contexts=2, test_mode=True)
        # Replace the lock with our mock
        pool.lock = MockLock()
        yield pool
        # Ensure cleanup happens even if test fails
        try:
            pool.cleanup()
        except Exception as e:
            print(f"Error during browser pool cleanup: {str(e)}")

def test_browser_pool_initialization(browser_pool):
    """Test browser pool initialization."""
    assert browser_pool.max_contexts == 2
    assert browser_pool.contexts == {}
    assert browser_pool._initialized is False
    assert browser_pool.test_mode is True

def test_browser_pool_initialize(browser_pool):
    """Test browser pool initialize method."""
    with patch.object(browser_pool, 'playwright', None):
        with patch.object(browser_pool, 'browser', None):
            browser_pool.initialize()
            assert browser_pool._initialized is True

def test_get_context_new(browser_pool):
    """Test getting a new context."""
    with patch.object(browser_pool, '_initialized', True):
        with patch.object(browser_pool, 'browser') as mock_browser:
            mock_context = MagicMock()
            mock_browser.new_context.return_value = mock_context
            
            context = browser_pool.get_context('example.com')
            
            mock_browser.new_context.assert_called_once()
            assert 'example.com' in browser_pool.contexts
            assert browser_pool.contexts['example.com'][0] == mock_context

def test_get_context_existing(browser_pool):
    """Test getting an existing context."""
    with patch.object(browser_pool, '_initialized', True):
        mock_context = MagicMock()
        browser_pool.contexts = {'example.com': (mock_context, time.time())}
        
        context = browser_pool.get_context('example.com')
        
        assert context == mock_context

def test_cleanup_old_contexts(browser_pool):
    """Test cleaning up old contexts when max is exceeded."""
    with patch.object(browser_pool, '_initialized', True):
        # Create more contexts than max_contexts
        mock_context1 = MagicMock()
        mock_context2 = MagicMock()
        mock_context3 = MagicMock()
        
        # Set up contexts with timestamps (oldest first)
        browser_pool.contexts = {
            'site1.com': (mock_context1, time.time() - 100),
            'site2.com': (mock_context2, time.time() - 50),
            'site3.com': (mock_context3, time.time())
        }
        
        # Private method would normally be called by get_context
        browser_pool._cleanup_old_contexts()
        
        # Should have removed the oldest context (site1)
        assert 'site1.com' not in browser_pool.contexts
        assert 'site2.com' in browser_pool.contexts
        assert 'site3.com' in browser_pool.contexts
        
        mock_context1.close.assert_called_once()
        mock_context2.close.assert_not_called()
        mock_context3.close.assert_not_called()

def test_save_cookies(browser_pool, tmp_path):
    """Test saving cookies for a domain."""
    with patch.object(browser_pool, '_initialized', True):
        # Check test mode - should exit early
        browser_pool.save_cookies('example.com')
        
        # Now test without test_mode
        browser_pool.test_mode = False
        
        mock_context = MagicMock()
        cookies = [{'name': 'test', 'value': '123'}]
        mock_context.cookies.return_value = cookies
        
        browser_pool.contexts = {'example.com': (mock_context, time.time())}
        
        with patch('builtins.open', MagicMock()):
            with patch('json.dump') as mock_json_dump:
                with patch('pathlib.Path.mkdir'):
                    browser_pool.save_cookies('example.com')
                    mock_json_dump.assert_called_once()
                    args, _ = mock_json_dump.call_args
                    assert args[0] == cookies

def test_cleanup(browser_pool):
    """Test cleanup method closes all contexts and browser."""
    with patch.object(browser_pool, '_initialized', True):
        mock_context1 = MagicMock()
        mock_context2 = MagicMock()
        
        browser_pool.contexts = {
            'site1.com': (mock_context1, time.time()),
            'site2.com': (mock_context2, time.time())
        }
        
        with patch.object(browser_pool, 'browser') as mock_browser:
            with patch.object(browser_pool, 'playwright') as mock_playwright:
                browser_pool.cleanup()
                
                mock_context1.close.assert_called_once()
                mock_context2.close.assert_called_once()
                mock_browser.close.assert_called_once()
                mock_playwright.stop.assert_called_once()
                
                assert browser_pool.contexts == {}
                assert browser_pool._initialized is False

@pytest.mark.parametrize("domain,headers,cookies", [
    ("example.com", None, None),
    ("example.com", {"User-Agent": "test-agent"}, None),
    ("example.com", None, {"session": "abc123"}),
    ("example.com", {"User-Agent": "test-agent"}, {"session": "abc123"}),
])
def test_get_context_with_parameters(browser_pool, domain, headers, cookies):
    """Test getting context with different parameters."""
    with patch.object(browser_pool, '_initialized', True):
        with patch.object(browser_pool, 'browser') as mock_browser:
            mock_context = MagicMock()
            mock_browser.new_context.return_value = mock_context
            
            context = browser_pool.get_context(domain, headers, cookies)
            
            mock_browser.new_context.assert_called_once()
            assert domain in browser_pool.contexts
            
            if cookies:
                mock_context.add_cookies.assert_called()

@pytest.fixture(scope="session", autouse=True)
def cleanup_playwright():
    """Ensure all Playwright resources are cleaned up after tests."""
    yield
    try:
        # Kill any lingering Playwright processes
        import subprocess
        import sys
        if sys.platform == "darwin":  # macOS
            subprocess.run(["pkill", "-f", "playwright"], capture_output=True)
        elif sys.platform == "win32":  # Windows
            subprocess.run(["taskkill", "/F", "/IM", "playwright.exe"], capture_output=True)
        elif sys.platform == "linux":  # Linux
            subprocess.run(["pkill", "-f", "playwright"], capture_output=True)
    except Exception as e:
        print(f"Failed to kill Playwright processes: {str(e)}") 