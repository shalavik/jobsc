"""Job fetching functionality.

This module provides job fetching capabilities from various sources including
RSS feeds, JSON APIs, HTML scraping, and headless browser automation.

The module is organized into:
- browser_pool: Browser context management for headless fetching
- base_fetcher: Core Fetcher class and common functionality  
- parsers: Site-specific HTML parsers
- headless: Advanced headless browser automation
"""

from typing import List, Dict, Any, Optional, Union

from .base_fetcher import Fetcher
from .browser_pool import BrowserPool

__all__ = [
    'Fetcher',
    'BrowserPool'
] 