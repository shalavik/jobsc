"""Tests for metrics endpoint functionality."""
import pytest
from fastapi.testclient import TestClient
from jobradar.__main__ import create_app
from jobradar.delivery.web.metrics import metrics, MetricsCollector

class TestMetricsEndpoint:
    """Test metrics endpoint functionality."""
    
    @pytest.fixture
    def client(self):
        """Create test client with fresh metrics."""
        # Reset metrics for clean test state
        global metrics
        metrics.__dict__.update(MetricsCollector().__dict__)
        
        app = create_app()
        return TestClient(app)
    
    def test_metrics_endpoint_returns_structure(self, client):
        """Test that metrics endpoint returns expected structure."""
        response = client.get("/metrics/")
        assert response.status_code == 200
        
        data = response.json()
        
        # Check main sections exist
        assert "jobs" in data
        assert "errors" in data
        assert "rate_limiting" in data
        assert "performance" in data
        assert "success_rates" in data
        
        # Check job metrics structure
        assert "fetched_total" in data["jobs"]
        assert "fetched_by_source" in data["jobs"]
        assert "duplicates_found" in data["jobs"]
        assert "duplicates_removed" in data["jobs"]
        assert "expired_removed" in data["jobs"]
        
        # Check error metrics structure
        assert "fetch_errors_total" in data["errors"]
        assert "fetch_errors_by_source" in data["errors"]
        assert "fetch_errors_by_type" in data["errors"]
    
    def test_health_endpoint_returns_status(self, client):
        """Test health endpoint returns status information."""
        response = client.get("/metrics/health")
        assert response.status_code == 200
        
        data = response.json()
        
        # Check required fields
        assert "status" in data
        assert "uptime_seconds" in data
        assert "success_rate_percent" in data
        assert "average_response_time_ms" in data
        assert "jobs_fetched_total" in data
        assert "errors_total" in data
        
        # Initial state should be healthy
        assert data["status"] == "healthy"
        assert data["success_rate_percent"] == 100.0
    
    def test_source_metrics_endpoint(self, client):
        """Test source-specific metrics endpoint."""
        response = client.get("/metrics/sources")
        assert response.status_code == 200
        
        data = response.json()
        # Should be empty dict initially
        assert isinstance(data, dict)
    
    def test_metrics_tracking_with_simulated_data(self, client):
        """Test that metrics correctly track simulated job fetching."""
        # Simulate some job fetches
        metrics.record_job_fetched("linkedin", 5)
        metrics.record_job_fetched("indeed", 3)
        
        # Simulate some errors
        metrics.record_fetch_error("linkedin", "timeout")
        metrics.record_fetch_error("indeed", "rate_limit")
        
        # Simulate rate limiting
        metrics.record_rate_limit_hit("linkedin")
        
        # Simulate duplicates
        metrics.record_duplicates_found(2)
        metrics.record_duplicates_removed(1)
        
        # Get metrics
        response = client.get("/metrics/")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify job counts
        assert data["jobs"]["fetched_total"] == 8
        assert data["jobs"]["fetched_by_source"]["linkedin"] == 5
        assert data["jobs"]["fetched_by_source"]["indeed"] == 3
        assert data["jobs"]["duplicates_found"] == 2
        assert data["jobs"]["duplicates_removed"] == 1
        
        # Verify error counts
        assert data["errors"]["fetch_errors_total"] == 2
        assert data["errors"]["fetch_errors_by_source"]["linkedin"] == 1
        assert data["errors"]["fetch_errors_by_source"]["indeed"] == 1
        assert data["errors"]["fetch_errors_by_type"]["timeout"] == 1
        assert data["errors"]["fetch_errors_by_type"]["rate_limit"] == 1
        
        # Verify rate limiting
        assert data["rate_limiting"]["rate_limit_hits"] == 1
        assert data["rate_limiting"]["rate_limit_hits_by_source"]["linkedin"] == 1
        
        # Verify success rates
        # LinkedIn: 5 fetched, 1 error = 5/6 = 83.33%
        linkedin_success_rate = data["success_rates"]["by_source"]["linkedin"]
        assert abs(linkedin_success_rate - 83.33) < 0.1
        
        # Indeed: 3 fetched, 1 error = 3/4 = 75%
        indeed_success_rate = data["success_rates"]["by_source"]["indeed"]
        assert abs(indeed_success_rate - 75.0) < 0.1
        
        # Overall: 8 fetched, 2 errors = 8/10 = 80%
        overall_success_rate = data["success_rates"]["overall"]
        assert abs(overall_success_rate - 80.0) < 0.1
    
    def test_health_status_changes_with_poor_metrics(self, client):
        """Test that health status changes based on success rate."""
        # Simulate poor performance
        metrics.record_fetch_error("test_source", "timeout")
        metrics.record_fetch_error("test_source", "timeout")
        metrics.record_fetch_error("test_source", "timeout")
        # Only 1 success out of 4 attempts = 25% success rate
        metrics.record_job_fetched("test_source", 1)
        
        response = client.get("/metrics/health")
        assert response.status_code == 200
        
        data = response.json()
        
        # Should be unhealthy due to low success rate
        assert data["status"] == "unhealthy"
        assert data["success_rate_percent"] == 25.0
    
    def test_response_time_tracking(self, client):
        """Test that response times are tracked."""
        # Make a request to trigger response time tracking
        response = client.get("/metrics/health")
        assert response.status_code == 200
        
        # Check that response time header is added
        assert "X-Process-Time" in response.headers
        process_time = float(response.headers["X-Process-Time"])
        assert process_time > 0
        
        # Get metrics to verify response time was recorded
        response = client.get("/metrics/")
        data = response.json()
        
        # Should have recorded response times
        assert data["performance"]["average_response_time_ms"] > 0
    
    def test_metrics_reset(self, client):
        """Test metrics reset functionality."""
        # Add some data
        metrics.record_job_fetched("test", 5)
        metrics.record_fetch_error("test", "error")
        
        # Verify data exists
        response = client.get("/metrics/")
        data = response.json()
        assert data["jobs"]["fetched_total"] == 5
        assert data["errors"]["fetch_errors_total"] == 1
        
        # Reset metrics
        response = client.post("/metrics/reset")
        assert response.status_code == 200
        assert response.json()["message"] == "Metrics reset successfully"
        
        # Verify data is reset
        response = client.get("/metrics/")
        data = response.json()
        assert data["jobs"]["fetched_total"] == 0
        assert data["errors"]["fetch_errors_total"] == 0
    
    def test_uptime_tracking(self, client):
        """Test that uptime is tracked correctly."""
        response = client.get("/metrics/health")
        assert response.status_code == 200
        
        data = response.json()
        
        # Uptime should be positive
        assert data["uptime_seconds"] > 0 