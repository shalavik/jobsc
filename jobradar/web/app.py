"""Web dashboard for JobRadar."""
from flask import Flask, render_template, jsonify, request
from ..database import Database
from ..models import Job
from ..smart_matcher import create_smart_matcher
import logging
import functools
from datetime import datetime, timedelta
import time

app = Flask(__name__, template_folder='templates', static_folder='static')
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
        
        # Smart matching filter
        smart_match = request.args.get('smart_match')
        
        # Pagination
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        offset = (page - 1) * per_page
        
        # Get total count for pagination
        total_count = db.count_jobs(filters)
        
        # Get jobs from database with pagination
        jobs = db.search_jobs(filters=filters, limit=per_page * 2, offset=offset)  # Get extra for smart filtering
        
        # Apply smart matching if requested
        if smart_match and smart_match.lower() == 'true':
            smart_matcher = create_smart_matcher()
            # Convert to Job objects for smart matching
            job_objects = []
            for db_job in jobs:
                job = Job(
                    id=db_job.id,
                    title=db_job.title,
                    company=db_job.company,
                    url=db_job.url,
                    source=db_job.source,
                    date=db_job.date.isoformat() if db_job.date else ""
                )
                # Add additional fields
                for attr in ['description', 'location', 'salary', 'job_type', 'experience_level', 'is_remote']:
                    if hasattr(db_job, attr):
                        setattr(job, attr, getattr(db_job, attr))
                job_objects.append(job)
            
            # Filter using smart matcher
            relevant_jobs = smart_matcher.filter_jobs(job_objects, min_score=1)
            
            # Convert back to database format for consistency
            jobs = []
            for job in relevant_jobs[:per_page]:  # Apply pagination after smart filtering
                # Find the original database job
                db_job = next((j for j in db.search_jobs({'id': job.id}, limit=1)), None)
                if db_job:
                    jobs.append(db_job)
        else:
            jobs = jobs[:per_page]  # Apply normal pagination
        
        # Convert jobs to dictionary format
        job_list = []
        for job in jobs:
            job_dict = {
                'id': job.id,
                'title': job.title,
                'company': job.company,
                'url': job.url,
                'source': job.source,
                'date': job.date.isoformat() if job.date else None,
                'description': getattr(job, 'description', None),
                'location': getattr(job, 'location', None),
                'salary': getattr(job, 'salary', None),
                'job_type': getattr(job, 'job_type', None),
                'experience_level': getattr(job, 'experience_level', None),
                'is_remote': getattr(job, 'is_remote', False)
            }
            job_list.append(job_dict)
        
        return jsonify({
            'jobs': job_list,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
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

@app.route('/api/smart-jobs')
@cached_api(ttl_seconds=60)  # Cache for 60 seconds
def get_smart_jobs():
    """Get jobs using smart title matching."""
    try:
        # Get parameters
        categories = request.args.get('categories', '').split(',') if request.args.get('categories') else None
        min_score = int(request.args.get('min_score', 1))
        limit = int(request.args.get('limit', 20))
        
        # Clean up categories
        if categories:
            categories = [cat.strip() for cat in categories if cat.strip()]
            if not categories:
                categories = None
        
        # Get all jobs from database
        all_jobs = db.search_jobs(filters={}, limit=1000)
        
        if not all_jobs:
            return jsonify({'jobs': [], 'message': 'No jobs found in database'})
        
        # Convert to Job objects
        job_objects = []
        for db_job in all_jobs:
            job = Job(
                id=db_job.id,
                title=db_job.title,
                company=db_job.company,
                url=db_job.url,
                source=db_job.source,
                date=db_job.date.isoformat() if db_job.date else ""
            )
            # Add additional fields
            for attr in ['description', 'location', 'salary', 'job_type', 'experience_level', 'is_remote']:
                if hasattr(db_job, attr):
                    setattr(job, attr, getattr(db_job, attr))
            job_objects.append(job)
        
        # Apply smart filtering
        smart_matcher = create_smart_matcher()
        if categories:
            # Validate categories
            valid_categories = list(smart_matcher.INTERESTED_KEYWORDS.keys())
            invalid_categories = [cat for cat in categories if cat not in valid_categories]
            if invalid_categories:
                return jsonify({
                    'error': f'Invalid categories: {invalid_categories}',
                    'valid_categories': valid_categories
                }), 400
            
            relevant_jobs = smart_matcher.search_jobs_by_interest(job_objects, categories)
        else:
            relevant_jobs = smart_matcher.filter_jobs(job_objects, min_score)
        
        # Limit results
        relevant_jobs = relevant_jobs[:limit]
        
        # Convert to response format
        job_list = []
        category_counts = {}
        
        for job in relevant_jobs:
            # Get matching keywords and scores
            keywords = smart_matcher.get_matching_keywords(job)
            scores = smart_matcher.get_match_score(job)
            
            # Count categories
            for category, score in scores.items():
                if score > 0:
                    category_counts[category] = category_counts.get(category, 0) + 1
            
            job_dict = {
                'id': job.id,
                'title': job.title,
                'company': job.company,
                'url': job.url,
                'source': job.source,
                'date': job.date if job.date else None,
                'description': getattr(job, 'description', None),
                'location': getattr(job, 'location', None),
                'salary': getattr(job, 'salary', None),
                'job_type': getattr(job, 'job_type', None),
                'experience_level': getattr(job, 'experience_level', None),
                'is_remote': getattr(job, 'is_remote', False),
                'matching_keywords': keywords,
                'category_scores': scores
            }
            job_list.append(job_dict)
        
        return jsonify({
            'jobs': job_list,
            'category_breakdown': category_counts,
            'total_found': len(relevant_jobs),
            'search_params': {
                'categories': categories,
                'min_score': min_score,
                'limit': limit
            }
        })
        
    except Exception as e:
        logger.error(f"Error in smart job search: {str(e)}")
        return jsonify({'error': 'Failed to perform smart job search'}), 500

def run_server(host='0.0.0.0', port=5000, debug=False):
    """Run the Flask development server."""
    app.run(host=host, port=port, debug=debug) 