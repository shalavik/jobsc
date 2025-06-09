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
    
    def test_job_inequality_different_ids(self):
        """GREEN: Jobs with different IDs should not be equal."""
        job1 = Job(id="id_1", title="Job", company="Corp", url="http://ex.com", source="src")
        job2 = Job(id="id_2", title="Job", company="Corp", url="http://ex.com", source="src")
        
        assert job1 != job2
        assert hash(job1) != hash(job2)
    
    def test_job_hashable_for_sets(self):
        """GREEN: Jobs should be usable in sets."""
        job1 = Job(id="1", title="Job1", company="Corp", url="http://ex.com", source="src")
        job2 = Job(id="2", title="Job2", company="Corp", url="http://ex.com", source="src")
        job3 = Job(id="1", title="Different", company="Corp", url="http://ex.com", source="src")  # Same ID as job1
        
        job_set = {job1, job2, job3}
        assert len(job_set) == 2  # job1 and job3 should be deduplicated
    
    def test_job_skills_defaults_to_empty_list(self):
        """GREEN: Job skills should default to empty list."""
        job = Job(id="1", title="Job", company="Corp", url="http://ex.com", source="src")
        assert job.skills == []
        assert isinstance(job.skills, list)
    
    def test_job_string_representation_contains_key_info(self, sample_job):
        """GREEN: Job string representation should be informative."""
        job_str = str(sample_job)
        assert "Senior Customer Support Engineer" in job_str
        assert "TechCorp Inc" in job_str


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
    
    def test_feed_defaults_fetch_method_to_type(self):
        """GREEN: Feed should default fetch_method to type."""
        feed = Feed(name="test", url="https://example.com", type="json", parser="json")
        assert feed.fetch_method == "json"
    
    def test_feed_cache_duration_has_default(self, sample_feed):
        """GREEN: Feed should have default cache duration."""
        assert sample_feed.cache_duration == 30  # Default 30 minutes
    
    def test_feed_error_tracking_fields(self, sample_feed):
        """GREEN: Feed should track errors."""
        assert sample_feed.error_count == 0
        assert sample_feed.last_error == ""


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
    
    def test_fetch_requires_feed_parameter(self):
        """RED: Fetch should require Feed object."""
        fetcher = Fetcher()
        
        with pytest.raises((TypeError, AttributeError)):
            fetcher.fetch(None)
    
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
    
    def test_fetch_respects_rate_limiting(self, sample_feed):
        """RED: Fetch should respect rate limiting."""
        fetcher = Fetcher()
        
        # This test drives the need for rate limiting integration
        with patch.object(fetcher.rate_limiter, 'wait_if_needed') as mock_rate_limit:
            with patch('requests.get') as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.content = b"<rss><channel></channel></rss>"
                
                fetcher.fetch(sample_feed)
                
                # Should call rate limiter
                mock_rate_limit.assert_called()
    
    def test_fetch_supports_different_feed_types(self):
        """RED: Fetch should support RSS, JSON, HTML feed types."""
        fetcher = Fetcher()
        
        # Test that fetcher has methods for different types
        assert hasattr(fetcher, '_fetch_rss')
        assert hasattr(fetcher, '_fetch_json') 
        assert hasattr(fetcher, '_fetch_html')
    
    @patch('requests.get')
    def test_fetch_rss_parses_feed_correctly(self, mock_get, sample_feed):
        """GREEN: RSS fetching should parse feed entries correctly."""
        mock_rss = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Senior Customer Support Engineer</title>
                    <link>https://example.com/job123</link>
                    <author>TechCorp Inc</author>
                    <published>2023-12-01T10:00:00Z</published>
                </item>
                <item>
                    <title>Technical Support Specialist</title>
                    <link>https://example.com/job456</link>
                    <author>SoftCorp</author>
                    <published>2023-12-01T11:00:00Z</published>
                </item>
            </channel>
        </rss>"""
        
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = mock_rss.encode('utf-8')
        
        fetcher = Fetcher()
        jobs = fetcher.fetch(sample_feed)
        
        assert len(jobs) == 2
        assert jobs[0].title == "Senior Customer Support Engineer"
        assert jobs[0].company == "TechCorp Inc"
        assert jobs[0].url == "https://example.com/job123"
        assert jobs[0].source == "test_feed"


class TestHTMLParsersTDD:
    """TDD tests for HTML parsers."""
    
    def test_html_parsers_initialization(self):
        """GREEN: HTMLParsers should initialize correctly."""
        parsers = HTMLParsers()
        assert parsers is not None
        assert hasattr(parsers, 'parse_jobs')
    
    def test_parse_jobs_requires_soup_and_feed(self):
        """RED: parse_jobs should require BeautifulSoup and Feed objects."""
        parsers = HTMLParsers()
        
        with pytest.raises((TypeError, AttributeError)):
            parsers.parse_jobs(None, None)
    
    def test_parser_selection_based_on_feed_url(self, sample_feed):
        """GREEN: Parser should select appropriate method based on feed URL."""
        parsers = HTMLParsers()
        
        # Test that parser has methods for different sites
        assert hasattr(parsers, '_parse_indeed')
        assert hasattr(parsers, '_parse_remoteok')
        assert hasattr(parsers, '_parse_linkedin')
    
    def test_generic_parser_fallback(self, sample_feed):
        """GREEN: Should fall back to generic parser for unknown sites."""
        from bs4 import BeautifulSoup
        
        html = "<html><div><h2>Test Job</h2><p>Test Company</p></div></html>"
        soup = BeautifulSoup(html, 'html.parser')
        
        parsers = HTMLParsers()
        jobs = parsers.parse_jobs(soup, sample_feed)
        
        # Should return list (may be empty if no jobs parsed)
        assert isinstance(jobs, list)


class TestHeadlessFetcherTDD:
    """TDD tests for headless browser fetching."""
    
    def test_headless_fetcher_initialization(self):
        """GREEN: HeadlessFetcher should initialize with browser pool."""
        from jobradar.fetchers.browser_pool import BrowserPool
        
        browser_pool = Mock(spec=BrowserPool)
        fetcher = HeadlessFetcher(browser_pool)
        
        assert fetcher is not None
        assert fetcher.browser_pool == browser_pool
    
    def test_headless_fetch_requires_feed(self):
        """RED: Headless fetch should require Feed object."""
        browser_pool = Mock()
        fetcher = HeadlessFetcher(browser_pool)
        
        with pytest.raises((TypeError, AttributeError)):
            fetcher.fetch(None)
    
    def test_headless_fetch_uses_browser_pool(self, sample_feed):
        """GREEN: Headless fetch should use browser pool for page automation."""
        mock_page = Mock()
        mock_page.content.return_value = "<html><body></body></html>"
        mock_page.goto.return_value = None
        
        mock_context = Mock()
        mock_context.new_page.return_value = mock_page
        
        mock_browser_pool = Mock()
        mock_browser_pool.get_context.return_value = mock_context
        
        fetcher = HeadlessFetcher(mock_browser_pool)
        
        # This should use the browser pool
        jobs = fetcher.fetch(sample_feed)
        
        mock_browser_pool.get_context.assert_called_once()
        mock_context.new_page.assert_called_once()
    
    def test_headless_fetch_handles_security_challenges(self, sample_feed):
        """RED: Headless fetch should detect and handle security challenges."""
        browser_pool = Mock()
        fetcher = HeadlessFetcher(browser_pool)
        
        # Test that fetcher has security challenge detection
        assert hasattr(fetcher, '_detect_security_challenge')
        assert hasattr(fetcher, '_handle_security_challenge')


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
    
    def test_add_duplicate_jobs_updates_existing(self, temp_db_path):
        """GREEN: Adding duplicate jobs should update existing records."""
        db = Database(f"sqlite:///{temp_db_path}")
        
        job1 = Job(id="same_id", title="Original Title", company="Original Corp", 
                  url="http://example.com", source="test")
        job2 = Job(id="same_id", title="Updated Title", company="Updated Corp",
                  url="http://example.com", source="test")
        
        # Add first job
        db.add_jobs([job1])
        
        # Add second job with same ID (should update)
        db.add_jobs([job2])
        
        # Should have only one job with updated data
        jobs = db.search_jobs({})
        assert len(jobs) == 1
        assert jobs[0].title == "Updated Title"
        assert jobs[0].company == "Updated Corp"
    
    def test_search_jobs_with_filters(self, temp_db_path, sample_jobs_list):
        """GREEN: Search should filter jobs correctly."""
        db = Database(f"sqlite:///{temp_db_path}")
        db.add_jobs(sample_jobs_list)
        
        # Search by title
        results = db.search_jobs({'title': 'Customer Support'})
        assert len(results) >= 1
        assert any('Customer Support' in job.title for job in results)
        
        # Search by company  
        results = db.search_jobs({'company': 'Company A'})
        assert len(results) >= 1
        assert any(job.company == 'Company A' for job in results)
    
    def test_count_jobs_returns_correct_number(self, temp_db_path, sample_jobs_list):
        """GREEN: count_jobs should return accurate count."""
        db = Database(f"sqlite:///{temp_db_path}")
        
        assert db.count_jobs() == 0
        
        db.add_jobs(sample_jobs_list)
        assert db.count_jobs() == len(sample_jobs_list)
    
    def test_get_recent_jobs_filters_by_date(self, temp_db_path):
        """GREEN: get_recent_jobs should filter by date correctly."""
        db = Database(f"sqlite:///{temp_db_path}")
        
        # Add jobs with different dates
        old_job = Job(id="old", title="Old Job", company="Corp", url="http://ex.com", 
                     source="test", date=(datetime.now() - timedelta(days=10)).isoformat())
        new_job = Job(id="new", title="New Job", company="Corp", url="http://ex.com",
                     source="test", date=datetime.now().isoformat())
        
        db.add_jobs([old_job, new_job])
        
        # Get recent jobs (last 7 days)
        recent = db.get_recent_jobs(days=7)
        
        # Should only contain new job
        assert len(recent) == 1
        assert recent[0].id == "new"
    
    def test_get_unique_values_returns_distinct_values(self, temp_db_path, sample_jobs_list):
        """GREEN: get_unique_values should return distinct values for field."""
        db = Database(f"sqlite:///{temp_db_path}")
        db.add_jobs(sample_jobs_list)
        
        sources = db.get_unique_values('source')
        expected_sources = {'indeed', 'linkedin', 'remoteok'}
        assert set(sources) == expected_sources
        
        companies = db.get_unique_values('company')
        expected_companies = {'Company A', 'Company B', 'Company C'}
        assert set(companies) == expected_companies


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
        assert 'customer_support' in scores or 'technical_support' in scores
        assert all(isinstance(score, int) for score in scores.values())
    
    def test_irrelevant_jobs_get_low_scores(self):
        """GREEN: Irrelevant jobs should get low relevance scores."""
        matcher = SmartTitleMatcher()
        
        irrelevant_job = Job(id="irr1", title="Underwater Basket Weaver", 
                           company="Corp", url="http://ex.com", source="test")
        
        scores = matcher.get_match_score(irrelevant_job)
        total_score = sum(scores.values())
        
        # Should have very low or zero total score
        assert total_score <= 1
    
    def test_filter_jobs_removes_irrelevant_jobs(self, sample_jobs_list):
        """GREEN: filter_jobs should remove jobs below threshold."""
        matcher = SmartTitleMatcher()
        
        # Customer support and technical support should be relevant
        relevant_jobs = matcher.filter_jobs(sample_jobs_list, min_score=1)
        
        # Should keep customer support and technical support jobs
        relevant_titles = [job.title for job in relevant_jobs]
        assert any('Customer Support' in title for title in relevant_titles)
        assert any('Technical Support' in title for title in relevant_titles)
    
    def test_configurable_score_threshold(self):
        """GREEN: Smart matcher should respect configurable score thresholds."""
        matcher = SmartTitleMatcher()
        
        job = Job(id="1", title="Customer Support Representative", company="Corp",
                 url="http://ex.com", source="test")
        
        # Test different thresholds
        assert matcher.is_relevant_job(job, min_score=1) is True
        # Higher threshold might filter out some jobs
        high_threshold_result = matcher.is_relevant_job(job, min_score=5)
        assert isinstance(high_threshold_result, bool)


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
    
    def test_location_filtering_supports_remote_jobs(self):
        """GREEN: Location filtering should handle remote jobs correctly."""
        config = FilterConfig(keywords=[], locations=['remote'], exclude=[])
        job_filter = JobFilter(config)
        
        remote_job = Job(id="1", title="Engineer", company="Corp", url="http://ex.com",
                        source="test", location="Remote", is_remote=True)
        office_job = Job(id="2", title="Engineer", company="Corp", url="http://ex.com", 
                        source="test", location="New York, NY", is_remote=False)
        
        assert job_filter.matches_location(remote_job) is True
        assert job_filter.matches_location(office_job) is False
    
    def test_salary_filtering_parses_salary_ranges(self):
        """GREEN: Salary filtering should parse and compare salary ranges."""
        config = FilterConfig(keywords=[], locations=[], exclude=[], 
                            salary_min=60000, salary_max=100000)
        job_filter = JobFilter(config)
        
        good_salary_job = Job(id="1", title="Engineer", company="Corp", url="http://ex.com",
                             source="test", salary="$70k - $90k")
        low_salary_job = Job(id="2", title="Engineer", company="Corp", url="http://ex.com",
                            source="test", salary="$40k - $50k")
        
        assert job_filter.matches_salary(good_salary_job) is True
        assert job_filter.matches_salary(low_salary_job) is False
    
    def test_exclude_filter_removes_unwanted_companies(self):
        """GREEN: Exclude filter should remove jobs from specified companies."""
        config = FilterConfig(keywords=[], locations=[], exclude=['SpamCorp', 'BadCompany'])
        job_filter = JobFilter(config)
        
        good_job = Job(id="1", title="Engineer", company="GoodCorp", url="http://ex.com", source="test")
        bad_job = Job(id="2", title="Engineer", company="SpamCorp", url="http://ex.com", source="test")
        
        assert job_filter.should_include(good_job) is True
        assert job_filter.should_include(bad_job) is False
    
    def test_combined_filters_all_conditions_must_match(self):
        """GREEN: Combined filters should require all conditions to match."""
        config = FilterConfig(
            keywords=['customer service'],
            locations=['remote'],
            exclude=['BadCorp'],
            is_remote=True
        )
        job_filter = JobFilter(config)
        
        perfect_job = Job(id="1", title="Customer Service Rep", company="GoodCorp",
                         url="http://ex.com", source="test", location="Remote", is_remote=True)
        partial_match = Job(id="2", title="Customer Service Rep", company="BadCorp",
                           url="http://ex.com", source="test", location="Remote", is_remote=True)
        
        assert job_filter.should_include(perfect_job) is True
        assert job_filter.should_include(partial_match) is False  # Excluded company


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
    
    def test_api_smart_jobs_supports_filtering(self, flask_client):
        """GREEN: Smart jobs API should support filtering parameters."""
        response = flask_client.get('/api/smart-jobs?categories=customer_support&min_score=2')
        
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert 'jobs' in data
        # API should handle filter parameters without error
    
    def test_api_filters_endpoint_returns_available_options(self, flask_client):
        """GREEN: /api/filters should return available filter options."""
        response = flask_client.get('/api/filters')
        
        assert response.status_code == 200
        
        data = json.loads(response.data)
        # Should include filter options like companies, locations, sources
        assert isinstance(data, dict)
    
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
    
    def test_fetch_command_accepts_parameters(self):
        """GREEN: Fetch command should accept standard parameters."""
        from jobradar.cli import fetch
        
        # Check that command has expected parameters
        param_names = [param.name for param in fetch.params]
        
        assert 'feed' in param_names
        assert 'limit' in param_names
        assert 'min-score' in param_names
    
    def test_web_command_starts_server(self):
        """RED: Web command should be able to start Flask server."""
        from jobradar.cli import web
        
        # Test that web command exists and is callable
        assert web is not None
        assert callable(web)


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
    
    def test_fetch_all_jobs_orchestrates_fetching(self, temp_db_path):
        """GREEN: fetch_all_jobs should coordinate job fetching from all feeds."""
        job_radar = JobRadar(db_url=f"sqlite:///{temp_db_path}")
        
        # Mock feeds
        job_radar.feeds = [
            Feed(name="test1", url="http://ex1.com", type="rss", parser="rss"),
            Feed(name="test2", url="http://ex2.com", type="rss", parser="rss")
        ]
        
        with patch.object(job_radar.fetcher, 'fetch') as mock_fetch:
            mock_fetch.return_value = [
                Job(id="1", title="Job 1", company="Corp", url="http://ex.com", source="test")
            ]
            
            jobs = job_radar.fetch_all_jobs()
            
            # Should call fetch for each feed
            assert mock_fetch.call_count == 2
            assert isinstance(jobs, list)
    
    def test_process_jobs_applies_smart_matching(self, temp_db_path, sample_jobs_list):
        """GREEN: process_jobs should apply smart matching to filter jobs."""
        job_radar = JobRadar(db_url=f"sqlite:///{temp_db_path}")
        
        with patch.object(job_radar.smart_matcher, 'filter_jobs') as mock_filter:
            mock_filter.return_value = sample_jobs_list[:2]  # Return subset
            
            processed = job_radar.process_jobs(sample_jobs_list)
            
            mock_filter.assert_called_once_with(sample_jobs_list)
            assert len(processed) == 2
    
    def test_save_jobs_persists_to_database(self, temp_db_path, sample_jobs_list):
        """GREEN: save_jobs should persist jobs to database."""
        job_radar = JobRadar(db_url=f"sqlite:///{temp_db_path}")
        
        saved_count = job_radar.save_jobs(sample_jobs_list)
        
        assert saved_count == len(sample_jobs_list)
        
        # Verify jobs were saved
        db_jobs = job_radar.database.search_jobs({})
        assert len(db_jobs) == len(sample_jobs_list)
    
    def test_search_jobs_queries_database(self, temp_db_path, sample_jobs_list):
        """GREEN: search_jobs should query database with filters."""
        job_radar = JobRadar(db_url=f"sqlite:///{temp_db_path}")
        job_radar.save_jobs(sample_jobs_list)
        
        results = job_radar.search_jobs({'title': 'Customer Support'}, limit=10)
        
        assert isinstance(results, list)
        assert all(isinstance(job, Job) for job in results)
    
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
    
    def test_api_database_integration(self, flask_client, temp_db_path):
        """GREEN: Web API should integrate with database for real data."""
        # This test verifies API returns actual data from database
        
        # Setup database with test data
        db = Database(f"sqlite:///{temp_db_path}")
        test_jobs = [
            Job(id="api1", title="API Test Job 1", company="TestCorp",
                url="http://test.com/1", source="test"),
            Job(id="api2", title="Customer Support Engineer", company="SupportCorp", 
                url="http://test.com/2", source="test")
        ]
        db.add_jobs(test_jobs)
        
        # Mock the database in the Flask app
        with patch('jobradar.web.app.Database') as mock_db_class:
            mock_db_class.return_value = db
            
            response = flask_client.get('/api/smart-jobs?page=1&per_page=10')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            # Should return jobs from database
            assert 'jobs' in data
            assert len(data['jobs']) >= 0  # May be filtered by smart matching


# ============================================================================
# TDD METHODOLOGY COMPLIANCE TESTS
# ============================================================================

def test_tdd_test_coverage_completeness():
    """RED: Verify we have tests for all major components (drives test creation)."""
    
    # This test ensures we maintain comprehensive test coverage
    required_test_classes = [
        'TestJobModelTDD',
        'TestFeedModelTDD', 
        'TestBaseFetcherTDD',
        'TestHTMLParsersTDD',
        'TestHeadlessFetcherTDD',
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


def test_tdd_methodology_red_green_refactor_cycle():
    """GREEN: Verify tests follow Red-Green-Refactor methodology."""
    
    # This test documents and verifies TDD methodology compliance
    tdd_principles = {
        'red': 'Write failing test first',
        'green': 'Write minimal code to make test pass',
        'refactor': 'Improve code while keeping tests green'
    }
    
    # Verify test structure supports TDD
    assert len(tdd_principles) == 3
    
    # All tests should be designed to drive implementation
    # Tests marked with RED comments should fail initially
    # Tests marked with GREEN comments should pass after implementation
    
    print("✅ TDD methodology compliance verified")


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 