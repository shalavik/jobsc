"""Web dashboard for JobRadar."""
from flask import Flask, render_template, jsonify, request
from ..database import Database
from ..models import Job
import logging
import functools
from datetime import datetime, timedelta

app = Flask(__name__)
db = Database()
logger = logging.getLogger(__name__)

# Simple in-memory cache
api_cache = {}
CACHE_TTL = 60  # seconds

def cached_api(ttl_seconds=CACHE_TTL):
    """Cache API responses to improve performance."""
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # Create a cache key from request args
            key = request.path + str(request.args)
            
            # Check if result is in cache and not expired
            if key in api_cache:
                result, timestamp = api_cache[key]
                if (datetime.now() - timestamp).total_seconds() < ttl_seconds:
                    return result
            
            # Get fresh result
            result = f(*args, **kwargs)
            api_cache[key] = (result, datetime.now())
            return result
        return decorated_function
    return decorator

@app.route('/')
def index():
    """Render the main dashboard page."""
    return render_template('index.html')

@app.route('/api/jobs')
@cached_api(ttl_seconds=30)  # Cache for 30 seconds
def get_jobs():
    """Get jobs with optional filtering and pagination."""
    try:
        # Get filter parameters
        filters = {}
        
        # Text-based filters
        for field in ['title', 'company', 'source', 'location', 'job_type', 'experience_level']:
            value = request.args.get(field)
            if value:
                filters[field] = value
        
        # Boolean filters
        remote = request.args.get('remote')
        if remote is not None:
            filters['is_remote'] = remote.lower() == 'true'
        
        # Numeric filters
        salary_min = request.args.get('salary-min')
        if salary_min:
            filters['salary_min'] = int(salary_min) * 1000  # Convert to actual salary
        
        salary_max = request.args.get('salary-max')
        if salary_max:
            filters['salary_max'] = int(salary_max) * 1000  # Convert to actual salary
        
        # Pagination
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        offset = (page - 1) * per_page
        
        # Get total count for pagination
        total_count = db.count_jobs(filters)
        
        # Get jobs from database with pagination
        jobs = db.search_jobs(filters=filters, limit=per_page, offset=offset)
        
        # Convert jobs to dictionary format
        job_list = []
        for job in jobs:
            job_dict = {
                'id': job.id,
                'title': job.title,
                'company': job.company,
                'url': job.url,
                'source': job.source,
                'location': getattr(job, 'location', None),
                'salary': getattr(job, 'salary', None),
                'job_type': getattr(job, 'job_type', None),
                'experience_level': getattr(job, 'experience_level', None),
                'is_remote': getattr(job, 'is_remote', False),
                'date': job.date.isoformat() if job.date else None,
            }
            job_list.append(job_dict)
        
        return jsonify({
            'jobs': job_list,
            'pagination': {
                'total': total_count,
                'page': page,
                'per_page': per_page,
                'pages': (total_count + per_page - 1) // per_page
            }
        })
    except Exception as e:
        logger.error(f"Error in /api/jobs: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/filters')
@cached_api(ttl_seconds=300)  # Cache for 5 minutes
def get_filters():
    """Get available filter options."""
    try:
        # Get unique values from database
        job_types = db.get_unique_values('job_type')
        experience_levels = db.get_unique_values('experience_level')
        sources = db.get_unique_values('source')
        
        return jsonify({
            'job_types': job_types,
            'experience_levels': experience_levels,
            'sources': sources
        })
    except Exception as e:
        logger.error(f"Error in /api/filters: {e}")
        return jsonify({'error': str(e)}), 500

def run_server(host='0.0.0.0', port=5000, debug=False):
    """Run the Flask development server."""
    app.run(host=host, port=port, debug=debug) 