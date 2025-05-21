"""Web dashboard for JobRadar."""
from flask import Flask, render_template, jsonify, request
from ..database import Database
from ..models import Job
import logging

app = Flask(__name__)
db = Database()
logger = logging.getLogger(__name__)

@app.route('/')
def index():
    """Render the main dashboard page."""
    return render_template('index.html')

@app.route('/api/jobs')
def get_jobs():
    """Get jobs with optional filtering."""
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
        
        # Get jobs from database
        jobs = db.search_jobs(filters=filters)
        
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
                'is_remote': getattr(job, 'is_remote', False)
            }
            job_list.append(job_dict)
        
        return jsonify({'jobs': job_list})
    except Exception as e:
        logger.error(f"Error in /api/jobs: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/filters')
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