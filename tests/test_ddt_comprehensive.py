"""
Comprehensive Data-Driven Tests (DDT) for JobRadar Application

This module contains comprehensive data-driven tests covering all major components
of the JobRadar application following DDT methodology principles.
"""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path

# Import all components to test
from jobradar.models import Job, Feed
from jobradar.fetchers import Fetcher
from jobradar.database import Database
from jobradar.filters import JobFilter
from jobradar.smart_matcher import SmartTitleMatcher, create_smart_matcher
from jobradar.rate_limiter import RateLimiter
from jobradar.config import load_feeds, get_config
from jobradar.core import JobRadar


# ============================================================================
# TEST DATA DEFINITIONS
# ============================================================================

# Job model test data
JOB_MODEL_TEST_DATA = [
    {
        "name": "valid_complete_job",
        "data": {
            "id": "job123",
            "title": "Senior Customer Support Engineer",
            "company": "TechCorp",
            "url": "https://example.com/job123",
            "source": "indeed",
            "date": "2024-01-15"
        },
        "expected_valid": True,
        "expected_score": 8
    },
    {
        "name": "valid_minimal_job",
        "data": {
            "id": "job456",
            "title": "Support Specialist",
            "company": "StartupCo",
            "url": "",
            "source": "linkedin",
            "date": ""
        },
        "expected_valid": True,
        "expected_score": 6
    },
    {
        "name": "invalid_missing_title",
        "data": {
            "id": "job789",
            "title": "",
            "company": "Company",
            "url": "https://example.com/job789",
            "source": "glassdoor",
            "date": "2024-01-15"
        },
        "expected_valid": False,
        "expected_score": 0
    },
    {
        "name": "invalid_missing_id",
        "data": {
            "id": "",
            "title": "Customer Success Manager",
            "company": "BigCorp",
            "url": "https://example.com/job",
            "source": "remote3",
            "date": "2024-01-15"
        },
        "expected_valid": False,
        "expected_score": 0
    }
]

# Feed configuration test data
FEED_CONFIG_TEST_DATA = [
    {
        "name": "indeed_headless_feed",
        "config": {
            "name": "indeed",
            "url": "https://indeed.com/jobs?q=customer+support",
            "type": "html",
            "fetch_method": "headless",
            "parser": "indeed",
            "rate_limit": {"requests_per_minute": 3, "retry_after": 20},
            "headers": {"User-Agent": "Mozilla/5.0"},
            "cookies": {}
        },
        "expected_valid": True,
        "expected_method": "headless"
    },
    {
        "name": "remoteok_html_feed",
        "config": {
            "name": "remoteok",
            "url": "https://remoteok.io/remote-jobs",
            "type": "html",
            "fetch_method": "html",
            "parser": "remoteok",
            "rate_limit": {"requests_per_minute": 10, "retry_after": 5},
            "headers": {},
            "cookies": {}
        },
        "expected_valid": True,
        "expected_method": "html"
    },
    {
        "name": "json_api_feed",
        "config": {
            "name": "api_jobs",
            "url": "https://api.example.com/jobs.json",
            "type": "json",
            "fetch_method": "json",
            "parser": "generic",
            "rate_limit": {"requests_per_minute": 60, "retry_after": 1},
            "headers": {"Authorization": "Bearer token"},
            "cookies": {}
        },
        "expected_valid": True,
        "expected_method": "json"
    },
    {
        "name": "invalid_missing_url",
        "config": {
            "name": "broken_feed",
            "url": "",
            "type": "html",
            "fetch_method": "html",
            "parser": "generic",
            "rate_limit": {"requests_per_minute": 10, "retry_after": 5},
            "headers": {},
            "cookies": {}
        },
        "expected_valid": False,
        "expected_method": None
    }
]

# Smart matcher test data
SMART_MATCHER_TEST_DATA = [
    {
        "name": "high_relevance_customer_support",
        "job": {
            "title": "Senior Customer Support Engineer",
            "company": "TechCorp",
            "description": "Handle customer inquiries, troubleshoot technical issues, provide excellent customer service"
        },
        "expected_score": 9,
        "expected_relevant": True,
        "expected_categories": ["customer_support", "technical_support"]
    },
    {
        "name": "medium_relevance_operations",
        "job": {
            "title": "Operations Specialist",
            "company": "LogisticsCorp",
            "description": "Manage daily operations, coordinate with teams, ensure process efficiency"
        },
        "expected_score": 6,
        "expected_relevant": True,
        "expected_categories": ["operations", "specialist_roles"]
    },
    {
        "name": "low_relevance_unrelated",
        "job": {
            "title": "Senior Software Engineer",
            "company": "DevCorp",
            "description": "Develop backend systems, write clean code, implement new features"
        },
        "expected_score": 2,
        "expected_relevant": False,
        "expected_categories": ["software_development"]
    },
    {
        "name": "zero_relevance_irrelevant",
        "job": {
            "title": "Marketing Manager",
            "company": "AdCorp",
            "description": "Create marketing campaigns, manage social media, analyze market trends"
        },
        "expected_score": 0,
        "expected_relevant": False,
        "expected_categories": []
    }
]

# Filter test data
FILTER_TEST_DATA = [
    {
        "name": "location_filter_remote",
        "filter_config": {
            "type": "location",
            "allowed_locations": ["remote", "worldwide", "global"],
            "blocked_locations": ["on-site", "office"]
        },
        "jobs": [
            {"title": "Remote Support", "location": "Remote", "expected": True},
            {"title": "Office Support", "location": "New York Office", "expected": False},
            {"title": "Global Support", "location": "Worldwide", "expected": True}
        ]
    },
    {
        "name": "company_filter_blacklist",
        "filter_config": {
            "type": "company",
            "blocked_companies": ["BadCorp", "AvoidInc", "NoGoodLLC"]
        },
        "jobs": [
            {"title": "Support Role", "company": "GoodCorp", "expected": True},
            {"title": "Support Role", "company": "BadCorp", "expected": False},
            {"title": "Support Role", "company": "AvoidInc", "expected": False}
        ]
    },
    {
        "name": "salary_filter_minimum",
        "filter_config": {
            "type": "salary",
            "min_salary": 50000,
            "max_salary": 150000
        },
        "jobs": [
            {"title": "Support Role", "salary": 60000, "expected": True},
            {"title": "Support Role", "salary": 30000, "expected": False},
            {"title": "Support Role", "salary": 200000, "expected": False}
        ]
    }
]

# Rate limiter test data
RATE_LIMITER_TEST_DATA = [
    {
        "name": "aggressive_rate_limit",
        "config": {"requests_per_minute": 1, "retry_after": 60},
        "requests": [
            {"expected_wait": None},  # First request
            {"expected_wait": 60},    # Second request should wait
            {"expected_wait": 60}     # Third request should wait
        ]
    },
    {
        "name": "moderate_rate_limit",
        "config": {"requests_per_minute": 10, "retry_after": 6},
        "requests": [
            {"expected_wait": None},  # First request
            {"expected_wait": 6},     # Second request should wait
            {"expected_wait": 6}      # Third request should wait
        ]
    },
    {
        "name": "lenient_rate_limit",
        "config": {"requests_per_minute": 60, "retry_after": 1},
        "requests": [
            {"expected_wait": None},  # First request
            {"expected_wait": 1},     # Second request should wait
            {"expected_wait": 1}      # Third request should wait
        ]
    }
]

# Database operation test data
DATABASE_TEST_DATA = [
    {
        "name": "insert_valid_jobs",
        "jobs": [
            {
                "id": "db_test_1",
                "title": "Customer Support Rep",
                "company": "TestCorp",
                "url": "https://test.com/1",
                "source": "test",
                "date": "2024-01-15"
            },
            {
                "id": "db_test_2",
                "title": "Technical Support",
                "company": "TechTest",
                "url": "https://test.com/2",
                "source": "test",
                "date": "2024-01-16"
            }
        ],
        "expected_inserted": 2,
        "expected_duplicates": 0
    },
    {
        "name": "handle_duplicate_jobs",
        "jobs": [
            {
                "id": "dup_test_1",
                "title": "Support Engineer",
                "company": "DupCorp",
                "url": "https://dup.com/1",
                "source": "test",
                "date": "2024-01-15"
            },
            {
                "id": "dup_test_1",  # Same ID
                "title": "Support Engineer Updated",
                "company": "DupCorp",
                "url": "https://dup.com/1",
                "source": "test",
                "date": "2024-01-15"
            }
        ],
        "expected_inserted": 1,
        "expected_duplicates": 1
    }
]

# Parser test data for different job sites
PARSER_TEST_DATA = [
    {
        "name": "indeed_parser",
        "html_content": """
        <div class="job_seen_beacon" data-jk="job123">
            <h2><span title="Customer Support Engineer">Customer Support Engineer</span></h2>
            <span class="companyName">TechCorp</span>
        </div>
        """,
        "parser": "indeed",
        "expected_jobs": 1,
        "expected_title": "Customer Support Engineer",
        "expected_company": "TechCorp"
    },
    {
        "name": "remoteok_parser",
        "html_content": """
        <tr class="job" data-id="remote123">
            <h2 itemprop="title">Remote Support Specialist</h2>
            <h3 itemprop="name">RemoteCorp</h3>
        </tr>
        """,
        "parser": "remoteok",
        "expected_jobs": 1,
        "expected_title": "Remote Support Specialist",
        "expected_company": "RemoteCorp"
    },
    {
        "name": "linkedin_parser",
        "html_content": """
        <div class="job-card-container">
            <h3 class="job-card-list__title">Customer Success Manager</h3>
            <h4 class="job-card-container__company-name">LinkedCorp</h4>
        </div>
        """,
        "parser": "linkedin",
        "expected_jobs": 1,
        "expected_title": "Customer Success Manager",
        "expected_company": "LinkedCorp"
    },
    {
        "name": "linkedin_parser_with_url",
        "html_content": """
        <div class="job-card-container">
            <h3 class="job-card-list__title">Senior Software Engineer</h3>
            <h4 class="job-card-container__company-name">TechCorp</h4>
            <a class="job-card-list__title-link" href="/jobs/view/123456789">View Job</a>
        </div>
        """,
        "parser": "linkedin",
        "expected_jobs": 1,
        "expected_title": "Senior Software Engineer",
        "expected_company": "TechCorp"
    },
    {
        "name": "linkedin_parser_duplicate_ids",
        "html_content": """
        <div class="job-card-container">
            <h3 class="job-card-list__title">Customer Support Agent</h3>
            <h4 class="job-card-container__company-name">SupportCorp</h4>
        </div>
        <div class="job-card-container">
            <h3 class="job-card-list__title">Customer Support Agent</h3>
            <h4 class="job-card-container__company-name">SupportCorp</h4>
        </div>
        <div class="job-card-container">
            <h3 class="job-card-list__title">Customer Support Agent</h3>
            <h4 class="job-card-container__company-name">SupportCorp</h4>
        </div>
        """,
        "parser": "linkedin",
        "expected_jobs": 3,
        "expected_title": "Customer Support Agent",
        "expected_company": "SupportCorp"
    }
]

# Error handling test data
ERROR_HANDLING_TEST_DATA = [
    {
        "name": "network_timeout",
        "error_type": "timeout",
        "error_config": {"timeout": 0.1},
        "expected_retry": True,
        "expected_backoff": True
    },
    {
        "name": "http_429_rate_limit",
        "error_type": "http_error",
        "error_config": {"status_code": 429},
        "expected_retry": True,
        "expected_backoff": True
    },
    {
        "name": "http_404_not_found",
        "error_type": "http_error",
        "error_config": {"status_code": 404},
        "expected_retry": False,
        "expected_backoff": False
    },
    {
        "name": "parsing_error",
        "error_type": "parsing_error",
        "error_config": {"invalid_html": True},
        "expected_retry": False,
        "expected_backoff": False
    }
]


# ============================================================================
# DDT TEST IMPLEMENTATIONS
# ============================================================================

class TestJobModelDDT:
    """Data-driven tests for Job model validation and scoring."""
    
    @pytest.mark.parametrize("test_case", JOB_MODEL_TEST_DATA)
    def test_job_creation_and_validation(self, test_case):
        """Test job creation with various data combinations."""
        job_data = test_case["data"]
        
        if test_case["expected_valid"]:
            # Should create job successfully
            job = Job(**job_data)
            assert job.id == job_data["id"]
            assert job.title == job_data["title"]
            assert job.company == job_data["company"]
            assert job.url == job_data["url"]
            assert job.source == job_data["source"]
            assert job.date == job_data["date"]
        else:
            # Should handle invalid data gracefully
            if not job_data["id"] or not job_data["title"]:
                with pytest.raises((ValueError, TypeError)):
                    job = Job(**job_data)
    
    @pytest.mark.parametrize("test_case", JOB_MODEL_TEST_DATA)
    def test_job_relevance_scoring(self, test_case):
        """Test job relevance scoring with smart matcher."""
        if not test_case["expected_valid"]:
            pytest.skip("Skipping invalid job data for scoring test")
            
        job_data = test_case["data"]
        job = Job(**job_data)
        
        # Mock smart matcher
        matcher = SmartTitleMatcher()
        scores = matcher.get_match_score(job)
        score = sum(scores.values())  # Total score across all categories
        
        # Score should be within expected range
        assert 0 <= score <= 10
        assert abs(score - test_case["expected_score"]) <= 2  # Allow some variance


class TestFeedConfigurationDDT:
    """Data-driven tests for feed configuration and validation."""
    
    @pytest.mark.parametrize("test_case", FEED_CONFIG_TEST_DATA)
    def test_feed_creation_and_validation(self, test_case):
        """Test feed creation with various configurations."""
        config = test_case["config"]
        
        if test_case["expected_valid"]:
            # Should create feed successfully
            feed = Feed(**config)
            assert feed.name == config["name"]
            assert feed.url == config["url"]
            assert feed.fetch_method == config["fetch_method"]
            assert feed.parser == config["parser"]
            assert feed.rate_limit == config["rate_limit"]
        else:
            # Should handle invalid configuration
            if not config.get("url"):
                with pytest.raises((ValueError, TypeError)):
                    feed = Feed(**config)
    
    @pytest.mark.parametrize("test_case", FEED_CONFIG_TEST_DATA)
    def test_feed_method_selection(self, test_case):
        """Test that correct fetch method is selected."""
        if not test_case["expected_valid"]:
            pytest.skip("Skipping invalid feed for method test")
            
        config = test_case["config"]
        feed = Feed(**config)
        
        assert feed.fetch_method == test_case["expected_method"]


class TestSmartMatcherDDT:
    """Data-driven tests for smart job matching and scoring."""
    
    @pytest.mark.parametrize("test_case", SMART_MATCHER_TEST_DATA)
    def test_relevance_scoring(self, test_case):
        """Test relevance scoring with various job types."""
        matcher = SmartTitleMatcher()
        job_data = test_case["job"]
        
        job = Job(
            id="test_123",
            title=job_data["title"],
            company=job_data["company"],
            url="https://example.com/job",
            source="test",
            description=job_data.get("description", "")
        )
        
        scores = matcher.get_match_score(job)
        total_score = sum(scores.values())
        is_relevant = matcher.is_relevant_job(job, min_score=1)
        
        # Check score is in expected range
        assert 0 <= total_score <= 10
        assert abs(total_score - test_case["expected_score"]) <= 2
        
        # Check relevance determination
        assert is_relevant == test_case["expected_relevant"]
    
    @pytest.mark.parametrize("test_case", SMART_MATCHER_TEST_DATA)
    def test_category_detection(self, test_case):
        """Test job category detection."""
        matcher = SmartTitleMatcher()
        job_data = test_case["job"]
        
        job = Job(
            id="test_123",
            title=job_data["title"],
            company=job_data["company"],
            url="https://example.com/job",
            source="test",
            description=job_data.get("description", "")
        )
        
        scores = matcher.get_match_score(job)
        matched_categories = [cat for cat, score in scores.items() if score > 0]
        
        # Check that expected categories are detected
        for expected_cat in test_case["expected_categories"]:
            assert expected_cat in matched_categories or len(matched_categories) == 0


class TestJobFilterDDT:
    """Data-driven tests for job filtering functionality."""
    
    @pytest.mark.parametrize("test_case", FILTER_TEST_DATA)
    def test_job_filtering(self, test_case):
        """Test job filtering with various filter configurations."""
        job_filter = JobFilter(test_case["filter_config"])
        
        for job_test in test_case["jobs"]:
            # Create a mock job with the test data
            job = Job(
                id="test_id",
                title=job_test["title"],
                company=job_test.get("company", "TestCorp"),
                url="https://test.com",
                source="test",
                date="2024-01-15"
            )
            
            # Add additional attributes for specific filter types
            if "location" in job_test:
                job.location = job_test["location"]
            if "salary" in job_test:
                job.salary = job_test["salary"]
            
            # Test the filter
            result = job_filter.should_include(job)
            assert result == job_test["expected"], f"Filter failed for {job_test}"


class TestRateLimiterDDT:
    """Data-driven tests for rate limiting functionality."""
    
    @pytest.mark.parametrize("test_case", RATE_LIMITER_TEST_DATA)
    def test_rate_limiting_patterns(self, test_case):
        """Test rate limiting with various configurations."""
        limiter = RateLimiter(test_mode=True)
        feed_name = f"test_feed_{test_case['name']}"
        config = test_case["config"]
        
        for i, request in enumerate(test_case["requests"]):
            wait_time = limiter.wait_if_needed(feed_name, config)
            
            if request["expected_wait"] is None:
                assert wait_time is None, f"Request {i+1} should not have waited"
            else:
                assert wait_time is not None, f"Request {i+1} should have waited"
                # Allow some tolerance for timing
                expected = request["expected_wait"]
                assert abs(wait_time - expected) <= 1, f"Wait time {wait_time} not close to expected {expected}"


class TestDatabaseOperationsDDT:
    """Data-driven tests for database operations."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        db = Database(db_path, test_mode=True)
        yield db
        
        # Cleanup
        db.close()
        os.unlink(db_path)
    
    @pytest.mark.parametrize("test_case", DATABASE_TEST_DATA)
    def test_job_insertion_and_deduplication(self, temp_db, test_case):
        """Test job insertion with various scenarios."""
        jobs = [Job(**job_data) for job_data in test_case["jobs"]]
        
        # Insert jobs
        inserted_count = 0
        duplicate_count = 0
        
        for job in jobs:
            try:
                temp_db.save_job(job)
                inserted_count += 1
            except Exception as e:
                if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                    duplicate_count += 1
                else:
                    raise
        
        # Verify results
        assert inserted_count >= test_case["expected_inserted"]
        
        # Check total jobs in database
        all_jobs = temp_db.get_all_jobs()
        assert len(all_jobs) == test_case["expected_inserted"]


class TestParserDDT:
    """Data-driven tests for HTML parsing functionality."""
    
    @pytest.mark.parametrize("test_case", PARSER_TEST_DATA)
    def test_html_parsing(self, test_case):
        """Test HTML parsing with various job site formats."""
        from bs4 import BeautifulSoup
        from jobradar.fetchers import Fetcher
        
        fetcher = Fetcher()
        soup = BeautifulSoup(test_case["html_content"], "html.parser")
        
        # Create a mock feed
        feed = Mock()
        feed.name = "test_feed"
        feed.parser = test_case["parser"]
        
        # Get the appropriate parser method
        parser_method = getattr(fetcher, f"_parse_{test_case['parser']}", None)
        if parser_method is None:
            pytest.skip(f"Parser {test_case['parser']} not implemented")
        
        # Parse the HTML
        jobs = parser_method(soup, feed)
        
        # Verify results
        assert len(jobs) == test_case["expected_jobs"]
        
        if jobs:
            job = jobs[0]
            assert job.title == test_case["expected_title"]
            assert job.company == test_case["expected_company"]

    def test_linkedin_duplicate_id_handling(self):
        """Test that LinkedIn parser handles duplicate IDs correctly."""
        from bs4 import BeautifulSoup
        from jobradar.fetchers import Fetcher
        
        fetcher = Fetcher()
        
        # Test case with duplicate jobs that would generate same IDs
        html_content = """
        <div class="job-card-container">
            <h3 class="job-card-list__title">Customer Support Agent</h3>
            <h4 class="job-card-container__company-name">SupportCorp</h4>
        </div>
        <div class="job-card-container">
            <h3 class="job-card-list__title">Customer Support Agent</h3>
            <h4 class="job-card-container__company-name">SupportCorp</h4>
        </div>
        <div class="job-card-container">
            <h3 class="job-card-list__title">Customer Support Agent</h3>
            <h4 class="job-card-container__company-name">SupportCorp</h4>
        </div>
        """
        
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Create a mock feed
        feed = Mock()
        feed.name = "linkedin_test"
        feed.parser = "linkedin"
        
        # Parse the HTML
        jobs = fetcher._parse_linkedin(soup, feed)
        
        # Verify results
        assert len(jobs) == 3, "Should parse all 3 duplicate jobs"
        
        # All jobs should have unique IDs
        job_ids = [job.id for job in jobs]
        unique_ids = set(job_ids)
        assert len(job_ids) == len(unique_ids), f"All job IDs should be unique. Got: {job_ids}"
        
        # All jobs should have the same title and company
        for job in jobs:
            assert job.title == "Customer Support Agent"
            assert job.company == "SupportCorp"
            assert job.source == "linkedin_test"
        
        # IDs should be hash-based (16 characters) since no URLs are provided
        # Each job gets a unique hash because position index is included in hash generation
        for job in jobs:
            assert len(job.id) == 16, f"Job ID should be 16-character hash: {job.id}"
            # Should be alphanumeric (hash)
            import re
            assert re.match(r'^[a-f0-9]{16}$', job.id), f"Job ID should be hex hash: {job.id}"

    def test_linkedin_url_pattern_extraction(self):
        """Test that LinkedIn parser extracts IDs from various URL patterns."""
        from bs4 import BeautifulSoup
        from jobradar.fetchers import Fetcher
        
        fetcher = Fetcher()
        
        # Test various LinkedIn URL patterns
        url_test_cases = [
            ("/jobs/view/123456789", "123456789"),
            ("/jobs/search/?jobId=987654321", "987654321"),
            ("/jobs/search/?currentJobId=555666777", "555666777"),
            ("/jobs/collections/recommended/?job-111222333", "111222333"),
            ("/jobs/search/444555666/?refId=abc123def", "abc123def"),  # refId pattern matches first
            ("/jobs/search/?refId=xyz789&trackingId=track123", "xyz789"),
        ]
        
        for url, expected_id in url_test_cases:
            html_content = f"""
            <div class="job-card-container">
                <h3 class="job-card-list__title">Test Job</h3>
                <h4 class="job-card-container__company-name">Test Company</h4>
                <a class="job-card-list__title-link" href="{url}">View Job</a>
            </div>
            """
            
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Create a mock feed
            feed = Mock()
            feed.name = "linkedin_test"
            feed.parser = "linkedin"
            
            # Parse the HTML
            jobs = fetcher._parse_linkedin(soup, feed)
            
            # Verify results
            assert len(jobs) == 1, f"Should parse one job for URL: {url}"
            assert jobs[0].id == expected_id, f"Expected ID {expected_id} for URL {url}, got {jobs[0].id}"
            assert jobs[0].url == f"https://www.linkedin.com{url}", f"URL should be properly formatted"


class TestErrorHandlingDDT:
    """Data-driven tests for error handling and recovery."""
    
    @pytest.mark.parametrize("test_case", ERROR_HANDLING_TEST_DATA)
    def test_error_handling_strategies(self, test_case):
        """Test error handling with various error types."""
        from jobradar.error_handling import ErrorHandler
        
        handler = ErrorHandler()
        error_config = test_case["error_config"]
        
        # Simulate different types of errors
        if test_case["error_type"] == "timeout":
            from requests.exceptions import Timeout
            error = Timeout("Request timed out")
        elif test_case["error_type"] == "http_error":
            from requests.exceptions import HTTPError
            response = Mock()
            response.status_code = error_config["status_code"]
            error = HTTPError(response=response)
        elif test_case["error_type"] == "parsing_error":
            error = ValueError("Invalid HTML structure")
        else:
            error = Exception("Generic error")
        
        # Test error handling
        should_retry = handler.should_retry(error)
        backoff_time = handler.get_backoff_time(error)
        
        assert should_retry == test_case["expected_retry"]
        assert (backoff_time > 0) == test_case["expected_backoff"]


class TestIntegrationDDT:
    """Data-driven integration tests for complete workflows."""
    
    @pytest.fixture
    def temp_config(self):
        """Create temporary configuration for testing."""
        config_data = {
            "database": {"path": ":memory:"},
            "smart_filtering": {
                "enabled": True,
                "min_score": 5,
                "categories": ["customer_support", "technical_support"]
            },
            "rate_limiting": {
                "default": {"requests_per_minute": 10, "retry_after": 1}
            },
            "feeds": [
                {
                    "name": "test_feed",
                    "url": "https://example.com/jobs",
                    "type": "html",
                    "parser": "generic",
                    "fetch_method": "html"
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            import yaml
            yaml.dump(config_data, f)
            config_path = f.name
        
        yield config_path
        
        # Cleanup
        os.unlink(config_path)
    
    INTEGRATION_TEST_DATA = [
        {
            "name": "end_to_end_job_processing",
            "mock_jobs": [
                {
                    "id": "integration_1",
                    "title": "Customer Support Engineer",
                    "company": "TechCorp",
                    "url": "https://test.com/1",
                    "source": "test",
                    "date": "2024-01-15"
                },
                {
                    "id": "integration_2",
                    "title": "Marketing Manager",
                    "company": "AdCorp",
                    "url": "https://test.com/2",
                    "source": "test",
                    "date": "2024-01-15"
                }
            ],
            "expected_relevant": 1,
            "expected_filtered": 1
        }
    ]
    
    @pytest.mark.parametrize("test_case", INTEGRATION_TEST_DATA)
    def test_end_to_end_workflow(self, temp_config, test_case):
        """Test complete job processing workflow."""
        # Load config from temporary file
        config = get_config(temp_config)
        
        # Create JobRadar instance with test config
        job_radar = JobRadar(db_url="sqlite:///:memory:")
        
        # Mock the fetcher to return test jobs
        mock_jobs = [Job(**job_data) for job_data in test_case["mock_jobs"]]
        
        # Process jobs using smart matcher
        smart_matcher = SmartTitleMatcher()
        relevant_jobs = smart_matcher.filter_jobs(mock_jobs, min_score=1)
        
        # Verify results
        assert len(mock_jobs) == 2
        assert len(relevant_jobs) == test_case["expected_relevant"]


# ============================================================================
# TEST DATA VALIDATION
# ============================================================================

def test_all_test_data_valid():
    """Validate that all test data is properly structured."""
    test_data_sets = [
        JOB_MODEL_TEST_DATA,
        FEED_CONFIG_TEST_DATA,
        SMART_MATCHER_TEST_DATA,
        FILTER_TEST_DATA,
        RATE_LIMITER_TEST_DATA,
        DATABASE_TEST_DATA,
        PARSER_TEST_DATA,
        ERROR_HANDLING_TEST_DATA
    ]
    
    for data_set in test_data_sets:
        assert isinstance(data_set, list), "Test data must be a list"
        assert len(data_set) > 0, "Test data must not be empty"
        
        for test_case in data_set:
            assert "name" in test_case, "Each test case must have a name"
            assert isinstance(test_case["name"], str), "Test case name must be a string"
            assert len(test_case["name"]) > 0, "Test case name must not be empty"


# ============================================================================
# PERFORMANCE AND LOAD TESTING DATA
# ============================================================================

PERFORMANCE_TEST_DATA = [
    {
        "name": "small_load",
        "job_count": 10,
        "expected_max_time": 1.0
    },
    {
        "name": "medium_load",
        "job_count": 100,
        "expected_max_time": 5.0
    },
    {
        "name": "large_load",
        "job_count": 1000,
        "expected_max_time": 30.0
    }
]

class TestPerformanceDDT:
    """Data-driven performance tests."""
    
    @pytest.mark.parametrize("test_case", PERFORMANCE_TEST_DATA)
    def test_job_processing_performance(self, test_case):
        """Test job processing performance with various loads."""
        import time
        
        # Create test jobs
        jobs = []
        for i in range(test_case["job_count"]):
            job = Job(
                id=f"perf_test_{i}",
                title=f"Test Job {i}",
                company=f"Company {i}",
                url=f"https://test.com/{i}",
                source="performance_test",
                date="2024-01-15"
            )
            jobs.append(job)
        
        # Measure processing time
        start_time = time.time()
        
        # Process jobs (mock the actual processing)
        matcher = SmartTitleMatcher()
        relevant_jobs = []
        for job in jobs:
            scores = matcher.get_match_score(job)
            total_score = sum(scores.values())
            if total_score >= 5:
                relevant_jobs.append(job)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Verify performance
        assert processing_time <= test_case["expected_max_time"], \
            f"Processing {test_case['job_count']} jobs took {processing_time:.2f}s, expected <= {test_case['expected_max_time']}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 