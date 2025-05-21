"""Tests for job filtering functionality."""
import pytest
from jobradar.filters import JobFilter, FilterConfig, create_filter_from_config
from jobradar.models import Job

@pytest.fixture
def filter_config():
    """Create a sample filter configuration."""
    return FilterConfig(
        keywords=["python", "developer"],
        locations=["remote", "worldwide"],
        exclude=["senior", "lead", "manager"]
    )

@pytest.fixture
def job_filter(filter_config):
    """Create a job filter instance."""
    return JobFilter(filter_config)

@pytest.fixture
def sample_jobs():
    """Create sample jobs for testing."""
    return [
        Job(
            id="1",
            title="Python Developer",
            company="Tech Corp",
            url="https://example.com/1",
            source="test",
            date="2024-01-01",
            location="Remote"
        ),
        Job(
            id="2",
            title="Senior Python Developer",
            company="Big Corp",
            url="https://example.com/2",
            source="test",
            date="2024-01-01",
            location="Worldwide"
        ),
        Job(
            id="3",
            title="Java Developer",
            company="Tech Corp",
            url="https://example.com/3",
            source="test",
            date="2024-01-01",
            location="New York"
        ),
        Job(
            id="4",
            title="Python Team Lead",
            company="Startup",
            url="https://example.com/4",
            source="test",
            date="2024-01-01",
            location="Remote"
        )
    ]

def test_matches_keywords(job_filter, sample_jobs):
    """Test keyword matching."""
    # Should match Python Developer
    assert job_filter.matches_keywords(sample_jobs[0]) is True
    
    # Should match Senior Python Developer
    assert job_filter.matches_keywords(sample_jobs[1]) is True
    
    # Should not match Java Developer (ensure keywords are set to only match Python)
    from jobradar.filters import FilterConfig, JobFilter
    new_config = FilterConfig(keywords=["python"], locations=job_filter.config.locations, exclude=job_filter.config.exclude)
    new_filter = JobFilter(new_config)
    assert new_filter.matches_keywords(sample_jobs[2]) is False

def test_matches_location(job_filter, sample_jobs):
    """Test location matching."""
    # Should match Remote
    assert job_filter.matches_location(sample_jobs[0]) is True
    
    # Should match Worldwide
    assert job_filter.matches_location(sample_jobs[1]) is True
    
    # Should not match New York
    assert job_filter.matches_location(sample_jobs[2]) is False

def test_is_excluded(job_filter, sample_jobs):
    """Test exclusion rules."""
    # Should not be excluded
    assert job_filter.is_excluded(sample_jobs[0]) is False
    
    # Should be excluded (contains "Senior")
    assert job_filter.is_excluded(sample_jobs[1]) is True
    
    # Should not be excluded
    assert job_filter.is_excluded(sample_jobs[2]) is False
    
    # Should be excluded (contains "Lead")
    assert job_filter.is_excluded(sample_jobs[3]) is True

def test_filter_jobs(job_filter, sample_jobs):
    """Test complete job filtering."""
    filtered_jobs = job_filter.filter_jobs(sample_jobs)
    
    # Should only include the first job
    assert len(filtered_jobs) == 1
    assert filtered_jobs[0].id == "1"
    assert filtered_jobs[0].title == "Python Developer"

def test_create_filter_from_config():
    """Test filter creation from config."""
    config = {
        'keywords': ['python', 'developer'],
        'locations': ['remote'],
        'exclude': ['senior']
    }
    
    job_filter = create_filter_from_config(config)
    assert isinstance(job_filter, JobFilter)
    assert len(job_filter.keyword_patterns) == 2
    assert len(job_filter.location_patterns) == 1
    assert len(job_filter.exclude_patterns) == 1

def test_empty_filter_config(sample_jobs):
    """Test filter with empty configuration."""
    from jobradar.filters import FilterConfig, JobFilter
    empty_config = FilterConfig(keywords=[], locations=[], exclude=[])
    job_filter = JobFilter(empty_config)
    
    # Should match everything with empty config
    assert job_filter.matches_keywords(sample_jobs[0]) is True
    assert job_filter.matches_location(sample_jobs[0]) is True
    assert job_filter.is_excluded(sample_jobs[0]) is False
    
    # Should return all jobs
    filtered_jobs = job_filter.filter_jobs(sample_jobs)
    assert len(filtered_jobs) == len(sample_jobs) 