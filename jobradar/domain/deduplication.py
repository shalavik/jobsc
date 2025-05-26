"""Fuzzy duplicate detection for job postings."""
import re
from typing import List, Tuple
from difflib import SequenceMatcher
from jobradar.domain.job import Job

class JobDeduplicator:
    """Handles fuzzy duplicate detection for job postings."""
    
    def __init__(self, similarity_threshold: float = 0.9):
        """Initialize the deduplicator.
        
        Args:
            similarity_threshold: Minimum similarity score (0-1) to consider jobs duplicates
        """
        self.similarity_threshold = similarity_threshold
        
        # Common abbreviations and their expansions
        self.normalizations = {
            r'\bsr\.?\b': 'senior',
            r'\bjr\.?\b': 'junior',
            r'\bmgr\.?\b': 'manager',
            r'\beng\.?\b': 'engineer',
            r'\bdev\.?\b': 'developer',
            r'\badmin\.?\b': 'administrator',
            r'\bassoc\.?\b': 'associate',
            r'\bspec\.?\b': 'specialist',
            r'\bcoord\.?\b': 'coordinator',
            r'\btech\.?\b': 'technical',
            r'\bsw\.?\b': 'software',
            r'\bhw\.?\b': 'hardware',
            r'\bqa\.?\b': 'quality assurance',
            r'\bui\.?\b': 'user interface',
            r'\bux\.?\b': 'user experience',
            r'\bapi\.?\b': 'application programming interface',
            r'\bdb\.?\b': 'database',
            r'\bsys\.?\b': 'system',
            r'\bops\.?\b': 'operations',
            r'\bhr\.?\b': 'human resources',
            r'\bit\.?\b': 'information technology',
            r'\bcs\.?\b': 'customer service',
            r'\bpm\.?\b': 'project manager',
            r'\bba\.?\b': 'business analyst',
            r'\bqa\.?\b': 'quality assurance',
        }
    
    def normalize_title(self, title: str) -> str:
        """Normalize a job title for comparison.
        
        Args:
            title: Original job title
            
        Returns:
            Normalized title string
        """
        # Convert to lowercase
        normalized = title.lower().strip()
        
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Apply normalizations (abbreviations -> full words)
        for pattern, replacement in self.normalizations.items():
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        
        # Remove common noise words and punctuation
        noise_patterns = [
            r'\b(the|a|an|and|or|at|in|on|for|with|by)\b',
            r'[^\w\s]',  # Remove punctuation
            r'\s+',      # Normalize whitespace again
        ]
        
        for pattern in noise_patterns:
            if pattern == r'\s+':
                normalized = re.sub(pattern, ' ', normalized)
            else:
                normalized = re.sub(pattern, '', normalized)
        
        return normalized.strip()
    
    def calculate_similarity(self, job1: Job, job2: Job) -> float:
        """Calculate similarity score between two jobs.
        
        Args:
            job1: First job
            job2: Second job
            
        Returns:
            Similarity score between 0 and 1
        """
        # Normalize titles
        title1 = self.normalize_title(job1.title)
        title2 = self.normalize_title(job2.title)
        
        # Calculate title similarity
        title_similarity = SequenceMatcher(None, title1, title2).ratio()
        
        # Company must match exactly (case-insensitive)
        company_match = job1.company.lower().strip() == job2.company.lower().strip()
        
        if not company_match:
            return 0.0  # Different companies = not duplicates
        
        # Weight title similarity heavily since company already matches
        return title_similarity
    
    def is_duplicate(self, job1: Job, job2: Job) -> bool:
        """Check if two jobs are duplicates.
        
        Args:
            job1: First job
            job2: Second job
            
        Returns:
            True if jobs are considered duplicates
        """
        similarity = self.calculate_similarity(job1, job2)
        return similarity >= self.similarity_threshold
    
    def find_duplicates(self, jobs: List[Job]) -> List[Tuple[Job, Job, float]]:
        """Find all duplicate pairs in a list of jobs.
        
        Args:
            jobs: List of jobs to check for duplicates
            
        Returns:
            List of tuples (job1, job2, similarity_score) for duplicate pairs
        """
        duplicates = []
        
        for i in range(len(jobs)):
            for j in range(i + 1, len(jobs)):
                similarity = self.calculate_similarity(jobs[i], jobs[j])
                if similarity >= self.similarity_threshold:
                    duplicates.append((jobs[i], jobs[j], similarity))
        
        return duplicates
    
    def deduplicate(self, jobs: List[Job]) -> List[Job]:
        """Remove duplicates from a list of jobs, keeping the first occurrence.
        
        Args:
            jobs: List of jobs to deduplicate
            
        Returns:
            List of unique jobs
        """
        unique_jobs = []
        seen_jobs = []
        
        for job in jobs:
            is_duplicate = False
            for seen_job in seen_jobs:
                if self.is_duplicate(job, seen_job):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_jobs.append(job)
                seen_jobs.append(job)
        
        return unique_jobs 