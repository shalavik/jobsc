"""Database models and connection management."""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, JSON, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
import logging
import json
import functools
import time

logger = logging.getLogger(__name__)

Base = declarative_base()

# Simple cache decorator
def cache_result(ttl_seconds=300):
    """Cache function results for a specified time to improve performance."""
    def decorator(func):
        cache = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create a cache key from function args
            key = str(args) + str(kwargs)
            
            # Check if result is in cache and not expired
            if key in cache:
                result, timestamp = cache[key]
                if time.time() - timestamp < ttl_seconds:
                    return result
            
            # Get fresh result
            result = func(*args, **kwargs)
            cache[key] = (result, time.time())
            return result
        
        return wrapper
    return decorator

class JobModel(Base):
    """SQLAlchemy model for job listings."""
    __tablename__ = 'jobs'
    
    id = Column(String(255), primary_key=True)
    title = Column(String(255), nullable=False, index=True)
    company = Column(String(255), nullable=False, index=True)
    url = Column(String(512), nullable=False)
    source = Column(String(50), nullable=False, index=True)
    date = Column(DateTime, nullable=True, index=True)
    description = Column(Text, nullable=True)
    location = Column(String(255), nullable=True, index=True)
    salary = Column(String(255), nullable=True)
    job_type = Column(String(50), nullable=True, index=True)
    experience_level = Column(String(50), nullable=True, index=True)
    is_remote = Column(Boolean, default=False, index=True)
    skills = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

class Database:
    """Database connection and operation manager."""
    
    def __init__(self, db_url: str = "sqlite:///jobs.db"):
        """Initialize database connection.
        
        Args:
            db_url: Database connection URL
        """
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
        self._create_tables()
    
    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        Base.metadata.create_all(self.engine)
    
    def _parse_salary(self, salary_str: str) -> Optional[int]:
        """Parse salary string to integer value.
        
        Args:
            salary_str: Salary string (e.g., "$100k", "100000")
            
        Returns:
            Optional[int]: Parsed salary value or None
        """
        if not salary_str:
            return None
            
        # Remove currency symbols and convert to lowercase
        salary_str = salary_str.lower().replace('$', '').replace(',', '')
        
        # Handle 'k' suffix
        if 'k' in salary_str:
            salary_str = salary_str.replace('k', '')
            try:
                return int(float(salary_str) * 1000)
            except ValueError:
                return None
                
        try:
            return int(salary_str)
        except ValueError:
            return None
    
    def add_job(self, job: 'Job') -> bool:
        """Add a job to the database.
        
        Args:
            job: Job object to add
            
        Returns:
            bool: True if job was added successfully
        """
        try:
            with self.Session() as session:
                # Check if job already exists
                existing = session.query(JobModel).filter_by(id=job.id).first()
                if existing:
                    # Update existing job
                    existing.title = job.title
                    existing.company = job.company
                    existing.url = job.url
                    existing.date = datetime.fromisoformat(job.date) if job.date else None
                    existing.description = getattr(job, 'description', None)
                    existing.location = getattr(job, 'location', None)
                    existing.salary = getattr(job, 'salary', None)
                    existing.job_type = getattr(job, 'job_type', None)
                    existing.experience_level = getattr(job, 'experience_level', None)
                    existing.is_remote = getattr(job, 'is_remote', False)
                    existing.skills = getattr(job, 'skills', [])
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new job
                    job_model = JobModel(
                        id=job.id,
                        title=job.title,
                        company=job.company,
                        url=job.url,
                        source=job.source,
                        date=datetime.fromisoformat(job.date) if job.date else None,
                        description=getattr(job, 'description', None),
                        location=getattr(job, 'location', None),
                        salary=getattr(job, 'salary', None),
                        job_type=getattr(job, 'job_type', None),
                        experience_level=getattr(job, 'experience_level', None),
                        is_remote=getattr(job, 'is_remote', False),
                        skills=getattr(job, 'skills', [])
                    )
                    session.add(job_model)
                
                session.commit()
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Error adding job to database: {str(e)}")
            return False
    
    def add_jobs(self, jobs: List['Job']) -> int:
        """Add multiple jobs to the database in a single transaction.
        
        Args:
            jobs: List of Job objects to add
            
        Returns:
            int: Number of jobs successfully added
        """
        if not jobs:
            return 0
            
        try:
            with self.Session() as session:
                # Get existing job IDs to determine which to update vs. insert
                job_ids = [job.id for job in jobs]
                existing_jobs = {
                    job.id: job for job in 
                    session.query(JobModel).filter(JobModel.id.in_(job_ids)).all()
                }
                
                success_count = 0
                for job in jobs:
                    try:
                        if job.id in existing_jobs:
                            # Update existing job
                            model = existing_jobs[job.id]
                            model.title = job.title
                            model.company = job.company
                            model.url = job.url
                            model.date = datetime.fromisoformat(job.date) if job.date else None
                            model.description = getattr(job, 'description', None)
                            model.location = getattr(job, 'location', None)
                            model.salary = getattr(job, 'salary', None)
                            model.job_type = getattr(job, 'job_type', None)
                            model.experience_level = getattr(job, 'experience_level', None)
                            model.is_remote = getattr(job, 'is_remote', False)
                            model.skills = getattr(job, 'skills', [])
                            model.updated_at = datetime.utcnow()
                        else:
                            # Create new job
                            model = JobModel(
                                id=job.id,
                                title=job.title,
                                company=job.company,
                                url=job.url,
                                source=job.source,
                                date=datetime.fromisoformat(job.date) if job.date else None,
                                description=getattr(job, 'description', None),
                                location=getattr(job, 'location', None),
                                salary=getattr(job, 'salary', None),
                                job_type=getattr(job, 'job_type', None),
                                experience_level=getattr(job, 'experience_level', None),
                                is_remote=getattr(job, 'is_remote', False),
                                skills=getattr(job, 'skills', [])
                            )
                            session.add(model)
                        success_count += 1
                    except Exception as e:
                        logger.error(f"Error adding job {job.id}: {str(e)}")
                
                # Commit once at the end
                session.commit()
                return success_count
                
        except SQLAlchemyError as e:
            logger.error(f"Error adding jobs to database: {str(e)}")
            return 0
    
    def get_job(self, job_id: str) -> Optional[JobModel]:
        """Get a job by ID.
        
        Args:
            job_id: Job ID to look up
            
        Returns:
            Optional[JobModel]: Job if found, None otherwise
        """
        try:
            with self.Session() as session:
                return session.query(JobModel).filter_by(id=job_id).first()
        except SQLAlchemyError as e:
            logger.error(f"Error getting job from database: {str(e)}")
            return None
    
    def search_jobs(self, filters: Dict[str, Any], limit: int = 100, offset: int = 0) -> List[JobModel]:
        """Search for jobs matching criteria with pagination.
        
        Args:
            filters: Dictionary of filter criteria
            limit: Maximum number of results to return
            offset: Number of results to skip (for pagination)
            
        Returns:
            List[JobModel]: List of matching jobs
        """
        try:
            with self.Session() as session:
                query = session.query(JobModel)
                query = self._apply_filters(query, filters)
                return query.order_by(JobModel.date.desc()).offset(offset).limit(limit).all()
                
        except SQLAlchemyError as e:
            logger.error(f"Error searching jobs in database: {str(e)}")
            return []
            
    def count_jobs(self, filters: Dict[str, Any] = None) -> int:
        """Count jobs matching criteria.
        
        Args:
            filters: Dictionary of filter criteria
            
        Returns:
            int: Count of matching jobs
        """
        try:
            with self.Session() as session:
                query = session.query(func.count(JobModel.id))
                if filters:
                    query = self._apply_filters(query, filters)
                return query.scalar() or 0
                
        except SQLAlchemyError as e:
            logger.error(f"Error counting jobs in database: {str(e)}")
            return 0
            
    def _apply_filters(self, query, filters: Dict[str, Any]):
        """Apply filters to a query.
        
        Args:
            query: SQLAlchemy query object
            filters: Dictionary of filter criteria
            
        Returns:
            SQLAlchemy query with filters applied
        """
        # Apply text-based filters
        if filters.get('company'):
            query = query.filter(JobModel.company.ilike(f"%{filters['company']}%"))
        if filters.get('title'):
            query = query.filter(JobModel.title.ilike(f"%{filters['title']}%"))
        if filters.get('source'):
            query = query.filter(JobModel.source == filters['source'])
        if filters.get('location'):
            query = query.filter(JobModel.location.ilike(f"%{filters['location']}%"))
        if filters.get('job_type'):
            query = query.filter(JobModel.job_type.ilike(f"%{filters['job_type']}%"))
        if filters.get('experience_level'):
            query = query.filter(JobModel.experience_level.ilike(f"%{filters['experience_level']}%"))
        
        # Apply boolean filter
        if filters.get('is_remote') is not None:
            query = query.filter(JobModel.is_remote == filters['is_remote'])
        
        # Apply salary range filters
        if filters.get('salary_min'):
            query = query.filter(
                JobModel.salary.isnot(None)
            ).filter(
                self._parse_salary(JobModel.salary) >= filters['salary_min']
            )
        if filters.get('salary_max'):
            query = query.filter(
                JobModel.salary.isnot(None)
            ).filter(
                self._parse_salary(JobModel.salary) <= filters['salary_max']
            )
            
        return query
    
    def delete_old_jobs(self, days: int = 30) -> int:
        """Delete jobs older than specified number of days.
        
        Args:
            days: Number of days after which jobs should be deleted
            
        Returns:
            int: Number of jobs deleted
        """
        try:
            with self.Session() as session:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                result = session.query(JobModel).filter(
                    JobModel.updated_at < cutoff_date
                ).delete()
                session.commit()
                return result
                
        except SQLAlchemyError as e:
            logger.error(f"Error deleting old jobs from database: {str(e)}")
            return 0
    
    @cache_result(ttl_seconds=300)
    def get_unique_values(self, field: str) -> List[str]:
        """Get unique values for a field from the database.
        
        Args:
            field: Name of the field to get unique values for
            
        Returns:
            List[str]: List of unique values
        """
        try:
            with self.Session() as session:
                if not hasattr(JobModel, field):
                    return []
                    
                column = getattr(JobModel, field)
                results = session.query(column).distinct().all()
                return [r[0] for r in results if r[0] is not None]
                
        except SQLAlchemyError as e:
            logger.error(f"Error getting unique values for {field}: {str(e)}")
            return [] 