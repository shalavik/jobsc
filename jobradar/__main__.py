import logging
import time
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn
from jobradar.domain.matching import create_smart_matcher
from jobradar.delivery.web.db_handler import DatabaseWebHandler
from jobradar.delivery.notifiers.email import EmailNotifier
from jobradar.delivery.web.metrics import create_metrics_router, metrics

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jobradar")

class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to track response times and other metrics."""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Record response time
        metrics.record_response_time(process_time)
        
        # Add response time header
        response.headers["X-Process-Time"] = str(process_time)
        
        return response

def create_app() -> FastAPI:
    """Create and configure the FastAPI app."""
    app = FastAPI(
        title="JobRadar API", 
        version="1.0",
        description="Job aggregation and matching API with performance monitoring"
    )

    # Add metrics middleware
    app.add_middleware(MetricsMiddleware)

    # Set up smart matcher (customize categories as needed)
    matcher = create_smart_matcher([
        "customer_support",
        "technical_support",
        "compliance_analyst",
        "marketing"
    ])

    # Set up database-backed web handler
    DatabaseWebHandler(app, matcher)

    # Include metrics router
    metrics_router = create_metrics_router()
    app.include_router(metrics_router)

    # Example: Set up email notifier (not triggered on startup)
    # email_notifier = EmailNotifier({
    #     'smtp_host': 'smtp.gmail.com',
    #     'smtp_port': 587,
    #     'smtp_user': 'your_email',
    #     'smtp_password': 'your_password',
    #     'recipient': 'recipient_email'
    # })

    # Extension point: Add background job fetching, notification triggers, etc.
    # e.g., use FastAPI background tasks or APScheduler

    @app.on_event("startup")
    async def startup_event():
        """Application startup event."""
        logger.info("JobRadar API starting up...")
        logger.info("Metrics available at /metrics")
        logger.info("Health check available at /metrics/health")
        logger.info("API documentation available at /docs")

    return app

if __name__ == "__main__":
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000) 