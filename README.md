# JobRadar

A Python-based job delivery application that aggregates job listings from multiple sources and provides intelligent filtering and delivery interfaces.

## Features

- **Multi-source job fetching**: RSS feeds, JSON APIs, HTML scraping, and headless browser automation
- **Smart job matching**: AI-powered job relevance scoring and filtering
- **Multiple delivery interfaces**: CLI commands and web dashboard
- **Advanced filtering**: Company, location, salary, experience level, and custom filters
- **Database storage**: SQLite with efficient job management and deduplication
- **Rate limiting**: Configurable rate limiting for respectful data collection
- **Proxy support**: Rotation and geographic targeting for challenging sources

## Architecture

JobRadar follows a modular architecture for maintainability and scalability:

### Core Components

- **`jobradar.fetchers`**: Modular job fetching system
  - `base_fetcher.py`: Core Fetcher class with RSS, JSON, and HTML support
  - `browser_pool.py`: Browser context management for headless fetching
  - `parsers.py`: Site-specific HTML parsers for various job boards
  - `headless.py`: Advanced headless browser automation with security challenge handling
- **`jobradar.models`**: Data models (Job, Feed) with proper validation
- **`jobradar.database`**: SQLite database operations with connection pooling
- **`jobradar.smart_matcher`**: AI-based job relevance scoring and filtering
- **`jobradar.web`**: Flask-based web dashboard with REST API
- **`jobradar.cli`**: Command-line interface for all operations

### Delivery Interfaces

1. **CLI Interface**: Command-line tools for fetching, searching, and managing jobs
2. **Web Dashboard**: Modern web interface with filtering and job browsing

### Smart Matching System

The smart matcher uses keyword-based scoring to identify relevant jobs across categories:
- Customer Support & Service
- Technical Support & Engineering
- Specialist Roles & Analysis
- Compliance & Analysis
- Operations & Management

## Installation

```bash
# Clone the repository
git clone <repository_url>
cd jobsc

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
python -m jobradar.cli migrate
```

## Usage Examples

### CLI Commands

```bash
# Fetch jobs from all configured sources
python -m jobradar.cli fetch

# Fetch from specific source with smart filtering
python -m jobradar.cli fetch --feed "RemoteOK" --smart --min-score 2

# Search jobs with filters
python -m jobradar.cli search --title "engineer" --remote --limit 20

# Smart search by categories
python -m jobradar.cli smart-search --categories "customer_support,technical_support" --min-score 2

# Start web dashboard
python -m jobradar.cli web --host 0.0.0.0 --port 8082
```

### Web Dashboard

Access the web interface at `http://localhost:8082` for:
- Browse jobs with real-time filtering
- Smart matching with category selection
- Export job lists
- View job statistics and analytics

### API Endpoints

- `GET /api/jobs` - Get jobs with filtering and pagination
- `GET /api/filters` - Get available filter options
- `GET /api/smart-jobs` - Get smart-filtered jobs by category

## Configuration

Configure job sources in `config.yaml`:

```yaml
feeds:
  - name: "RemoteOK"
    url: "https://remoteok.io/remote-jobs"
    type: "html"
    parser: "remoteok"
    fetch_method: "headless"
    rate_limit:
      requests_per_minute: 10

smart_filtering:
  enabled: true
  min_score: 1
  categories:
    - "customer_support"
    - "technical_support"

filters:
  exclude_companies:
    - "spam-company"
  min_salary: 50000
```

## Development

### Code Standards

This project follows strict Python best practices as defined in `.cursorrules`:

- **PEP 8 compliance**: All code follows Python style guidelines
- **Type hints**: All functions include proper type annotations
- **Modular architecture**: Clear separation between fetchers, delivery, and smart matching
- **Comprehensive testing**: TDD approach with pytest
- **Documentation**: Detailed docstrings following PEP 257

### Running Tests

```bash
# Run all tests
pytest

# Run specific test modules
pytest tests/test_fetchers_module.py -v

# Run with coverage
pytest --cov=jobradar
```

### Architecture Guidelines

- **Fetchers**: Data collection modules for different sources
- **Delivery**: CLI and web interfaces for user interaction
- **Smart Matching**: AI-based job filtering and relevance scoring
- **Separation of Concerns**: Clear boundaries between components
- **Error Handling**: Graceful handling with proper logging
- **Rate Limiting**: Respectful data collection practices

### Adding New Job Sources

1. Create a parser in `jobradar/fetchers/parsers.py`
2. Add configuration in `config.yaml`
3. Write tests in `tests/`
4. Update documentation

### Modular Fetcher System

The fetcher system is organized into focused modules:

```python
from jobradar.fetchers import Fetcher, BrowserPool  # Main interfaces
from jobradar.fetchers.base_fetcher import Fetcher  # Core functionality
from jobradar.fetchers.parsers import HTMLParsers   # Site-specific parsing
from jobradar.fetchers.headless import HeadlessFetcher  # Browser automation
```

## Supported Job Sources

- **RemoteOK**: Remote job listings with skill tags
- **Indeed**: Large job board with advanced search
- **LinkedIn**: Professional network jobs (limited access)
- **WorkingNomads**: Curated remote positions
- **Remotive**: Remote tech jobs with filtering
- **Snaphunt**: Global job marketplace
- **Various RSS feeds**: Automated job feed processing

## Database Schema

Jobs are stored with comprehensive metadata:
- Basic info: title, company, URL, source
- Details: location, salary, job type, experience level
- Metadata: posting date, remote status, skills
- Relevance: smart match scores and categories

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all tests pass
5. Follow the code standards in `.cursorrules`
6. Submit a pull request

## License

[Insert your license information here]

## Support

For issues and questions:
- Check the GitHub issues
- Review the configuration examples
- Ensure proper environment setup