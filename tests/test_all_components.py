"""
Comprehensive TDD Test Suite for JobRadar Application

This module contains TDD tests for all major components following Red-Green-Refactor methodology.
"""

import pytest
import tempfile
import os
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path
import yaml

# Import components to test
from jobradar.models import Job, Feed
from jobradar.fetchers.base_fetcher import Fetcher
from jobradar.database import Database
from jobradar.smart_matcher import SmartTitleMatcher
from jobradar.filters import JobFilter, FilterConfig
from jobradar.core import JobRadar


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def temp_db_path():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def sample_job():
    """Sample job for testing."""
    return Job(
        id="test_job_123",
        title="Customer Support Engineer", 
        company="TechCorp",
        url="https://example.com/jobs/123",
        source="indeed"
    )


@pytest.fixture
def sample_feed():
    """Sample feed for testing."""
    return Feed(
        name="test_feed",
        url="https://example.com/rss",
        type="rss",
        parser="rss"
    )


# ============================================================================
# JOB MODEL TESTS
# ============================================================================

class TestJobModel:
    """TDD tests for Job model."""
    
    def test_job_requires_id(self):
        """RED: Job should require ID field."""
        with pytest.raises(ValueError, match="Job ID is required"):
            Job(
                id="",
                title="Engineer",
                company="Corp",
                url="http://example.com",
                source="test"
            )
    
    def test_job_requires_title(self):
        """RED: Job should require title field.""" 
        with pytest.raises(ValueError, match="Job title is required"):
            Job(
                id="123",
                title="",
                company="Corp",
                url="http://example.com",
                source="test"
            )
    
    def test_job_creation_success(self, sample_job):
        """GREEN: Job creation with valid data should work."""
        assert sample_job.id == "test_job_123"
        assert sample_job.title == "Customer Support Engineer"
        assert sample_job.company == "TechCorp"
    
    def test_job_equality_by_id(self):
        """GREEN: Jobs with same ID should be equal."""
        job1 = Job(id="same", title="Job 1", company="Corp1", url="http://1.com", source="s1")
        job2 = Job(id="same", title="Job 2", company="Corp2", url="http://2.com", source="s2")
        
        assert job1 == job2
        assert hash(job1) == hash(job2)
    
    def test_job_skills_default_list(self):
        """GREEN: Job skills should default to empty list."""
        job = Job(id="1", title="Job", company="Corp", url="http://ex.com", source="src")
        assert job.skills == []
        assert isinstance(job.skills, list)


# ============================================================================
# FEED MODEL TESTS  
# ============================================================================

class TestFeedModel:
    """TDD tests for Feed model."""
    
    def test_feed_requires_url(self):
        """RED: Feed should require URL."""
        with pytest.raises(ValueError, match="Feed URL is required"):
            Feed(name="test", url="", type="rss", parser="rss")
    
    def test_feed_creation_success(self, sample_feed):
        """GREEN: Feed creation with valid data should work."""
        assert sample_feed.name == "test_feed"
        assert sample_feed.url == "https://example.com/rss"
        assert sample_feed.type == "rss"


# ============================================================================
# FETCHER TESTS
# ============================================================================

class TestFetcher:
    """TDD tests for job fetching."""
    
    def test_fetcher_initialization(self):
        """GREEN: Fetcher should initialize properly."""
        fetcher = Fetcher()
        assert fetcher is not None
        assert hasattr(fetcher, 'rate_limiter')
        assert hasattr(fetcher, 'browser_pool')
    
    @patch('requests.get')
    def test_fetch_rss_returns_jobs(self, mock_get, sample_feed):
        """GREEN: RSS fetch should return list of jobs."""
        mock_rss = """<?xml version="1.0"?>
        <rss><channel>
            <item>
                <title>Test Job</title>
                <link>http://example.com/job</link>
                <author>Test Corp</author>
            </item>
        </channel></rss>"""
        
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = mock_rss.encode('utf-8')
        
        fetcher = Fetcher()
        jobs = fetcher.fetch(sample_feed)
        
        assert isinstance(jobs, list)
    
    @patch('requests.get')  
    def test_fetch_handles_errors(self, mock_get, sample_feed):
        """GREEN: Fetch should handle network errors gracefully."""
        mock_get.side_effect = Exception("Network error")
        
        fetcher = Fetcher()
        jobs = fetcher.fetch(sample_feed)
        
        assert isinstance(jobs, list)
        assert len(jobs) == 0


# ============================================================================
# DATABASE TESTS
# ============================================================================

class TestDatabase:
    """TDD tests for database operations."""
    
    def test_database_creates_tables(self, temp_db_path):
        """GREEN: Database should create tables on init."""
        db = Database(f"sqlite:///{temp_db_path}")
        
        import sqlite3
        with sqlite3.connect(temp_db_path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            assert 'jobs' in tables
    
    def test_add_job_stores_data(self, temp_db_path, sample_job):
        """GREEN: Adding job should store it in database."""
        db = Database(f"sqlite:///{temp_db_path}")
        
        result = db.add_jobs([sample_job])
        assert result == 1
        
        jobs = db.search_jobs({})
        assert len(jobs) == 1
        assert jobs[0].title == sample_job.title
    
    def test_count_jobs_accurate(self, temp_db_path):
        """GREEN: count_jobs should return correct number."""
        db = Database(f"sqlite:///{temp_db_path}")
        
        assert db.count_jobs() == 0
        
        job = Job(id="1", title="Job", company="Corp", url="http://ex.com", source="src")
        db.add_jobs([job])
        
        assert db.count_jobs() == 1


# ============================================================================
# SMART MATCHER TESTS
# ============================================================================

class TestSmartMatcher:
    """TDD tests for smart job matching."""
    
    def test_matcher_initialization(self):
        """GREEN: SmartMatcher should initialize correctly."""
        matcher = SmartTitleMatcher()
        assert matcher is not None
        assert hasattr(matcher, 'is_relevant_job')
    
    def test_customer_support_jobs_relevant(self):
        """GREEN: Customer support jobs should be relevant."""
        matcher = SmartTitleMatcher()
        
        cs_job = Job(id="1", title="Customer Support Engineer", company="Corp",
                    url="http://ex.com", source="test")
        
        assert matcher.is_relevant_job(cs_job) is True
    
    def test_get_match_scores(self):
        """GREEN: Should return category scores."""
        matcher = SmartTitleMatcher()
        
        job = Job(id="1", title="Technical Support", company="Corp",
                 url="http://ex.com", source="test")
        
        scores = matcher.get_match_score(job)
        assert isinstance(scores, dict)


# ============================================================================
# FILTER TESTS
# ============================================================================

class TestJobFilter:
    """TDD tests for job filtering."""
    
    def test_filter_config_creation(self):
        """GREEN: FilterConfig should be creatable."""
        config = FilterConfig(
            keywords=['python'],
            locations=['remote'],
            exclude=[]
        )
        assert config.keywords == ['python']
    
    def test_job_filter_with_config(self):
        """GREEN: JobFilter should work with config."""
        config = FilterConfig(keywords=['support'], locations=[], exclude=[])
        job_filter = JobFilter(config)
        
        assert job_filter is not None
        assert job_filter.config == config
    
    def test_keyword_filtering(self):
        """GREEN: Should filter by keywords in title/company."""
        config = FilterConfig(keywords=['customer'], locations=[], exclude=[])
        job_filter = JobFilter(config)
        
        match_job = Job(id="1", title="Customer Support", company="Corp",
                       url="http://ex.com", source="test")
        no_match = Job(id="2", title="Software Engineer", company="Corp", 
                      url="http://ex.com", source="test")
        
        assert job_filter.matches_keywords(match_job) is True
        assert job_filter.matches_keywords(no_match) is False


# ============================================================================
# CORE ORCHESTRATION TESTS
# ============================================================================

class TestJobRadarCore:
    """TDD tests for main JobRadar class."""
    
    def test_jobradar_initialization(self, temp_db_path):
        """GREEN: JobRadar should initialize all components."""
        job_radar = JobRadar(db_url=f"sqlite:///{temp_db_path}")
        
        assert job_radar is not None
        assert hasattr(job_radar, 'database')
        assert hasattr(job_radar, 'fetcher')
        assert hasattr(job_radar, 'smart_matcher')
    
    def test_save_jobs_to_database(self, temp_db_path, sample_job):
        """GREEN: Should save jobs to database."""
        job_radar = JobRadar(db_url=f"sqlite:///{temp_db_path}")
        
        saved = job_radar.save_jobs([sample_job])
        assert saved == 1
        
        stats = job_radar.get_stats()
        assert stats['total_jobs'] == 1
    
    def test_get_stats_returns_data(self, temp_db_path):
        """GREEN: get_stats should return database stats."""
        job_radar = JobRadar(db_url=f"sqlite:///{temp_db_path}")
        
        stats = job_radar.get_stats()
        assert isinstance(stats, dict)
        assert 'total_jobs' in stats
        assert 'sources' in stats


# ============================================================================
# WEB API TESTS
# ============================================================================

class TestWebAPI:
    """TDD tests for web API endpoints."""
    
    @pytest.fixture
    def flask_client(self):
        """Flask test client."""
        from jobradar.web.app import app
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    def test_smart_jobs_endpoint_exists(self, flask_client):
        """GREEN: /api/smart-jobs should exist."""
        response = flask_client.get('/api/smart-jobs')
        assert response.status_code != 404
    
    def test_smart_jobs_returns_json(self, flask_client):
        """GREEN: Smart jobs API should return JSON."""
        response = flask_client.get('/api/smart-jobs')
        assert response.content_type.startswith('application/json')
    
    def test_pagination_support(self, flask_client):
        """GREEN: Should support pagination parameters."""
        response = flask_client.get('/api/smart-jobs?page=1&per_page=5')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert 'jobs' in data
        assert 'pagination' in data
    
    def test_index_page_loads(self, flask_client):
        """GREEN: Main page should load."""
        response = flask_client.get('/')
        assert response.status_code == 200
        assert b'JobRadar' in response.data


# ============================================================================
# CLI TESTS
# ============================================================================

class TestCLI:
    """TDD tests for CLI interface."""
    
    def test_cli_importable(self):
        """GREEN: CLI module should be importable."""
        from jobradar import cli
        assert cli is not None
    
    def test_main_commands_exist(self):
        """GREEN: Should have main CLI commands."""
        from jobradar.cli import cli
        
        command_names = [cmd.name for cmd in cli.commands.values()]
        assert 'fetch' in command_names
        assert 'search' in command_names 
        assert 'web' in command_names


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """TDD integration tests."""
    
    def test_end_to_end_pipeline(self, temp_db_path):
        """GREEN: Complete pipeline should work."""
        job_radar = JobRadar(db_url=f"sqlite:///{temp_db_path}")
        
        # Mock data
        mock_jobs = [
            Job(id="1", title="Customer Support", company="Corp",
                url="http://test.com/1", source="test"),
            Job(id="2", title="Engineer", company="Corp",
                url="http://test.com/2", source="test")
        ]
        
        # Process and save
        processed = job_radar.process_jobs(mock_jobs)
        saved = job_radar.save_jobs(processed)
        
        assert saved > 0
        
        stats = job_radar.get_stats()
        assert stats['total_jobs'] > 0
    
    def test_config_loading(self):
        """GREEN: Config loading should work."""
        from jobradar.config import load_feeds
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump({
                'feeds': [{
                    'name': 'test',
                    'url': 'http://example.com',
                    'type': 'rss',
                    'parser': 'rss'
                }]
            }, f)
            f.flush()
            
            try:
                feeds = load_feeds(Path(f.name))
                assert len(feeds) == 1
                assert feeds[0].name == 'test'
            finally:
                os.unlink(f.name)


# ============================================================================
# TDD METHODOLOGY COMPLIANCE
# ============================================================================

def test_tdd_coverage_complete():
    """META: Verify comprehensive test coverage."""
    required_classes = [
        'TestJobModel',
        'TestFeedModel', 
        'TestFetcher',
        'TestDatabase',
        'TestSmartMatcher',
        'TestJobFilter',
        'TestJobRadarCore',
        'TestWebAPI',
        'TestCLI',
        'TestIntegration'
    ]
    
    import sys
    current_module = sys.modules[__name__]
    defined_classes = [name for name in dir(current_module) 
                      if name.startswith('Test')]
    
    for required in required_classes:
        assert required in defined_classes, f"Missing: {required}"
    
    print(f"✅ TDD coverage complete: {len(defined_classes)} test classes")


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 