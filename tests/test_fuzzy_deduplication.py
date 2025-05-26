"""Tests for fuzzy duplicate detection."""
import pytest
from jobradar.domain.job import Job, JobSource
from jobradar.domain.deduplication import JobDeduplicator

class TestJobDeduplicator:
    """Test fuzzy duplicate detection functionality."""
    
    @pytest.fixture
    def deduplicator(self):
        """Create a JobDeduplicator instance."""
        return JobDeduplicator(similarity_threshold=0.9)
    
    def test_senior_vs_sr_detected_as_duplicate(self, deduplicator):
        """Test that 'Senior' vs 'Sr.' are detected as duplicates."""
        job1 = Job(
            title="Senior Software Engineer",
            company="TechCorp",
            location="Remote",
            description="Senior role",
            url="https://example.com/job1",
            source=JobSource.LINKEDIN
        )
        
        job2 = Job(
            title="Sr. Software Engineer",
            company="TechCorp",
            location="Remote", 
            description="Senior role abbreviated",
            url="https://example.com/job2",
            source=JobSource.LINKEDIN
        )
        
        similarity = deduplicator.calculate_similarity(job1, job2)
        assert similarity >= 0.9, f"Similarity {similarity} should be ≥ 0.9"
        assert deduplicator.is_duplicate(job1, job2)
    
    def test_different_companies_not_duplicates(self, deduplicator):
        """Test that same title at different companies are not duplicates."""
        job1 = Job(
            title="Software Engineer",
            company="TechCorp",
            location="Remote",
            description="Role at TechCorp",
            url="https://example.com/job1",
            source=JobSource.LINKEDIN
        )
        
        job2 = Job(
            title="Software Engineer",
            company="StartupCo",
            location="Remote",
            description="Role at StartupCo", 
            url="https://example.com/job2",
            source=JobSource.LINKEDIN
        )
        
        assert not deduplicator.is_duplicate(job1, job2)
    
    def test_title_normalization(self, deduplicator):
        """Test that title normalization works correctly."""
        # Test abbreviation expansion
        assert "senior" in deduplicator.normalize_title("Sr. Engineer")
        assert "junior" in deduplicator.normalize_title("Jr. Developer")
        assert "manager" in deduplicator.normalize_title("Mgr. Position")
        
        # Test case insensitivity
        assert deduplicator.normalize_title("SENIOR ENGINEER") == deduplicator.normalize_title("senior engineer")
        
        # Test punctuation removal
        normalized = deduplicator.normalize_title("Software Engineer - Full Stack")
        assert "-" not in normalized
    
    def test_find_duplicates_in_list(self, deduplicator):
        """Test finding duplicates in a list of jobs."""
        jobs = [
            Job(
                title="Senior Developer",
                company="TechCorp",
                location="Remote",
                description="Senior dev role",
                url="https://example.com/job1",
                source=JobSource.LINKEDIN
            ),
            Job(
                title="Sr. Developer", 
                company="TechCorp",
                location="Remote",
                description="Senior dev role abbreviated",
                url="https://example.com/job2",
                source=JobSource.LINKEDIN
            ),
            Job(
                title="Junior Developer",
                company="TechCorp", 
                location="Remote",
                description="Junior dev role",
                url="https://example.com/job3",
                source=JobSource.LINKEDIN
            )
        ]
        
        duplicates = deduplicator.find_duplicates(jobs)
        assert len(duplicates) == 1
        assert duplicates[0][2] >= 0.9  # Similarity score
    
    def test_deduplicate_removes_duplicates(self, deduplicator):
        """Test that deduplication removes duplicate jobs."""
        jobs = [
            Job(
                title="Senior Engineer",
                company="TechCorp",
                location="Remote",
                description="First posting",
                url="https://example.com/job1",
                source=JobSource.LINKEDIN
            ),
            Job(
                title="Sr. Engineer",
                company="TechCorp", 
                location="Remote",
                description="Duplicate posting",
                url="https://example.com/job2",
                source=JobSource.LINKEDIN
            ),
            Job(
                title="Data Scientist",
                company="TechCorp",
                location="Remote", 
                description="Different role",
                url="https://example.com/job3",
                source=JobSource.LINKEDIN
            )
        ]
        
        unique_jobs = deduplicator.deduplicate(jobs)
        assert len(unique_jobs) == 2
        
        # Should keep the first occurrence
        titles = [job.title for job in unique_jobs]
        assert "Senior Engineer" in titles
        assert "Data Scientist" in titles
        assert "Sr. Engineer" not in titles
    
    def test_high_similarity_threshold_works(self):
        """Test that the 90% similarity threshold works as expected."""
        deduplicator = JobDeduplicator(similarity_threshold=0.95)
        
        job1 = Job(
            title="Software Engineer",
            company="TechCorp",
            location="Remote",
            description="Role 1",
            url="https://example.com/job1", 
            source=JobSource.LINKEDIN
        )
        
        job2 = Job(
            title="Software Developer",  # Similar but not identical
            company="TechCorp",
            location="Remote",
            description="Role 2",
            url="https://example.com/job2",
            source=JobSource.LINKEDIN
        )
        
        # Should not be considered duplicates with high threshold
        assert not deduplicator.is_duplicate(job1, job2) 