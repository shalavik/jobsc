"""
TDD Tests for JobRadar Model Validation

Tests drive validation requirements for Job and Feed models.
"""

import pytest
from datetime import datetime
from jobradar.models import Job, Feed


class TestJobValidation:
    """Test Job model validation rules."""
    
    def test_job_requires_id(self):
        """Job must have non-empty ID."""
        with pytest.raises(ValueError, match="Job ID is required"):
            Job(id="", title="Test", company="Corp", url="http://test.com", source="test")
    
    def test_job_requires_title(self):
        """Job must have non-empty title."""
        with pytest.raises(ValueError, match="Job title is required"):
            Job(id="123", title="", company="Corp", url="http://test.com", source="test")
    
    def test_job_valid_creation(self):
        """Valid job should create successfully."""
        job = Job(
            id="valid_id",
            title="Test Job",
            company="Test Corp",
            url="https://example.com/job",
            source="test_source"
        )
        assert job.id == "valid_id"
        assert job.title == "Test Job"
    
    def test_job_skills_defaults_to_list(self):
        """Skills should default to empty list."""
        job = Job(id="1", title="Job", company="Corp", url="http://test.com", source="test")
        assert job.skills == []
        assert isinstance(job.skills, list)
    
    def test_job_equality_by_id(self):
        """Jobs with same ID should be equal."""
        job1 = Job(id="same", title="Job 1", company="Corp1", url="http://1.com", source="s1")
        job2 = Job(id="same", title="Job 2", company="Corp2", url="http://2.com", source="s2")
        assert job1 == job2
    
    def test_job_hashable(self):
        """Jobs should be hashable for use in sets."""
        job1 = Job(id="1", title="Job", company="Corp", url="http://test.com", source="test")
        job2 = Job(id="2", title="Job", company="Corp", url="http://test.com", source="test")
        job_set = {job1, job2}
        assert len(job_set) == 2


class TestFeedValidation:
    """Test Feed model validation rules."""
    
    def test_feed_requires_url(self):
        """Feed must have non-empty URL."""
        with pytest.raises(ValueError, match="Feed URL is required"):
            Feed(name="test", url="", type="rss", parser="rss")
    
    def test_feed_valid_creation(self):
        """Valid feed should create successfully."""
        feed = Feed(
            name="test_feed",
            url="https://example.com/rss",
            type="rss", 
            parser="rss"
        )
        assert feed.name == "test_feed"
        assert feed.url == "https://example.com/rss"
    
    def test_feed_defaults(self):
        """Feed should have proper defaults."""
        feed = Feed(name="test", url="http://test.com", type="rss", parser="rss")
        assert feed.cache_duration == 30
        assert feed.error_count == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 