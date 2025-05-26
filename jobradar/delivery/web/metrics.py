"""Metrics endpoint for monitoring job fetch success rates and errors."""
import time
from typing import Dict, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)

@dataclass
class MetricsCollector:
    """Collects and stores application metrics."""
    
    # Job fetching metrics
    jobs_fetched_total: int = 0
    jobs_fetched_by_source: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    fetch_errors_total: int = 0
    fetch_errors_by_source: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    fetch_errors_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Rate limiting metrics
    rate_limit_hits: int = 0
    rate_limit_hits_by_source: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Response time tracking (last 100 requests)
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    
    # Duplicate detection metrics
    duplicates_found: int = 0
    duplicates_removed: int = 0
    
    # Job expiration metrics
    expired_jobs_removed: int = 0
    
    # Application start time
    start_time: float = field(default_factory=time.time)
    
    def record_job_fetched(self, source: str, count: int = 1) -> None:
        """Record successful job fetch.
        
        Args:
            source: Job source name
            count: Number of jobs fetched
        """
        self.jobs_fetched_total += count
        self.jobs_fetched_by_source[source] += count
        
    def record_fetch_error(self, source: str, error_type: str = "generic") -> None:
        """Record a fetch error.
        
        Args:
            source: Job source name
            error_type: Type of error (timeout, rate_limit, parse_error, etc.)
        """
        self.fetch_errors_total += 1
        self.fetch_errors_by_source[source] += 1
        self.fetch_errors_by_type[error_type] += 1
        
    def record_rate_limit_hit(self, source: str) -> None:
        """Record a rate limit hit.
        
        Args:
            source: Job source name
        """
        self.rate_limit_hits += 1
        self.rate_limit_hits_by_source[source] += 1
        
    def record_response_time(self, duration: float) -> None:
        """Record API response time.
        
        Args:
            duration: Response time in seconds
        """
        self.response_times.append(duration)
        
    def record_duplicates_found(self, count: int) -> None:
        """Record duplicates found during deduplication.
        
        Args:
            count: Number of duplicates found
        """
        self.duplicates_found += count
        
    def record_duplicates_removed(self, count: int) -> None:
        """Record duplicates removed during deduplication.
        
        Args:
            count: Number of duplicates removed
        """
        self.duplicates_removed += count
        
    def record_expired_jobs_removed(self, count: int) -> None:
        """Record expired jobs removed.
        
        Args:
            count: Number of expired jobs removed
        """
        self.expired_jobs_removed += count
        
    def get_success_rate(self, source: str = None) -> float:
        """Calculate fetch success rate.
        
        Args:
            source: Optional source to calculate rate for
            
        Returns:
            Success rate as percentage (0-100)
        """
        if source:
            fetched = self.jobs_fetched_by_source.get(source, 0)
            errors = self.fetch_errors_by_source.get(source, 0)
        else:
            fetched = self.jobs_fetched_total
            errors = self.fetch_errors_total
            
        total = fetched + errors
        if total == 0:
            return 100.0
            
        return (fetched / total) * 100.0
        
    def get_average_response_time(self) -> float:
        """Get average response time from recent requests.
        
        Returns:
            Average response time in seconds
        """
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)
        
    def get_uptime(self) -> float:
        """Get application uptime in seconds.
        
        Returns:
            Uptime in seconds
        """
        return time.time() - self.start_time

# Global metrics collector
metrics = MetricsCollector()

def create_metrics_router() -> APIRouter:
    """Create FastAPI router for metrics endpoints.
    
    Returns:
        FastAPI router with metrics endpoints
    """
    router = APIRouter(prefix="/metrics", tags=["metrics"])
    
    @router.get("/")
    async def get_metrics() -> Dict[str, Any]:
        """Get all application metrics.
        
        Returns:
            Dictionary containing all metrics
        """
        return {
            "jobs": {
                "fetched_total": metrics.jobs_fetched_total,
                "fetched_by_source": dict(metrics.jobs_fetched_by_source),
                "duplicates_found": metrics.duplicates_found,
                "duplicates_removed": metrics.duplicates_removed,
                "expired_removed": metrics.expired_jobs_removed
            },
            "errors": {
                "fetch_errors_total": metrics.fetch_errors_total,
                "fetch_errors_by_source": dict(metrics.fetch_errors_by_source),
                "fetch_errors_by_type": dict(metrics.fetch_errors_by_type)
            },
            "rate_limiting": {
                "rate_limit_hits": metrics.rate_limit_hits,
                "rate_limit_hits_by_source": dict(metrics.rate_limit_hits_by_source)
            },
            "performance": {
                "average_response_time_ms": metrics.get_average_response_time() * 1000,
                "uptime_seconds": metrics.get_uptime()
            },
            "success_rates": {
                "overall": metrics.get_success_rate(),
                "by_source": {
                    source: metrics.get_success_rate(source)
                    for source in metrics.jobs_fetched_by_source.keys()
                }
            }
        }
    
    @router.get("/health")
    async def health_check() -> Dict[str, Any]:
        """Health check endpoint.
        
        Returns:
            Health status and basic metrics
        """
        overall_success_rate = metrics.get_success_rate()
        avg_response_time = metrics.get_average_response_time()
        
        # Determine health status
        status = "healthy"
        if overall_success_rate < 80:
            status = "degraded"
        if overall_success_rate < 50 or avg_response_time > 5.0:
            status = "unhealthy"
            
        return {
            "status": status,
            "uptime_seconds": metrics.get_uptime(),
            "success_rate_percent": overall_success_rate,
            "average_response_time_ms": avg_response_time * 1000,
            "jobs_fetched_total": metrics.jobs_fetched_total,
            "errors_total": metrics.fetch_errors_total
        }
    
    @router.get("/sources")
    async def get_source_metrics() -> Dict[str, Any]:
        """Get metrics broken down by job source.
        
        Returns:
            Per-source metrics
        """
        sources = set(metrics.jobs_fetched_by_source.keys()) | set(metrics.fetch_errors_by_source.keys())
        
        source_metrics = {}
        for source in sources:
            fetched = metrics.jobs_fetched_by_source.get(source, 0)
            errors = metrics.fetch_errors_by_source.get(source, 0)
            rate_limits = metrics.rate_limit_hits_by_source.get(source, 0)
            success_rate = metrics.get_success_rate(source)
            
            source_metrics[source] = {
                "jobs_fetched": fetched,
                "errors": errors,
                "rate_limit_hits": rate_limits,
                "success_rate_percent": success_rate
            }
            
        return source_metrics
    
    @router.post("/reset")
    async def reset_metrics() -> Dict[str, str]:
        """Reset all metrics (for testing/debugging).
        
        Returns:
            Confirmation message
        """
        global metrics
        metrics = MetricsCollector()
        logger.info("Metrics reset")
        return {"message": "Metrics reset successfully"}
    
    return router 