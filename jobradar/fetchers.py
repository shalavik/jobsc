"""Feed fetching functionality.

This module provides backward compatibility by importing the main classes
from the new modular structure. The original functionality has been split
into separate modules for better maintainability.

Use: from jobradar.fetchers import Fetcher, BrowserPool
"""

# Import from the new modular structure
from .fetchers import Fetcher, BrowserPool

# For backward compatibility, also import the main classes at this level
__all__ = ['Fetcher', 'BrowserPool']