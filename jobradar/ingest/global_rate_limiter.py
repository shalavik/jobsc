"""Global rate limiter with token bucket and exponential backoff."""
import asyncio
import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class BackoffStrategy(Enum):
    """Backoff strategies for rate limiting."""
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    FIBONACCI = "fibonacci"

@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    max_tokens: int = 100
    refill_rate: float = 10.0  # tokens per second
    initial_backoff: float = 1.0  # seconds
    max_backoff: float = 300.0  # 5 minutes max
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    backoff_multiplier: float = 2.0

class TokenBucket:
    """Token bucket implementation for rate limiting."""
    
    def __init__(self, config: RateLimitConfig):
        """Initialize token bucket.
        
        Args:
            config: Rate limit configuration
        """
        self.config = config
        self.tokens = float(config.max_tokens)
        self.last_refill = time.time()
        self.consecutive_failures = 0
        self.last_failure_time = 0.0
        
    def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        
        # Add tokens based on refill rate
        tokens_to_add = elapsed * self.config.refill_rate
        self.tokens = min(self.config.max_tokens, self.tokens + tokens_to_add)
        self.last_refill = now
        
    def can_consume(self, tokens: int = 1) -> bool:
        """Check if we can consume tokens without actually consuming them.
        
        Args:
            tokens: Number of tokens to check for
            
        Returns:
            True if tokens are available
        """
        self._refill_tokens()
        return self.tokens >= tokens
        
    def consume(self, tokens: int = 1) -> bool:
        """Attempt to consume tokens.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were consumed successfully
        """
        self._refill_tokens()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
        
    def get_wait_time(self, tokens: int = 1) -> float:
        """Get time to wait before tokens are available.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            Time to wait in seconds
        """
        self._refill_tokens()
        
        if self.tokens >= tokens:
            return 0.0
            
        tokens_needed = tokens - self.tokens
        return tokens_needed / self.config.refill_rate
        
    def record_failure(self) -> None:
        """Record a failure for backoff calculation."""
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        
    def record_success(self) -> None:
        """Record a success, resetting failure count."""
        self.consecutive_failures = 0
        
    def get_backoff_time(self) -> float:
        """Calculate backoff time based on consecutive failures.
        
        Returns:
            Time to wait in seconds
        """
        if self.consecutive_failures == 0:
            return 0.0
            
        base_backoff = self.config.initial_backoff
        
        if self.config.backoff_strategy == BackoffStrategy.LINEAR:
            backoff = base_backoff * self.consecutive_failures
        elif self.config.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            backoff = base_backoff * (self.config.backoff_multiplier ** (self.consecutive_failures - 1))
        elif self.config.backoff_strategy == BackoffStrategy.FIBONACCI:
            # Simple fibonacci sequence for backoff
            fib_a, fib_b = 1, 1
            for _ in range(self.consecutive_failures - 1):
                fib_a, fib_b = fib_b, fib_a + fib_b
            backoff = base_backoff * fib_b
        else:
            backoff = base_backoff
            
        return min(backoff, self.config.max_backoff)

class GlobalRateLimiter:
    """Global rate limiter managing multiple sources."""
    
    def __init__(self):
        """Initialize global rate limiter."""
        self.buckets: Dict[str, TokenBucket] = {}
        self.global_bucket = TokenBucket(RateLimitConfig(
            max_tokens=50,
            refill_rate=5.0,  # Conservative global rate
            initial_backoff=2.0,
            max_backoff=600.0  # 10 minutes max
        ))
        
    def get_bucket(self, source: str, config: Optional[RateLimitConfig] = None) -> TokenBucket:
        """Get or create a token bucket for a source.
        
        Args:
            source: Source identifier
            config: Optional custom configuration
            
        Returns:
            Token bucket for the source
        """
        if source not in self.buckets:
            if config is None:
                config = RateLimitConfig()
            self.buckets[source] = TokenBucket(config)
        return self.buckets[source]
        
    async def acquire(self, source: str, tokens: int = 1, config: Optional[RateLimitConfig] = None) -> bool:
        """Acquire tokens for a request.
        
        Args:
            source: Source identifier
            tokens: Number of tokens to acquire
            config: Optional custom configuration
            
        Returns:
            True if tokens were acquired
        """
        source_bucket = self.get_bucket(source, config)
        
        # Check both source-specific and global limits
        source_wait = source_bucket.get_wait_time(tokens)
        global_wait = self.global_bucket.get_wait_time(tokens)
        source_backoff = source_bucket.get_backoff_time()
        global_backoff = self.global_bucket.get_backoff_time()
        
        # Use the maximum wait time
        total_wait = max(source_wait, global_wait, source_backoff, global_backoff)
        
        if total_wait > 0:
            logger.info(f"Rate limiting {source}: waiting {total_wait:.2f}s")
            await asyncio.sleep(total_wait)
            
        # Try to consume tokens
        source_success = source_bucket.consume(tokens)
        global_success = self.global_bucket.consume(tokens)
        
        success = source_success and global_success
        
        if success:
            source_bucket.record_success()
            self.global_bucket.record_success()
        else:
            source_bucket.record_failure()
            self.global_bucket.record_failure()
            
        return success
        
    def record_error(self, source: str, error_type: str = "generic") -> None:
        """Record an error for backoff calculation.
        
        Args:
            source: Source identifier
            error_type: Type of error (for future use)
        """
        # Ensure bucket exists
        source_bucket = self.get_bucket(source)
        source_bucket.record_failure()
        self.global_bucket.record_failure()
        
        logger.warning(f"Recorded error for {source}: {error_type}")

# Global instance
global_rate_limiter = GlobalRateLimiter() 