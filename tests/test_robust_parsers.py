"""Data-driven tests for robust HTML parsers."""
import pytest
from unittest.mock import Mock, patch
from jobradar.fetchers import Fetcher
from jobradar.models import Feed, Job
from bs4 import BeautifulSoup

@pytest.fixture
def fetcher():
    """Create a fetcher instance for testing."""
    return Fetcher()

@pytest.fixture
def remoteok_feed():
    """Create a RemoteOK feed configuration."""
    return Feed(
        name="remoteok",
        url="https://remoteok.io/jobs",
        type="html",
        parser="remoteok",
        fetch_method="html",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )

# Test data for _parse_remoteok with different HTML structures
remoteok_test_data = [
    # Standard structure
    {
        'html': """
        <tr class="job" data-id="123">
            <h2 itemprop="title">Python Developer</h2>
            <h3 itemprop="name">Test Company</h3>
        </tr>
        """,
        'expected': {
            'count': 1,
            'title': "Python Developer",
            'company': "Test Company",
        }
    },
    # Alternative structure
    {
        'html': """
        <div class="job">
            <div class="position">Python Developer</div>
            <div class="company">Test Company</div>
        </div>
        """,
        'expected': {
            'count': 1,
            'title': "Python Developer",
            'company': "Test Company",
        }
    },
    # Multiple jobs
    {
        'html': """
        <tr class="job" data-id="123">
            <h2 itemprop="title">Python Developer</h2>
            <h3 itemprop="name">Company A</h3>
        </tr>
        <tr class="job" data-id="456">
            <h2 itemprop="title">JavaScript Developer</h2>
            <h3 itemprop="name">Company B</h3>
        </tr>
        """,
        'expected': {
            'count': 2,
            'titles': ["Python Developer", "JavaScript Developer"],
            'companies': ["Company A", "Company B"],
        }
    },
    # Missing company name
    {
        'html': """
        <tr class="job" data-id="123">
            <h2 itemprop="title">Python Developer</h2>
            <!-- No company name -->
        </tr>
        """,
        'expected': {
            'count': 1,
            'title': "Python Developer",
            'company': "Unknown Company",  # Should use fallback
        }
    },
    # Empty response
    {
        'html': """<div></div>""",
        'expected': {
            'count': 0,
        }
    }
]

@pytest.mark.parametrize("test_case", remoteok_test_data)
def test_parse_remoteok(fetcher, remoteok_feed, test_case):
    """Test parsing RemoteOK with different HTML structures."""
    soup = BeautifulSoup(test_case['html'], 'lxml')
    jobs = fetcher._parse_remoteok(soup, remoteok_feed)
    
    assert len(jobs) == test_case['expected']['count']
    
    if test_case['expected']['count'] == 0:
        return
    
    if 'titles' in test_case['expected']:
        # Test multiple jobs
        assert [job.title for job in jobs] == test_case['expected']['titles']
        assert [job.company for job in jobs] == test_case['expected']['companies']
    else:
        # Test single job
        assert jobs[0].title == test_case['expected']['title']
        assert jobs[0].company == test_case['expected']['company']

@pytest.fixture
def remotive_feed():
    """Create a Remotive feed configuration."""
    return Feed(
        name="remotive",
        url="https://remotive.com/jobs",
        type="html",
        parser="remotive",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )

# Test data for _parse_remotive with different HTML structures
remotive_test_data = [
    # Standard structure
    {
        'html': """
        <div class="job-card">
            <h2 class="job-title">Python Developer</h2>
            <div class="company-name">Test Company</div>
            <a class="job-link" href="/jobs/123">View Job</a>
        </div>
        """,
        'expected': {
            'count': 1,
            'title': "Python Developer",
            'company': "Test Company",
        }
    },
    # Alternative structure
    {
        'html': """
        <li class="job-li">
            <div class="position">Python Developer</div>
            <span class="company">Test Company</span>
            <a href="/jobs/123">View</a>
        </li>
        """,
        'expected': {
            'count': 1,
            'title': "Python Developer",
            'company': "Test Company",
        }
    },
    # "at Company" text pattern
    {
        'html': """
        <div class="job">
            <h3>Python Developer at Awesome Company</h3>
            <a href="/jobs/123">View</a>
        </div>
        """,
        'expected': {
            'count': 1,
            'title': "Python Developer at Awesome Company",
            'company': "Awesome Company",  # Should extract from title
        }
    },
    # CAPTCHA/block detection
    {
        'html': """
        <div>
            <h1>Security Check</h1>
            <p>Please complete this captcha to continue</p>
        </div>
        """,
        'expected': {
            'count': 0,
            'captcha': True
        }
    },
    # Empty response with generic extraction attempt
    {
        'html': """
        <section class="job-section">
            <h2>Python Developer</h2>
            <span>Company XYZ</span>
            <a href="/jobs/123">View</a>
        </section>
        """,
        'expected': {
            'count': 1,
            'title': "Python Developer",
            'company': "Company XYZ",
        }
    }
]

@pytest.mark.parametrize("test_case", remotive_test_data)
def test_parse_remotive(fetcher, remotive_feed, test_case, monkeypatch):
    """Test parsing Remotive with different HTML structures."""
    # Patch the logger to capture warning messages about CAPTCHA
    mock_logger = Mock()
    monkeypatch.setattr('jobradar.fetchers.logger', mock_logger)
    
    soup = BeautifulSoup(test_case['html'], 'lxml')
    jobs = fetcher._parse_remotive(soup, remotive_feed)
    
    assert len(jobs) == test_case['expected']['count']
    
    if test_case['expected'].get('captcha', False):
        # Verify CAPTCHA warning was logged
        mock_logger.warning.assert_called_once_with("Remotive is showing a block or CAPTCHA page")
    
    if test_case['expected']['count'] == 0:
        return
        
    assert jobs[0].title == test_case['expected']['title']
    assert jobs[0].company == test_case['expected']['company']

# Test data structure for multiple parsers
multi_parser_test_data = [
    {
        'parser': 'snaphunt',
        'html': """
        <div class="job-card">
            <h3 class="job-title">Python Developer</h3>
            <div class="company-name">Test Company</div>
            <a class="job-link" href="/jobs/123">View Job</a>
        </div>
        """,
        'expected': {
            'title': "Python Developer",
            'company': "Test Company",
        }
    },
    {
        'parser': 'nodesk',
        'html': """
        <div class="job-card">
            <h2 class="job-title">Python Developer</h2>
            <div class="company-name">Test Company</div>
            <a class="job-link" href="/jobs/123">View Job</a>
        </div>
        """,
        'expected': {
            'title': "Python Developer",
            'company': "Test Company",
        }
    },
    {
        'parser': 'cryptojobslist',
        'html': """
        <div class="job-card">
            <h2 class="job-title">Python Developer</h2>
            <div class="company-name">Test Company</div>
            <a class="job-link" href="/jobs/123">View Job</a>
        </div>
        """,
        'expected': {
            'title': "Python Developer",
            'company': "Test Company",
        }
    },
    {
        'parser': 'jobspresso',
        'html': """
        <div class="job-card">
            <h2 class="job-title">Python Developer</h2>
            <div class="company-name">Test Company</div>
            <a class="job-link" href="/jobs/123">View Job</a>
        </div>
        """,
        'expected': {
            'title': "Python Developer",
            'company': "Test Company",
        }
    }
]

@pytest.mark.parametrize("test_case", multi_parser_test_data)
def test_multiple_parsers(fetcher, test_case):
    """Test multiple parsers with their HTML structures."""
    parser_name = test_case['parser']
    feed = Feed(
        name=parser_name,
        url=f"https://{parser_name}.com/jobs",
        type="html",
        parser=parser_name,
        fetch_method="html",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    soup = BeautifulSoup(test_case['html'], 'lxml')
    
    # Get the parse method dynamically
    parser_method = getattr(fetcher, f"_parse_{parser_name}")
    jobs = parser_method(soup, feed)
    
    assert len(jobs) == 1
    assert jobs[0].title == test_case['expected']['title']
    assert jobs[0].company == test_case['expected']['company']

# Test data for missing elements but robust enough to still extract
robust_parsing_test_data = [
    {
        'parser': 'remoteok',
        'html': """
        <tr class="job">
            <h2 itemprop="title">Python Developer</h2>
            <!-- No company -->
            <a href="/jobs/123">Link</a>
        </tr>
        """,
        'expected': {
            'count': 1,
            'title': "Python Developer",
            'company': "Unknown Company",
        }
    },
    {
        'parser': 'remotive',
        'html': """
        <div class="job-card">
            <h2 class="job-title">Python Developer</h2>
            <!-- No company name, no link -->
        </div>
        """,
        'expected': {
            'count': 1,
            'title': "Python Developer",
            'company': "Unknown Company",
        }
    },
    {
        'parser': 'nodesk_substack',
        'html': """
        <article class="post">
            <h3>Python Developer at Amazing Company</h3>
            <a href="/p/123">Read More</a>
        </article>
        """,
        'expected': {
            'count': 1,
            'title': "Python Developer at Amazing Company",
            'company': "Amazing Company",  # Should extract company from title
        }
    }
]

@pytest.mark.parametrize("test_case", robust_parsing_test_data)
def test_robust_parsing(fetcher, test_case):
    """Test that parsers can extract data even from incomplete HTML."""
    parser_name = test_case['parser']
    feed = Feed(
        name=parser_name,
        url=f"https://{parser_name}.com/jobs",
        type="html",
        parser=parser_name,
        fetch_method="html",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    soup = BeautifulSoup(test_case['html'], 'lxml')
    
    # Get the parse method dynamically
    parser_method = getattr(fetcher, f"_parse_{parser_name}")
    jobs = parser_method(soup, feed)
    
    assert len(jobs) == test_case['expected']['count']
    if test_case['expected']['count'] > 0:
        assert jobs[0].title == test_case['expected']['title']
        assert jobs[0].company == test_case['expected']['company']

# Test alternative selectors when primary ones fail
alternative_selectors_test_data = [
    {
        'parser': 'remoteok',
        'primary_html': """<div></div>""",  # Empty primary structure
        'alternative_html': """
        <article class="job">
            <div class="position">Python Developer</div>
            <span class="company">Test Company</span>
        </article>
        """,
        'expected': {
            'count': 1,
            'title': "Python Developer",
            'company': "Test Company",
        }
    },
    {
        'parser': 'remotive',
        'primary_html': """<div></div>""",  # Empty primary structure
        'alternative_html': """
        <div class="ce">
            <h3>Python Developer</h3>
            <div class="company">Test Company</div>
            <a href="/jobs/123">View Job</a>
        </div>
        """,
        'expected': {
            'count': 1,
            'title': "Python Developer",
            'company': "Test Company",
        }
    }
]

@pytest.mark.parametrize("test_case", alternative_selectors_test_data)
def test_alternative_selectors(fetcher, test_case, monkeypatch):
    """Test that parsers try alternative selectors when primary ones fail."""
    parser_name = test_case['parser']
    feed = Feed(
        name=parser_name,
        url=f"https://{parser_name}.com/jobs",
        type="html",
        parser=parser_name,
        fetch_method="html",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    # First try with primary HTML that won't match the main selector
    primary_soup = BeautifulSoup(test_case['primary_html'], 'lxml')
    
    # Patch find_all to return empty for primary selector then alternative HTML for secondary selector
    def mock_find_all(tag, **kwargs):
        if 'class_' in kwargs and kwargs['class_'] == 'job-card':
            # Primary selector, return empty
            return []
        else:
            # Secondary selector, return alternative HTML
            return BeautifulSoup(test_case['alternative_html'], 'lxml').find_all(tag, **kwargs)
    
    primary_soup.find_all = mock_find_all
    
    # Get the parse method dynamically
    parser_method = getattr(fetcher, f"_parse_{parser_name}")
    jobs = parser_method(primary_soup, feed)
    
    assert len(jobs) == test_case['expected']['count']
    if test_case['expected']['count'] > 0:
        assert jobs[0].title == test_case['expected']['title']
        assert jobs[0].company == test_case['expected']['company'] 