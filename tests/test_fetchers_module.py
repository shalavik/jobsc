"""Tests for the modular fetcher structure.

This module tests the new modular fetcher structure to ensure it maintains
backward compatibility and follows Python best practices.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from jobradar.fetchers import Fetcher, BrowserPool
from jobradar.fetchers.base_fetcher import Fetcher as BaseFetcher
from jobradar.fetchers.browser_pool import BrowserPool as BaseBrowserPool
from jobradar.fetchers.parsers import HTMLParsers
from jobradar.fetchers.headless import HeadlessFetcher
from jobradar.models import Feed, Job
from bs4 import BeautifulSoup


class TestModularStructure:
    """Test the modular structure and imports."""
    
    def test_backward_compatibility_imports(self):
        """Test that the old imports still work."""
        # These should work exactly as before
        from jobradar.fetchers import Fetcher, BrowserPool
        
        # Test instantiation
        fetcher = Fetcher()
        assert isinstance(fetcher, BaseFetcher)
        
        # Browser pool should also work
        pool = BrowserPool()
        assert isinstance(pool, BaseBrowserPool)
    
    def test_new_module_imports(self):
        """Test that the new modular imports work."""
        from jobradar.fetchers.base_fetcher import Fetcher
        from jobradar.fetchers.browser_pool import BrowserPool
        from jobradar.fetchers.parsers import HTMLParsers
        from jobradar.fetchers.headless import HeadlessFetcher
        
        # Test instantiation
        fetcher = Fetcher()
        pool = BrowserPool()
        parsers = HTMLParsers()
        headless = HeadlessFetcher(pool)
        
        assert all([fetcher, pool, parsers, headless])


class TestBaseFetcher:
    """Test the base fetcher functionality."""
    
    def test_fetcher_initialization(self):
        """Test fetcher initializes correctly."""
        fetcher = Fetcher()
        assert hasattr(fetcher, 'rate_limiter')
        assert hasattr(fetcher, 'browser_pool')
        assert hasattr(fetcher, 'html_parsers')
        assert hasattr(fetcher, 'headless_fetcher')
    
    def test_fetch_method_routing(self):
        """Test that fetch method correctly routes to appropriate handlers."""
        fetcher = Fetcher()
        
        # Mock the individual fetch methods
        fetcher._fetch_rss = Mock(return_value=[])
        fetcher._fetch_json = Mock(return_value=[])
        fetcher._fetch_html = Mock(return_value=[])
        fetcher.headless_fetcher.fetch = Mock(return_value=[])
        
        # Test RSS routing
        rss_feed = Feed(name="test", url="http://example.com", type="rss", parser="test", fetch_method="rss")
        fetcher.fetch(rss_feed)
        fetcher._fetch_rss.assert_called_once_with(rss_feed)
        
        # Test JSON routing
        json_feed = Feed(name="test", url="http://example.com", type="json", parser="test", fetch_method="json")
        fetcher.fetch(json_feed)
        fetcher._fetch_json.assert_called_once_with(json_feed)
        
        # Test HTML routing
        html_feed = Feed(name="test", url="http://example.com", type="html", parser="test", fetch_method="html")
        fetcher.fetch(html_feed)
        fetcher._fetch_html.assert_called_once_with(html_feed)
        
        # Test headless routing
        headless_feed = Feed(name="test", url="http://example.com", type="headless", parser="test", fetch_method="headless")
        fetcher.fetch(headless_feed)
        fetcher.headless_fetcher.fetch.assert_called_once_with(headless_feed)
    
    def test_unsupported_fetch_method_raises_error(self):
        """Test that unsupported fetch methods raise appropriate error."""
        fetcher = Fetcher()
        invalid_feed = Feed(name="test", url="http://example.com", type="invalid", parser="test", fetch_method="invalid")
        
        with pytest.raises(ValueError, match="Unsupported fetch_method"):
            fetcher.fetch(invalid_feed)


class TestBrowserPool:
    """Test the browser pool functionality."""
    
    def test_browser_pool_initialization(self):
        """Test browser pool initializes with correct parameters."""
        pool = BrowserPool(max_contexts=5, test_mode=True)
        assert pool.max_contexts == 5
        assert pool.test_mode is True
        assert pool.contexts == {}
        assert pool._initialized is False
    
    def test_proxy_loading(self):
        """Test proxy loading from environment."""
        with patch.dict('os.environ', {'PROXY_LIST': 'proxy1:8080,proxy2:8080'}, clear=False):
            pool = BrowserPool()
            pool._load_proxies()
            assert len(pool.proxies) == 2
            assert 'proxy1:8080' in pool.proxies
            assert 'proxy2:8080' in pool.proxies
    
    def test_proxy_rotation(self):
        """Test proxy rotation functionality."""
        pool = BrowserPool()
        pool.proxies = ['proxy1', 'proxy2', 'proxy3']
        
        # Test rotation
        assert pool.get_next_proxy() == 'proxy1'
        assert pool.get_next_proxy() == 'proxy2'
        assert pool.get_next_proxy() == 'proxy3'
        assert pool.get_next_proxy() == 'proxy1'  # Should wrap around
    
    def test_no_proxies_returns_none(self):
        """Test that get_next_proxy returns None when no proxies are available."""
        pool = BrowserPool()
        pool.proxies = []
        assert pool.get_next_proxy() is None


class TestHTMLParsers:
    """Test the HTML parsers functionality."""
    
    def test_parser_routing(self):
        """Test that parsers are correctly routed based on URL."""
        parsers = HTMLParsers()
        
        # Mock the specific parser methods
        parsers._parse_indeed = Mock(return_value=[])
        parsers._parse_remoteok = Mock(return_value=[])
        parsers._parse_generic = Mock(return_value=[])
        
        # Test Indeed routing
        indeed_feed = Feed(name="test", url="https://indeed.com/jobs", type="html", parser="indeed")
        soup = BeautifulSoup('<html></html>', 'html.parser')
        parsers.parse_jobs(soup, indeed_feed)
        parsers._parse_indeed.assert_called_once_with(soup, indeed_feed)
        
        # Test RemoteOK routing
        remoteok_feed = Feed(name="test", url="https://remoteok.io/remote-jobs", type="html", parser="remoteok")
        parsers.parse_jobs(soup, remoteok_feed)
        parsers._parse_remoteok.assert_called_once_with(soup, remoteok_feed)
        
        # Test generic routing for unknown sites
        unknown_feed = Feed(name="test", url="https://unknown.com/jobs", type="html", parser="unknown")
        parsers.parse_jobs(soup, unknown_feed)
        parsers._parse_generic.assert_called_once_with(soup, unknown_feed)
    
    def test_indeed_parser(self):
        """Test Indeed-specific parsing logic."""
        parsers = HTMLParsers()
        
        # Create mock HTML structure similar to Indeed
        html = '''
        <html>
            <div data-jk="12345">
                <h2><a><span title="Software Engineer">Software Engineer</span></a></h2>
                <span class="companyName">Tech Company</span>
            </div>
        </html>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        feed = Feed(name="indeed", url="https://indeed.com/jobs", type="html", parser="indeed")
        
        jobs = parsers._parse_indeed(soup, feed)
        
        assert len(jobs) == 1
        assert jobs[0].title == "Software Engineer"
        assert jobs[0].company == "Tech Company"
        assert jobs[0].id == "12345"
        assert jobs[0].source == "indeed"
    
    def test_remoteok_parser(self):
        """Test RemoteOK-specific parsing logic."""
        parsers = HTMLParsers()
        
        # Create mock HTML structure similar to RemoteOK
        html = '''
        <html>
            <tr class="job" data-id="67890">
                <td class="company">
                    <h2>Python Developer</h2>
                    <h3>Remote Tech Co</h3>
                    <a href="/job/67890">Apply</a>
                </td>
                <td class="tags">
                    <div class="tag">Python</div>
                    <div class="tag">Remote</div>
                </td>
            </tr>
        </html>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        feed = Feed(name="remoteok", url="https://remoteok.io/remote-jobs", type="html", parser="remoteok")
        
        jobs = parsers._parse_remoteok(soup, feed)
        
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Remote Tech Co"
        assert jobs[0].id == "67890"
        assert jobs[0].source == "remoteok"


class TestHeadlessFetcher:
    """Test the headless fetcher functionality."""
    
    def test_headless_fetcher_initialization(self):
        """Test headless fetcher initializes correctly."""
        pool = BrowserPool()
        headless = HeadlessFetcher(pool)
        assert headless.browser_pool is pool
        assert hasattr(headless, 'html_parsers')
    
    @patch('jobradar.fetchers.headless.stealth_sync')
    def test_security_challenge_detection(self, mock_stealth):
        """Test security challenge detection logic."""
        pool = BrowserPool(test_mode=True)
        headless = HeadlessFetcher(pool)
        
        # Mock page object
        mock_page = Mock()
        mock_page.wait_for_timeout = Mock()
        mock_page.query_selector = Mock(return_value=None)
        mock_page.title = Mock(return_value="Normal Page")
        mock_page.text_content = Mock(return_value="Normal content")
        
        # Test no challenge detected
        assert headless._detect_security_challenge(mock_page) is False
        
        # Test CAPTCHA detected
        mock_page.query_selector = Mock(return_value=Mock())  # Found a CAPTCHA selector
        assert headless._detect_security_challenge(mock_page) is True
        
        # Test challenge in title
        mock_page.query_selector = Mock(return_value=None)
        mock_page.title = Mock(return_value="Security Challenge")
        assert headless._detect_security_challenge(mock_page) is True


class TestErrorHandling:
    """Test error handling and resilience."""
    
    def test_fetcher_handles_network_errors(self):
        """Test that fetcher properly handles network errors."""
        fetcher = Fetcher()
        
        # Mock requests to raise an exception
        with patch('requests.get', side_effect=Exception("Network error")):
            feed = Feed(name="test", url="http://example.com", type="rss", parser="test", fetch_method="rss")
            
            with pytest.raises(Exception, match="Network error"):
                fetcher.fetch(feed)
    
    def test_browser_pool_handles_initialization_errors(self):
        """Test that browser pool handles initialization errors gracefully."""
        with patch('jobradar.fetchers.browser_pool.sync_playwright') as mock_playwright:
            mock_playwright.side_effect = Exception("Browser initialization failed")
            
            pool = BrowserPool()
            with pytest.raises(Exception, match="Browser initialization failed"):
                pool.initialize()


class TestTypeHints:
    """Test that type hints are properly implemented."""
    
    def test_fetcher_type_hints(self):
        """Test that Fetcher methods have proper type hints."""
        import inspect
        from jobradar.fetchers.base_fetcher import Fetcher
        
        # Check fetch method signature
        sig = inspect.signature(Fetcher.fetch)
        assert 'feed' in sig.parameters
        assert 'max_retries' in sig.parameters
        assert sig.parameters['max_retries'].default == 3
        
        # Check return annotation
        assert sig.return_annotation is not None
    
    def test_browser_pool_type_hints(self):
        """Test that BrowserPool methods have proper type hints."""
        import inspect
        from jobradar.fetchers.browser_pool import BrowserPool
        
        # Check initialization signature
        sig = inspect.signature(BrowserPool.__init__)
        assert 'max_contexts' in sig.parameters
        assert 'test_mode' in sig.parameters


if __name__ == '__main__':
    pytest.main([__file__]) 