"""Domain module for business logic and models."""

from .job import Job, JobSource
from .matching import SmartTitleMatcher, create_smart_matcher
from .deduplication import JobDeduplicator

__all__ = ['Job', 'JobSource', 'SmartTitleMatcher', 'create_smart_matcher', 'JobDeduplicator'] 