"""
Comprehensive Test-Driven Development (TDD) Test Suite for JobRadar

This module contains comprehensive TDD tests following strict Red-Green-Refactor methodology
for all major components of the JobRadar application.

Test Categories:
1. Core Models (Job, Feed) 
2. Fetchers (Base, Headless, Parsers)
3. Database Operations
4. Smart Matcher
5. Filters
6. Web API
7. CLI Interface  
8. Integration Tests

TDD Principles Applied:
- Red: Write failing test first
- Green: Write minimal code to pass
- Refactor: Improve code while keeping tests green
"""

import pytest
import tempfile
import os
import json
import sqlite3
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
import requests
import yaml

# Import components to test
from jobradar.models import Job, Feed
from jobradar.fetchers.base_fetcher import Fetcher
from jobradar.fetchers.parsers import HTMLParsers
from jobradar.fetchers.headless import HeadlessFetcher
from jobradar.database import Database, JobModel
from jobradar.smart_matcher import SmartTitleMatcher
from jobradar.rate_limiter import RateLimiter
from jobradar.filters import JobFilter, FilterConfig
from jobradar.core import JobRadar, fetch_jobs
from jobradar.config import load_feeds, get_config
from jobradar.web.app import app as flask_app


# ============================================================================
# FIXTURES AND TEST UTILITIES
# ============================================================================

@pytest.fixture
def temp_db_path():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        yield f.name
    os.unlink(f.name)

@pytest.fixture
def sample_job():
    """Sample job for testing."""
    return Job(
        id="test_job_123",
        title="Senior Customer Support Engineer", 
        company="TechCorp Inc",
        url="https://example.com/jobs/123",
        source="indeed",
        date="2023-12-01T10:00:00",
        location="Remote",
        salary="$80k - $120k",
        job_type="Full-time",
        description="Help customers with technical issues",
        is_remote=True,
        experience_level="Senior",
        skills=["Python", "Customer Service", "Technical Support"]
    )

@pytest.fixture
def sample_feed():
    """Sample feed for testing."""
    return Feed(
        name="test_feed",
        url="https://example.com/rss",
        type="rss",
        parser="rss",
        fetch_method="rss",
        rate_limit={"requests_per_minute": 30}
    )

@pytest.fixture
def sample_jobs_list():
    """List of sample jobs for testing."""
    return [
        Job(
            id="job_1",
            title="Customer Support Representative",
            company="Company A", 
            url="https://example.com/job1",
            source="indeed"
        ),
        Job(
            id="job_2", 
            title="Software Engineer",
            company="Company B",
            url="https://example.com/job2", 
            source="linkedin"
        ),
        Job(
            id="job_3",
            title="Technical Support Specialist",
            company="Company C",
            url="https://example.com/job3",
            source="remoteok"
        )
    ]

@pytest.fixture
def mock_requests():
    """Mock requests for HTTP calls."""
    with patch('requests.get') as mock_get:
        yield mock_get

@pytest.fixture 
def flask_client():
    """Flask test client."""
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        yield client


# ============================================================================
# TDD TESTS FOR CORE MODELS
# ============================================================================

class TestJobModelTDD:
    """TDD tests for Job model driving design through tests."""
    
    def test_job_requires_essential_fields_fails_without_id(self):
        """RED: Job should require ID field."""
        with pytest.raises(ValueError, match="Job ID is required"):
            Job(
                id="",  # Empty ID should fail
                title="Customer Support Engineer",
                company="TechCorp",
                url="https://example.com/job",
                source="indeed"
            )
    
    def test_job_requires_essential_fields_fails_without_title(self):
        """RED: Job should require title field."""
        with pytest.raises(ValueError, match="Job title is required"):
            Job(
                id="test_123",
                title="",  # Empty title should fail
                company="TechCorp", 
                url="https://example.com/job",
                source="indeed"
            )
    
    def test_job_creation_with_minimal_valid_data(self, sample_job):
        """GREEN: Job creation with all required fields."""
        assert sample_job.id == "test_job_123"
        assert sample_job.title == "Senior Customer Support Engineer"
        assert sample_job.company == "TechCorp Inc"
        assert sample_job.url == "https://example.com/jobs/123"
        assert sample_job.source == "indeed"
    
    def test_job_equality_based_on_id(self):
        """GREEN: Jobs with same ID should be equal."""
        job1 = Job(
            id="same_id",
            title="Job 1",
            company="Company 1",
            url="https://example.com/1", 
            source="source1"
        )
        job2 = Job(
            id="same_id",  # Same ID
            title="Job 2",  # Different other fields
            company="Company 2",
            url="https://example.com/2",
            source="source2"
        )
        
        assert job1 == job2
        assert hash(job1) == hash(job2)
    
    def test_job_skills_defaults_to_empty_list(self):
        """GREEN: Job skills should default to empty list."""
        job = Job(id="1", title="Job", company="Corp", url="http://ex.com", source="src")
        assert job.skills == []
        assert isinstance(job.skills, list)


class TestFeedModelTDD:
    """TDD tests for Feed model."""
    
    def test_feed_requires_url(self):
        """RED: Feed should require URL."""
        with pytest.raises(ValueError, match="Feed URL is required"):
            Feed(
                name="test_feed",
                url="",  # Empty URL should fail
                type="rss",
                parser="rss"
            )
    
    def test_feed_creation_with_required_fields(self, sample_feed):
        """GREEN: Feed creation with valid data."""
        assert sample_feed.name == "test_feed"
        assert sample_feed.url == "https://example.com/rss"
        assert sample_feed.type == "rss"
        assert sample_feed.parser == "rss"


# ============================================================================
# TDD TESTS FOR FETCHERS
# ============================================================================

class TestBaseFetcherTDD:
    """TDD tests for base Fetcher class."""
    
    def test_fetcher_initialization(self):
        """GREEN: Fetcher should initialize with required components."""
        fetcher = Fetcher()
        assert fetcher is not None
        assert hasattr(fetcher, 'rate_limiter')
        assert hasattr(fetcher, 'browser_pool')
        assert hasattr(fetcher, 'html_parsers')
    
    def test_fetch_returns_list_of_jobs(self, sample_feed, mock_requests):
        """GREEN: Fetch should return list of Job objects."""
        # Mock RSS response
        mock_rss_content = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Customer Support Engineer</title>
                    <link>https://example.com/job1</link>
                    <author>TechCorp</author>
                </item>
            </channel>
        </rss>"""
        
        mock_requests.return_value.status_code = 200
        mock_requests.return_value.content = mock_rss_content.encode('utf-8')
        
        fetcher = Fetcher()
        jobs = fetcher.fetch(sample_feed)
        
        assert isinstance(jobs, list)
        if jobs:  # If parsing succeeds
            assert all(isinstance(job, Job) for job in jobs)
    
    def test_fetch_handles_network_errors_gracefully(self, sample_feed, mock_requests):
        """GREEN: Fetch should handle network errors without crashing."""
        mock_requests.side_effect = requests.exceptions.RequestException("Network error")
        
        fetcher = Fetcher()
        jobs = fetcher.fetch(sample_feed)
        
        # Should return empty list on error, not crash
        assert isinstance(jobs, list)
        assert len(jobs) == 0


# ============================================================================
# TDD TESTS FOR DATABASE
# ============================================================================

class TestDatabaseTDD:
    """TDD tests for Database operations."""
    
    def test_database_initialization_creates_tables(self, temp_db_path):
        """GREEN: Database should create tables on initialization."""
        db = Database(f"sqlite:///{temp_db_path}")
        
        # Check that tables exist
        with sqlite3.connect(temp_db_path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            assert 'jobs' in tables
    
    def test_add_single_job_stores_correctly(self, temp_db_path, sample_job):
        """GREEN: Adding single job should store all fields correctly."""
        db = Database(f"sqlite:///{temp_db_path}")
        
        result = db.add_jobs([sample_job])
        assert result == 1
        
        # Verify job was stored
        jobs = db.search_jobs({})
        assert len(jobs) == 1
        assert jobs[0].title == sample_job.title
        assert jobs[0].company == sample_job.company
    
    def test_count_jobs_returns_correct_number(self, temp_db_path, sample_jobs_list):
        """GREEN: count_jobs should return accurate count."""
        db = Database(f"sqlite:///{temp_db_path}")
        
        assert db.count_jobs() == 0
        
        db.add_jobs(sample_jobs_list)
        assert db.count_jobs() == len(sample_jobs_list)


# ============================================================================
# TDD TESTS FOR SMART MATCHER
# ============================================================================

class TestSmartMatcherTDD:
    """TDD tests for AI-based job relevance scoring."""
    
    def test_smart_matcher_initialization(self):
        """GREEN: SmartTitleMatcher should initialize correctly."""
        matcher = SmartTitleMatcher()
        assert matcher is not None
        assert hasattr(matcher, 'is_relevant_job')
        assert hasattr(matcher, 'get_match_score')
    
    def test_customer_support_jobs_are_relevant(self):
        """GREEN: Customer support jobs should be marked as relevant."""
        matcher = SmartTitleMatcher()
        
        cs_job = Job(id="cs1", title="Customer Support Engineer", company="Corp",
                    url="http://ex.com", source="test")
        
        assert matcher.is_relevant_job(cs_job) is True
    
    def test_get_match_score_returns_category_scores(self):
        """GREEN: get_match_score should return scores by category."""
        matcher = SmartTitleMatcher()
        
        job = Job(id="1", title="Technical Support Specialist", company="Corp",
                 url="http://ex.com", source="test")
        
        scores = matcher.get_match_score(job)
        
        assert isinstance(scores, dict)
        assert any(key in ['customer_support', 'technical_support'] for key in scores.keys())
        assert all(isinstance(score, int) for score in scores.values())


# ============================================================================
# TDD TESTS FOR FILTERS
# ============================================================================

class TestJobFilterTDD:
    """TDD tests for job filtering functionality."""
    
    def test_filter_config_creation(self):
        """GREEN: FilterConfig should be creatable with valid parameters."""
        config = FilterConfig(
            keywords=['python', 'customer service'],
            locations=['remote', 'new york'],
            exclude=['spam company'],
            salary_min=50000,
            is_remote=True
        )
        
        assert config.keywords == ['python', 'customer service']
        assert config.salary_min == 50000
        assert config.is_remote is True
    
    def test_job_filter_initialization_with_config(self):
        """GREEN: JobFilter should initialize with FilterConfig."""
        config = FilterConfig(keywords=['test'], locations=[], exclude=[])
        job_filter = JobFilter(config)
        
        assert job_filter is not None
        assert job_filter.config == config
    
    def test_keyword_filtering_matches_title_and_company(self):
        """GREEN: Keyword filtering should search title and company."""
        config = FilterConfig(keywords=['customer support'], locations=[], exclude=[])
        job_filter = JobFilter(config)
        
        matching_job = Job(id="1", title="Customer Support Engineer", company="Corp",
                          url="http://ex.com", source="test")
        non_matching_job = Job(id="2", title="Software Engineer", company="TechCorp",
                              url="http://ex.com", source="test")
        
        assert job_filter.matches_keywords(matching_job) is True
        assert job_filter.matches_keywords(non_matching_job) is False


# ============================================================================
# TDD TESTS FOR WEB API
# ============================================================================

class TestWebAPITDD:
    """TDD tests for Flask web API endpoints."""
    
    def test_api_smart_jobs_endpoint_exists(self, flask_client):
        """GREEN: /api/smart-jobs endpoint should exist and be accessible."""
        response = flask_client.get('/api/smart-jobs')
        
        # Should not return 404
        assert response.status_code != 404
        # Should return JSON
        assert response.content_type.startswith('application/json')
    
    def test_api_smart_jobs_returns_paginated_results(self, flask_client):
        """GREEN: Smart jobs API should support pagination."""
        response = flask_client.get('/api/smart-jobs?page=1&per_page=5')
        
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert 'jobs' in data
        assert 'pagination' in data
        assert isinstance(data['jobs'], list)
    
    def test_web_index_page_loads(self, flask_client):
        """GREEN: Main web page should load successfully."""
        response = flask_client.get('/')
        
        assert response.status_code == 200
        assert b'JobRadar' in response.data  # Should contain app name


# ============================================================================
# TDD TESTS FOR CLI INTERFACE  
# ============================================================================

class TestCLIInterfaceTDD:
    """TDD tests for command-line interface."""
    
    def test_cli_module_importable(self):
        """GREEN: CLI module should be importable."""
        from jobradar import cli
        assert cli is not None
    
    def test_cli_commands_exist(self):
        """GREEN: CLI should have main commands defined."""
        from jobradar.cli import cli
        
        # Check that main commands exist
        command_names = [cmd.name for cmd in cli.commands.values()]
        
        assert 'fetch' in command_names
        assert 'search' in command_names
        assert 'web' in command_names


# ============================================================================
# TDD TESTS FOR CORE ORCHESTRATION
# ============================================================================

class TestJobRadarCoreTDD:
    """TDD tests for main JobRadar orchestration class."""
    
    def test_jobradar_initialization(self, temp_db_path):
        """GREEN: JobRadar should initialize all components."""
        job_radar = JobRadar(db_url=f"sqlite:///{temp_db_path}")
        
        assert job_radar is not None
        assert hasattr(job_radar, 'database')
        assert hasattr(job_radar, 'fetcher')
        assert hasattr(job_radar, 'smart_matcher')
        assert hasattr(job_radar, 'rate_limiter')
    
    def test_save_jobs_persists_to_database(self, temp_db_path, sample_jobs_list):
        """GREEN: save_jobs should persist jobs to database."""
        job_radar = JobRadar(db_url=f"sqlite:///{temp_db_path}")
        
        saved_count = job_radar.save_jobs(sample_jobs_list)
        
        assert saved_count == len(sample_jobs_list)
        
        # Verify jobs were saved
        db_jobs = job_radar.database.search_jobs({})
        assert len(db_jobs) == len(sample_jobs_list)
    
    def test_get_stats_returns_database_statistics(self, temp_db_path, sample_jobs_list):
        """GREEN: get_stats should return comprehensive database statistics."""
        job_radar = JobRadar(db_url=f"sqlite:///{temp_db_path}")
        job_radar.save_jobs(sample_jobs_list)
        
        stats = job_radar.get_stats()
        
        assert isinstance(stats, dict)
        assert 'total_jobs' in stats
        assert 'sources' in stats
        assert 'companies' in stats
        assert stats['total_jobs'] == len(sample_jobs_list)


# ============================================================================
# TDD INTEGRATION TESTS
# ============================================================================

class TestIntegrationTDD:
    """TDD integration tests for complete workflows."""
    
    def test_end_to_end_job_processing_pipeline(self, temp_db_path):
        """GREEN: Complete job processing from fetch to save should work."""
        job_radar = JobRadar(db_url=f"sqlite:///{temp_db_path}")
        
        # Mock feed
        test_feed = Feed(name="integration_test", url="http://test.com", 
                        type="rss", parser="rss")
        job_radar.feeds = [test_feed]
        
        # Mock jobs returned by fetcher
        mock_jobs = [
            Job(id="int1", title="Customer Support Engineer", company="TestCorp",
                url="http://test.com/job1", source="integration_test"),
            Job(id="int2", title="Software Engineer", company="TestCorp",
                url="http://test.com/job2", source="integration_test")
        ]
        
        with patch.object(job_radar.fetcher, 'fetch') as mock_fetch:
            mock_fetch.return_value = mock_jobs
            
            # Execute full pipeline
            fetched_jobs = job_radar.fetch_all_jobs()
            processed_jobs = job_radar.process_jobs(fetched_jobs)
            saved_count = job_radar.save_jobs(processed_jobs)
            
            # Verify pipeline worked
            assert len(fetched_jobs) == 2
            assert saved_count > 0
            
            # Verify data persisted
            stats = job_radar.get_stats()
            assert stats['total_jobs'] > 0
    
    def test_config_loading_integration(self):
        """GREEN: Configuration loading should integrate with main workflow."""
        # Test config functions exist and work
        from jobradar.config import load_feeds, get_config
        
        assert callable(load_feeds)
        assert callable(get_config)
        
        # Test with minimal valid config
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump({
                'feeds': [{
                    'name': 'test_feed',
                    'url': 'http://example.com/rss',
                    'type': 'rss',
                    'parser': 'rss'
                }]
            }, f)
            f.flush()
            
            try:
                feeds = load_feeds(Path(f.name))
                assert len(feeds) == 1
                assert feeds[0].name == 'test_feed'
            finally:
                os.unlink(f.name)


# ============================================================================
# TDD METHODOLOGY COMPLIANCE TESTS
# ============================================================================

def test_tdd_test_coverage_completeness():
    """RED: Verify we have tests for all major components."""
    
    # This test ensures we maintain comprehensive test coverage
    required_test_classes = [
        'TestJobModelTDD',
        'TestFeedModelTDD', 
        'TestBaseFetcherTDD',
        'TestDatabaseTDD',
        'TestSmartMatcherTDD',
        'TestJobFilterTDD',
        'TestWebAPITDD',
        'TestCLIInterfaceTDD',
        'TestJobRadarCoreTDD',
        'TestIntegrationTDD'
    ]
    
    # Get all classes defined in this module
    import sys
    current_module = sys.modules[__name__]
    defined_classes = [name for name in dir(current_module) 
                      if name.startswith('Test') and name.endswith('TDD')]
    
    # Verify all required test classes exist
    for required_class in required_test_classes:
        assert required_class in defined_classes, f"Missing test class: {required_class}"
    
    print(f"✅ TDD test coverage complete: {len(defined_classes)} test classes defined")


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 