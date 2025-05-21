"""Tests for database functionality."""
import pytest
from datetime import datetime, timedelta
from jobradar.database import Database, JobModel
from jobradar.models import Job

@pytest.fixture
def db():
    """Create a test database instance."""
    return Database("sqlite:///:memory:")

@pytest.fixture
def sample_job():
    """Create a sample job for testing."""
    return Job(
        id="test123",
        title="Python Developer",
        company="Test Company",
        url="https://example.com/job1",
        source="test",
        date="2024-01-01T00:00:00"
    )

def test_add_job(db, sample_job):
    """Test adding a job to the database."""
    assert db.add_job(sample_job) is True
    
    # Verify job was added
    job = db.get_job(sample_job.id)
    assert job is not None
    assert job.title == sample_job.title
    assert job.company == sample_job.company
    assert job.url == sample_job.url
    assert job.source == sample_job.source

def test_add_job_duplicate(db, sample_job):
    """Test adding a duplicate job updates existing record."""
    # Add job first time
    assert db.add_job(sample_job) is True
    
    # Modify job and add again
    sample_job.title = "Updated Title"
    assert db.add_job(sample_job) is True
    
    # Verify job was updated
    job = db.get_job(sample_job.id)
    assert job.title == "Updated Title"

def test_add_jobs(db):
    """Test adding multiple jobs."""
    jobs = [
        Job(id=f"test{i}", title=f"Job {i}", company="Test", url=f"https://example.com/{i}", source="test")
        for i in range(3)
    ]
    
    assert db.add_jobs(jobs) == 3
    
    # Verify all jobs were added
    for job in jobs:
        assert db.get_job(job.id) is not None

def test_search_jobs(db, sample_job):
    """Test searching for jobs."""
    # Add test job
    db.add_job(sample_job)
    
    # Search by company
    results = db.search_jobs(filters={"company": "Test Company"})
    assert any(job.company == "Test Company" for job in results)
    
    # Search by title
    results = db.search_jobs(filters={"title": "Python"})
    assert len(results) == 1
    assert "Python" in results[0].title
    
    # Search with no matches
    results = db.search_jobs(filters={"company": "Nonexistent"})
    assert len(results) == 0

def test_search_jobs_limit(db):
    """Test search results limit."""
    # Add multiple jobs
    jobs = [
        Job(id=f"test{i}", title=f"Job {i}", company="Test", url=f"https://example.com/{i}", source="test")
        for i in range(5)
    ]
    db.add_jobs(jobs)
    
    # Test limit
    results = db.search_jobs(filters={}, limit=3)
    assert len(results) == 3

def test_delete_old_jobs(db, sample_job):
    """Test deleting old jobs."""
    # Add test job
    db.add_job(sample_job)
    
    # Delete jobs older than 1 day
    assert db.delete_old_jobs(days=1) == 0  # Should not delete recent job
    
    # Modify job to be old
    with db.Session() as session:
        job = session.query(JobModel).filter_by(id=sample_job.id).first()
        job.updated_at = datetime.utcnow() - timedelta(days=2)
        session.commit()
    
    # Delete old jobs
    assert db.delete_old_jobs(days=1) == 1  # Should delete old job
    
    # Verify job was deleted
    assert db.get_job(sample_job.id) is None 