"""Tests for SmartTitleMatcher functionality."""
import pytest
from jobradar.smart_matcher import SmartTitleMatcher, create_smart_matcher
from jobradar.models import Job

@pytest.fixture
def smart_matcher():
    """Create a smart matcher instance for testing."""
    return create_smart_matcher()

@pytest.fixture
def sample_jobs():
    """Create sample jobs for testing."""
    return [
        Job(
            id="1",
            title="Customer Support Representative",
            company="Tech Corp",
            url="https://example.com/job1",
            source="test",
            date=""
        ),
        Job(
            id="2", 
            title="Software Engineer",
            company="Dev Company",
            url="https://example.com/job2",
            source="test",
            date=""
        ),
        Job(
            id="3",
            title="Technical Support Specialist",
            company="Support Inc",
            url="https://example.com/job3", 
            source="test",
            date=""
        ),
        Job(
            id="4",
            title="Compliance Analyst",
            company="Bank Corp",
            url="https://example.com/job4",
            source="test", 
            date=""
        ),
        Job(
            id="5",
            title="Operations Manager",
            company="Ops Company", 
            url="https://example.com/job5",
            source="test",
            date=""
        ),
        Job(
            id="6",
            title="Full Stack Developer",
            company="Tech Startup",
            url="https://example.com/job6",
            source="test",
            date=""
        ),
        Job(
            id="7",
            title="Customer Success Manager",
            company="SaaS Corp",
            url="https://example.com/job7", 
            source="test",
            date=""
        ),
        Job(
            id="8",
            title="AML Analyst",
            company="Financial Services",
            url="https://example.com/job8",
            source="test",
            date=""
        )
    ]

def test_smart_matcher_creation():
    """Test creating a smart matcher."""
    matcher = create_smart_matcher()
    assert isinstance(matcher, SmartTitleMatcher)
    assert len(matcher.INTERESTED_KEYWORDS) == 6  # 6 categories
    assert len(matcher.EXCLUDE_KEYWORDS) > 0

def test_customer_support_matching(smart_matcher, sample_jobs):
    """Test matching customer support jobs."""
    customer_support_job = sample_jobs[0]  # Customer Support Representative
    customer_success_job = sample_jobs[6]  # Customer Success Manager
    
    scores = smart_matcher.get_match_score(customer_support_job)
    assert scores['customer_support'] > 0
    assert scores['support_roles'] > 0
    
    scores = smart_matcher.get_match_score(customer_success_job)
    assert scores['customer_support'] > 0
    
    assert smart_matcher.is_relevant_job(customer_support_job)
    assert smart_matcher.is_relevant_job(customer_success_job)

def test_exclude_patterns(smart_matcher, sample_jobs):
    """Test that excluded jobs are filtered out."""
    software_engineer_job = sample_jobs[1]  # Software Engineer  
    full_stack_job = sample_jobs[5]  # Full Stack Developer
    
    # These should be excluded
    scores = smart_matcher.get_match_score(software_engineer_job)
    assert sum(scores.values()) == 0
    
    scores = smart_matcher.get_match_score(full_stack_job)
    assert sum(scores.values()) == 0
    
    assert not smart_matcher.is_relevant_job(software_engineer_job)
    assert not smart_matcher.is_relevant_job(full_stack_job)

def test_filter_jobs(smart_matcher, sample_jobs):
    """Test filtering jobs based on relevance."""
    relevant_jobs = smart_matcher.filter_jobs(sample_jobs, min_score=1)
    
    # Should exclude software engineer and full stack developer
    job_titles = [job.title for job in relevant_jobs]
    assert "Software Engineer" not in job_titles
    assert "Full Stack Developer" not in job_titles
    
    # Should include relevant jobs
    assert len(relevant_jobs) > 0 