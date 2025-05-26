"""Smart job title matching functionality."""
from typing import List, Set, Dict, Optional
import re
from dataclasses import dataclass
import logging
from .job import Job

logger = logging.getLogger(__name__)

@dataclass
class SmartTitleMatcher:
    """Intelligent job title matcher that can find relevant jobs based on keywords."""
    
    # Define categories of job titles the user is interested in
    INTERESTED_KEYWORDS = {
        'customer_support': [
            'customer service', 'customer support', 'customer experience', 
            'customer operations', 'client services', 'customer happiness',
            'client relations', 'customer success', 'customer advocate',
            'customer onboarding', 'customer solutions'
        ],
        'support_roles': [
            'support', 'support specialist', 'support representative',
            'support analyst', 'support technician', 'customer care'
        ],
        'technical_support': [
            'technical support', 'product support', 'support engineer', 
            'application support', 'it support', 'escalation support',
            'helpdesk technician', 'helpdesk', 'technical account manager',
            'l1 support', 'l2 support', 'l3 support'
        ],
        'specialist_roles': [
            'integration specialist', 'onboarding specialist', 
            'client implementation', 'implementation engineer',
            'solutions engineer', 'partner solutions', 'pre-sales engineer',
            'technical account manager', 'account manager'
        ],
        'compliance_analysis': [
            'aml analyst', 'compliance analyst', 'fraud analyst',
            'transaction monitoring', 'compliance operations',
            'financial crime analyst', 'risk compliance officer',
            'crypto compliance', 'kyc analyst', 'edd analyst',
            'compliance officer', 'risk officer', 'risk analyst'
        ],
        'operations': [
            'operations', 'operations specialist', 'operations analyst',
            'business operations', 'client operations'
        ]
    }
    
    # Words to exclude to avoid false positives
    EXCLUDE_KEYWORDS = [
        'software engineer', 'software developer', 'full stack', 'frontend', 'backend',
        'devops', 'data scientist', 'machine learning', 'ai engineer', 'web developer',
        'mobile developer', 'ios developer', 'android developer', 'ui/ux designer',
        'product manager', 'project manager', 'scrum master', 'engineering manager'
    ]
    
    def __init__(self, active_categories: Optional[List[str]] = None):
        """Initialize the smart title matcher.
        
        Args:
            active_categories: List of categories to use for matching (None for all)
        """
        self.active_categories = active_categories or list(self.INTERESTED_KEYWORDS.keys())
        self.keyword_patterns = self._compile_patterns()
        self.exclude_patterns = self._compile_exclude_patterns()
        
    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Compile regex patterns for efficient matching."""
        patterns = {}
        
        # Only compile patterns for active categories
        for category, keywords in self.INTERESTED_KEYWORDS.items():
            if category in self.active_categories:
                patterns[category] = []
                for keyword in keywords:
                    # Create pattern for exact phrase matching
                    exact_pattern = re.compile(rf'\b{re.escape(keyword)}\b', re.IGNORECASE)
                    patterns[category].append(exact_pattern)
                    
                    # For multi-word keywords, also add individual important words
                    words = keyword.split()
                    if len(words) > 1:
                        for word in words:
                            if len(word) > 4 and word.lower() not in ['analyst', 'engineer', 'specialist']:
                                # Only add specific domain words
                                if word.lower() in ['support', 'customer', 'compliance', 'operations', 'implementation', 'onboarding']:
                                    word_pattern = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
                                    patterns[category].append(word_pattern)
        
        return patterns
    
    def _compile_exclude_patterns(self) -> List[re.Pattern]:
        """Compile exclude patterns to filter out non-relevant jobs."""
        patterns = []
        for keyword in self.EXCLUDE_KEYWORDS:
            pattern = re.compile(rf'\b{re.escape(keyword)}\b', re.IGNORECASE)
            patterns.append(pattern)
        return patterns
    
    def get_match_score(self, job: Job) -> Dict[str, int]:
        """Calculate match scores for each category.
        
        Args:
            job: Job to evaluate
            
        Returns:
            Dict mapping category names to match scores
        """
        text_to_check = f"{job.title} {job.company}"
        if hasattr(job, 'description') and job.description:
            text_to_check += f" {job.description}"
        
        # First check if this job should be excluded
        for exclude_pattern in self.exclude_patterns:
            if exclude_pattern.search(text_to_check):
                logger.debug(f"Excluding job '{job.title}' - matches exclude pattern: {exclude_pattern.pattern}")
                return {category: 0 for category in self.active_categories}
            
        scores = {}
        
        for category, patterns in self.keyword_patterns.items():
            score = 0
            matched_patterns = set()
            
            for pattern in patterns:
                if pattern.search(text_to_check) and pattern.pattern not in matched_patterns:
                    score += 1
                    matched_patterns.add(pattern.pattern)
                    
            scores[category] = score
            
        return scores
    
    def is_relevant_job(self, job: Job, min_score: int = 1) -> bool:
        """Check if a job is relevant based on title matching.
        
        Args:
            job: Job to check
            min_score: Minimum total score across all categories
            
        Returns:
            bool: True if job is relevant
        """
        scores = self.get_match_score(job)
        total_score = sum(scores.values())
        
        if total_score >= min_score:
            # Log the match for debugging
            matched_categories = [cat for cat, score in scores.items() if score > 0]
            logger.debug(f"Job '{job.title}' at '{job.company}' matched categories: {matched_categories}")
            return True
            
        return False
    
    def get_matching_keywords(self, job: Job) -> List[str]:
        """Get the specific keywords that matched for a job.
        
        Args:
            job: Job to check
            
        Returns:
            List of matched keywords
        """
        text_to_check = f"{job.title} {job.company}".lower()
        if hasattr(job, 'description') and job.description:
            text_to_check += f" {job.description}".lower()
            
        matched_keywords = []
        
        for category, keywords in self.INTERESTED_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text_to_check:
                    matched_keywords.append(keyword)
                else:
                    # Check for partial word matches for important keywords
                    words = keyword.split()
                    if len(words) > 1:
                        for word in words:
                            if (len(word) > 4 and word.lower() in text_to_check and 
                                word.lower() in ['support', 'customer', 'compliance', 'operations', 'implementation', 'onboarding']):
                                matched_keywords.append(word)
                                
        return list(set(matched_keywords))  # Remove duplicates
    
    def filter_jobs(self, jobs: List[Job], min_score: int = 1) -> List[Job]:
        """Filter jobs to only include those that match user interests.
        
        Args:
            jobs: List of jobs to filter
            min_score: Minimum score threshold
            
        Returns:
            List of relevant jobs
        """
        relevant_jobs = []
        
        for job in jobs:
            if self.is_relevant_job(job, min_score):
                relevant_jobs.append(job)
                matched_keywords = self.get_matching_keywords(job)
                logger.info(f"Including job: '{job.title}' at '{job.company}' - Keywords: {matched_keywords}")
            else:
                logger.debug(f"Excluding job: '{job.title}' at '{job.company}' - No relevant keywords found")
                
        return relevant_jobs
    
    def search_jobs_by_interest(self, jobs: List[Job], categories: Optional[List[str]] = None) -> List[Job]:
        """Search for jobs matching specific interest categories.
        
        Args:
            jobs: List of jobs to search
            categories: List of category names to search for (None for all)
            
        Returns:
            List of matching jobs
        """
        if not categories:
            categories = list(self.INTERESTED_KEYWORDS.keys())
            
        matching_jobs = []
        
        for job in jobs:
            scores = self.get_match_score(job)
            
            # Check if any of the requested categories have matches
            if any(scores.get(cat, 0) > 0 for cat in categories):
                matching_jobs.append(job)
                
        return matching_jobs

def create_smart_matcher(categories: Optional[List[str]] = None) -> SmartTitleMatcher:
    """Factory function to create a smart title matcher.
    
    Args:
        categories: List of categories to use for matching (None for all)
    
    Returns:
        SmartTitleMatcher: Configured smart matcher instance
    """
    return SmartTitleMatcher(active_categories=categories) 