"""Job parsers for different job sources."""

from .base import BaseParser
from .linkedin import LinkedInParser

__all__ = [
    'BaseParser',
    'LinkedInParser',
] 