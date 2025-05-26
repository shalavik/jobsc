"""Tests for proxy manager functionality."""
import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
from jobradar.ingest.proxy_manager import ProxyManager

class TestProxyManager:
    """Test proxy manager functionality."""
    
    def test_proxy_manager_disabled_by_default(self):
        """Test that proxy manager is disabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            manager = ProxyManager()
            assert not manager.enabled
            assert manager.get_proxy_dict() is None
    
    def test_proxy_manager_enabled_by_environment(self):
        """Test that proxy manager can be enabled via environment variable."""
        with patch.dict(os.environ, {"ENABLE_PROXIES": "true"}, clear=True):
            with patch('jobradar.ingest.proxy_manager.PyProxy') as mock_proxy:
                # Mock the proxy client
                mock_instance = MagicMock()
                mock_instance.proxy = ["127.0.0.1", "8080"]
                mock_instance.format_proxy.return_value = {
                    'http': 'http://127.0.0.1:8080',
                    'https': 'http://127.0.0.1:8080'
                }
                mock_proxy.return_value = mock_instance
                
                manager = ProxyManager()
                assert manager.enabled
                
                # Should have initialized proxy client
                mock_proxy.assert_called_once()
    
    def test_proxy_manager_with_custom_proxy_list(self):
        """Test proxy manager with custom proxy list file."""
        # Create temporary proxy list file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("127.0.0.1:8080\n")
            f.write("127.0.0.1:8081\n")
            f.write("127.0.0.1:8082\n")
            proxy_file = f.name
        
        try:
            with patch.dict(os.environ, {"PROXY_LIST_PATH": proxy_file}, clear=True):
                manager = ProxyManager()
                assert manager.enabled
                assert len(manager.proxy_list) == 3
                assert manager.current_proxy == ["127.0.0.1", "8080"]
        finally:
            os.unlink(proxy_file)
    
    def test_proxy_cycling_with_custom_list(self):
        """Test that proxy cycling works with custom proxy list."""
        # Create temporary proxy list file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("127.0.0.1:8080\n")
            f.write("127.0.0.1:8081\n")
            f.write("127.0.0.1:8082\n")
            proxy_file = f.name
        
        try:
            with patch.dict(os.environ, {"PROXY_LIST_PATH": proxy_file}, clear=True):
                manager = ProxyManager()
                
                # Initial proxy
                assert manager.current_proxy == ["127.0.0.1", "8080"]
                
                # Cycle to next proxy
                success = manager.cycle_proxy()
                assert success
                assert manager.current_proxy == ["127.0.0.1", "8081"]
                
                # Cycle again
                success = manager.cycle_proxy()
                assert success
                assert manager.current_proxy == ["127.0.0.1", "8082"]
                
                # Cycle back to first (wrap around)
                success = manager.cycle_proxy()
                assert success
                assert manager.current_proxy == ["127.0.0.1", "8080"]
        finally:
            os.unlink(proxy_file)
    
    def test_proxy_dict_formatting(self):
        """Test that proxy dictionary is formatted correctly."""
        # Create temporary proxy list file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("127.0.0.1:8080\n")
            proxy_file = f.name
        
        try:
            with patch.dict(os.environ, {"PROXY_LIST_PATH": proxy_file}, clear=True):
                manager = ProxyManager()
                
                proxy_dict = manager.get_proxy_dict()
                assert proxy_dict is not None
                assert proxy_dict['http'] == 'http://127.0.0.1:8080'
                assert proxy_dict['https'] == 'http://127.0.0.1:8080'
        finally:
            os.unlink(proxy_file)
    
    @patch('jobradar.ingest.proxy_manager.requests.get')
    def test_proxy_testing(self, mock_get):
        """Test proxy testing functionality."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        # Create temporary proxy list file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("127.0.0.1:8080\n")
            proxy_file = f.name
        
        try:
            with patch.dict(os.environ, {"PROXY_LIST_PATH": proxy_file}, clear=True):
                manager = ProxyManager()
                
                # Test current proxy
                result = manager.test_current_proxy()
                assert result is True
                
                # Verify request was made with proxy
                mock_get.assert_called_once()
                call_args = mock_get.call_args
                assert 'proxies' in call_args.kwargs
                assert call_args.kwargs['proxies']['http'] == 'http://127.0.0.1:8080'
        finally:
            os.unlink(proxy_file)
    
    @patch('jobradar.ingest.proxy_manager.requests.get')
    def test_get_working_proxy_cycles_on_failure(self, mock_get):
        """Test that get_working_proxy cycles through proxies on failure."""
        # Mock failed response for first proxy, success for second
        mock_responses = [
            MagicMock(status_code=500),  # First proxy fails
            MagicMock(status_code=200),  # Second proxy succeeds
        ]
        mock_get.side_effect = mock_responses
        
        # Create temporary proxy list file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("127.0.0.1:8080\n")  # This will fail
            f.write("127.0.0.1:8081\n")  # This will succeed
            proxy_file = f.name
        
        try:
            with patch.dict(os.environ, {"PROXY_LIST_PATH": proxy_file}, clear=True):
                manager = ProxyManager()
                
                # Should start with first proxy
                assert manager.current_proxy == ["127.0.0.1", "8080"]
                
                # Get working proxy should cycle to second proxy
                working_proxy = manager.get_working_proxy(max_attempts=2)
                
                assert working_proxy is not None
                assert working_proxy['http'] == 'http://127.0.0.1:8081'
                assert manager.current_proxy == ["127.0.0.1", "8081"]
                
                # Should have made 2 requests (one for each proxy)
                assert mock_get.call_count == 2
        finally:
            os.unlink(proxy_file)
    
    def test_proxy_manager_status(self):
        """Test proxy manager status reporting."""
        # Create temporary proxy list file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("127.0.0.1:8080\n")
            f.write("127.0.0.1:8081\n")
            proxy_file = f.name
        
        try:
            with patch.dict(os.environ, {"PROXY_LIST_PATH": proxy_file}, clear=True):
                manager = ProxyManager()
                
                status = manager.get_status()
                
                assert status['enabled'] is True
                assert status['current_proxy'] == ["127.0.0.1", "8080"]
                assert status['proxy_count'] == 2
                assert status['using_custom_list'] is True
        finally:
            os.unlink(proxy_file)
    
    def test_proxy_manager_with_py_proxy_library(self):
        """Test proxy manager using py-proxy library."""
        with patch.dict(os.environ, {"ENABLE_PROXIES": "true"}, clear=True):
            with patch('jobradar.ingest.proxy_manager.PyProxy') as mock_proxy:
                # Mock the proxy client
                mock_instance = MagicMock()
                mock_instance.proxy = ["192.168.1.1", "3128"]
                mock_instance.format_proxy.return_value = {
                    'http': 'http://192.168.1.1:3128',
                    'https': 'http://192.168.1.1:3128'
                }
                mock_instance.test_proxy.return_value = 1  # Success
                mock_proxy.return_value = mock_instance
                
                manager = ProxyManager()
                
                # Test proxy functionality
                assert manager.enabled
                proxy_dict = manager.get_proxy_dict()
                assert proxy_dict['http'] == 'http://192.168.1.1:3128'
                
                # Test proxy testing
                result = manager.test_current_proxy()
                assert result is True
                
                # Test cycling
                mock_instance.cycle.return_value = None
                mock_instance.proxy = ["192.168.1.2", "3128"]  # New proxy after cycle
                success = manager.cycle_proxy()
                assert success
                mock_instance.cycle.assert_called_once_with(valid_only=True)
    
    def test_disabled_proxy_manager_returns_none(self):
        """Test that disabled proxy manager returns None for all operations."""
        with patch.dict(os.environ, {}, clear=True):
            manager = ProxyManager()
            
            assert not manager.enabled
            assert manager.get_proxy_dict() is None
            assert manager.get_working_proxy() is None
            assert not manager.cycle_proxy()
            assert manager.test_current_proxy() is True  # No proxy = direct connection OK 