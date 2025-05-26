"""Environment-driven proxy manager with automatic rotation."""
import os
import logging
from typing import Optional, Dict, List
from proxy import Proxy as PyProxy
import requests

logger = logging.getLogger(__name__)

class ProxyManager:
    """Environment-driven proxy manager with automatic rotation."""
    
    def __init__(self, country_code: Optional[str] = None, validate_proxies: bool = True):
        """Initialize proxy manager.
        
        Args:
            country_code: Optional country code to filter proxies (e.g., "US")
            validate_proxies: Whether to validate proxies after fetching
        """
        self.country_code = country_code
        self.validate_proxies = validate_proxies
        self.proxy_client = None
        self.current_proxy = None
        self.proxy_list = []
        self.proxy_index = 0
        self.enabled = self._should_enable_proxies()
        
        if self.enabled:
            self._initialize_proxy_client()
    
    def _should_enable_proxies(self) -> bool:
        """Check if proxies should be enabled based on environment variables.
        
        Returns:
            True if proxies should be enabled
        """
        # Check environment variables
        enable_proxies = os.getenv("ENABLE_PROXIES", "false").lower() == "true"
        proxy_list_path = os.getenv("PROXY_LIST_PATH")
        
        if proxy_list_path and os.path.exists(proxy_list_path):
            logger.info(f"Using proxy list from {proxy_list_path}")
            return True
            
        if enable_proxies:
            logger.info("Proxies enabled via ENABLE_PROXIES environment variable")
            return True
            
        logger.info("Proxies disabled - set ENABLE_PROXIES=true or provide PROXY_LIST_PATH to enable")
        return False
    
    def _initialize_proxy_client(self) -> None:
        """Initialize the proxy client."""
        try:
            # Check if we have a custom proxy list
            proxy_list_path = os.getenv("PROXY_LIST_PATH")
            
            if proxy_list_path and os.path.exists(proxy_list_path):
                self._load_proxy_list_from_file(proxy_list_path)
            else:
                # Use py-proxy to fetch proxies
                logger.info("Fetching proxies automatically...")
                self.proxy_client = PyProxy(
                    country=self.country_code,
                    validate_proxies=self.validate_proxies
                )
                
                if self.validate_proxies:
                    logger.info("Validating fetched proxies...")
                    self.proxy_client.validate_proxies()
                
                self.current_proxy = self.proxy_client.proxy
                logger.info(f"Initialized with proxy: {self.current_proxy}")
                
        except Exception as e:
            logger.error(f"Failed to initialize proxy client: {str(e)}")
            self.enabled = False
    
    def _load_proxy_list_from_file(self, file_path: str) -> None:
        """Load proxy list from file.
        
        Args:
            file_path: Path to file containing proxy list (one per line)
        """
        try:
            with open(file_path, 'r') as f:
                self.proxy_list = [line.strip() for line in f if line.strip()]
            
            if self.proxy_list:
                self.current_proxy = self.proxy_list[0].split(':')
                logger.info(f"Loaded {len(self.proxy_list)} proxies from file")
            else:
                logger.warning("No proxies found in file")
                self.enabled = False
                
        except Exception as e:
            logger.error(f"Failed to load proxy list from {file_path}: {str(e)}")
            self.enabled = False
    
    def get_proxy_dict(self) -> Optional[Dict[str, str]]:
        """Get current proxy formatted for requests library.
        
        Returns:
            Proxy dictionary for requests or None if proxies disabled
        """
        if not self.enabled or not self.current_proxy:
            return None
            
        try:
            if self.proxy_client:
                # Using py-proxy
                return self.proxy_client.format_proxy(self.current_proxy)
            else:
                # Using custom proxy list
                if isinstance(self.current_proxy, list) and len(self.current_proxy) >= 2:
                    ip, port = self.current_proxy[0], self.current_proxy[1]
                    proxy_url = f"http://{ip}:{port}"
                    return {
                        'http': proxy_url,
                        'https': proxy_url
                    }
                    
        except Exception as e:
            logger.error(f"Failed to format proxy: {str(e)}")
            
        return None
    
    def cycle_proxy(self, valid_only: bool = True) -> bool:
        """Cycle to the next proxy.
        
        Args:
            valid_only: Only cycle to validated proxies (if using py-proxy)
            
        Returns:
            True if successfully cycled to new proxy
        """
        if not self.enabled:
            return False
            
        try:
            if self.proxy_client:
                # Using py-proxy
                old_proxy = self.current_proxy
                self.proxy_client.cycle(valid_only=valid_only)
                self.current_proxy = self.proxy_client.proxy
                
                if self.current_proxy != old_proxy:
                    logger.info(f"Cycled to new proxy: {self.current_proxy}")
                    return True
                else:
                    logger.warning("No new proxy available for cycling")
                    return False
                    
            else:
                # Using custom proxy list
                if len(self.proxy_list) > 1:
                    self.proxy_index = (self.proxy_index + 1) % len(self.proxy_list)
                    self.current_proxy = self.proxy_list[self.proxy_index].split(':')
                    logger.info(f"Cycled to proxy: {self.current_proxy}")
                    return True
                else:
                    logger.warning("Only one proxy available, cannot cycle")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to cycle proxy: {str(e)}")
            return False
    
    def test_current_proxy(self) -> bool:
        """Test if current proxy is working.
        
        Returns:
            True if proxy is working
        """
        if not self.enabled or not self.current_proxy:
            return True  # No proxy means direct connection
            
        try:
            if self.proxy_client:
                # Using py-proxy
                result = self.proxy_client.test_proxy(self.current_proxy)
                return result == 1
            else:
                # Test custom proxy manually
                proxy_dict = self.get_proxy_dict()
                if proxy_dict:
                    response = requests.get(
                        "http://httpbin.org/ip",
                        proxies=proxy_dict,
                        timeout=10
                    )
                    return response.status_code == 200
                    
        except Exception as e:
            logger.error(f"Proxy test failed: {str(e)}")
            
        return False
    
    def get_working_proxy(self, max_attempts: int = 5) -> Optional[Dict[str, str]]:
        """Get a working proxy, cycling through available proxies if needed.
        
        Args:
            max_attempts: Maximum number of proxies to test
            
        Returns:
            Working proxy dictionary or None
        """
        if not self.enabled:
            return None
            
        for attempt in range(max_attempts):
            if self.test_current_proxy():
                return self.get_proxy_dict()
            else:
                logger.warning(f"Proxy {self.current_proxy} failed test, cycling...")
                if not self.cycle_proxy():
                    break
                    
        logger.error("No working proxy found after testing available proxies")
        return None
    
    def get_status(self) -> Dict[str, any]:
        """Get proxy manager status.
        
        Returns:
            Status dictionary
        """
        return {
            "enabled": self.enabled,
            "current_proxy": self.current_proxy,
            "country_code": self.country_code,
            "validate_proxies": self.validate_proxies,
            "proxy_count": len(self.proxy_list) if self.proxy_list else "unknown",
            "using_custom_list": bool(self.proxy_list)
        }

# Global proxy manager instance
proxy_manager = ProxyManager() 