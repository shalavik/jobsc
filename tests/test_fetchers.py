"""Tests for the fetcher functionality."""
import pytest
import json
from unittest.mock import Mock, patch
from requests.exceptions import RequestException
from jobradar.fetchers import Fetcher
from jobradar.models import Feed, Job
from bs4 import BeautifulSoup

@pytest.fixture
def fetcher():
    """Create a fetcher instance for testing."""
    return Fetcher()

@pytest.fixture
def rss_feed():
    """Create a sample RSS feed configuration."""
    return Feed(
        name="test_rss",
        url="https://example.com/feed.rss",
        type="rss",
        parser="rss",
        fetch_method="rss",
        rate_limit={
            'requests_per_minute': 2,
            'retry_after': 1
        }
    )

@pytest.fixture
def json_feed():
    """Create a sample JSON feed configuration."""
    return Feed(
        name="test_json",
        url="https://example.com/jobs.json",
        type="json",
        parser="json",
        fetch_method="json",
        rate_limit={
            'requests_per_minute': 2,
            'retry_after': 1
        }
    )

@pytest.fixture
def html_feed():
    """Create a sample HTML feed configuration."""
    return Feed(
        name="test_html",
        url="https://example.com/jobs.html",
        type="html",
        parser="html",
        fetch_method="html",
        rate_limit={
            'requests_per_minute': 2,
            'retry_after': 1
        }
    )

def test_fetch_rss(fetcher, rss_feed):
    """Test fetching from an RSS feed."""
    mock_response = Mock()
    mock_response.text = """
    <?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <item>
                <title>Python Developer</title>
                <link>https://example.com/job1</link>
                <company>Test Company</company>
                <pubDate>2024-01-01</pubDate>
            </item>
        </channel>
    </rss>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(rss_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://example.com/job1"

def test_fetch_json(fetcher, json_feed):
    """Test fetching from a JSON feed."""
    mock_response = Mock()
    mock_response.json.return_value = [{
        'id': '1',
        'title': 'Python Developer',
        'company': 'Test Company',
        'url': 'https://example.com/job1',
        'date': '2024-01-01'
    }]
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(json_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://example.com/job1"

def test_fetch_html_indeed(fetcher):
    """Test fetching from Indeed HTML feed."""
    indeed_feed = Feed(
        name="indeed",
        url="https://www.indeed.com/jobs",
        type="html",
        parser="indeed",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job_seen_beacon" data-jk="123">
        <h2 class="jobTitle">Python Developer</h2>
        <span class="companyName">Test Company</span>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(indeed_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://www.indeed.com/viewjob?jk=123"

def test_fetch_html_remoteok(fetcher):
    """Test fetching from RemoteOK HTML feed."""
    remoteok_feed = Feed(
        name="remoteok",
        url="https://remoteok.io/jobs",
        type="html",
        parser="remoteok",
        fetch_method="html",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <tr class="job" data-id="123">
        <h2 itemprop="title">Python Developer</h2>
        <h3 itemprop="name">Test Company</h3>
    </tr>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(remoteok_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://remoteok.com/remote-jobs/123"

def test_fetch_retry_on_rate_limit(fetcher, rss_feed):
    """Test that fetch retries on rate limit."""
    mock_response = Mock()
    mock_response.text = """
    <?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <item>
                <title>Python Developer</title>
                <link>https://example.com/job1</link>
                <company>Test Company</company>
            </item>
        </channel>
    </rss>
    """
    
    # First call raises rate limit, second succeeds
    with patch('requests.get', side_effect=[
        RequestException(response=Mock(status_code=429)),
        mock_response
    ]):
        jobs = fetcher.fetch(rss_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"

def test_fetch_max_retries_exceeded(fetcher, rss_feed):
    """Test that fetch raises after max retries."""
    # All calls raise rate limit
    with patch('requests.get', side_effect=[
        RequestException(response=Mock(status_code=429)),
        RequestException(response=Mock(status_code=429)),
        RequestException(response=Mock(status_code=429))
    ]):
        with pytest.raises(RequestException):
            fetcher.fetch(rss_feed, max_retries=2)

def test_fetch_unsupported_type(fetcher):
    """Test that fetch raises on unsupported feed type."""
    feed = Feed(
        name="test",
        url="https://example.com",
        type="unsupported",
        parser="test",
        fetch_method="unsupported",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    with pytest.raises(ValueError, match="Unsupported fetch_method"):
        fetcher.fetch(feed)

def test_fetch_html_snaphunt(fetcher):
    """Test fetching from Snaphunt HTML feed."""
    snaphunt_feed = Feed(
        name="snaphunt",
        url="https://snaphunt.com/jobs",
        type="html",
        parser="snaphunt",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card">
        <h3 class="job-title">Python Developer</h3>
        <div class="company-name">Test Company</div>
        <a class="job-link" href="/jobs/123">View Job</a>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(snaphunt_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://snaphunt.com/jobs/123"

def test_fetch_html_alljobs(fetcher):
    """Test fetching from AllJobs HTML feed."""
    alljobs_feed = Feed(
        name="alljobs",
        url="https://www.alljobs.co.il/jobs",
        type="html",
        parser="alljobs",
        fetch_method="html",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-item">
        <h2 class="job-title">Python Developer</h2>
        <div class="company-name">Test Company</div>
        <a class="job-link" href="/jobs/123">View Job</a>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(alljobs_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://www.alljobs.co.il/jobs/123"

def test_fetch_html_remotive(fetcher):
    """Test fetching from Remotive HTML feed."""
    remotive_feed = Feed(
        name="remotive",
        url="https://remotive.com/jobs",
        type="html",
        parser="remotive",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card">
        <h2 class="job-title">Python Developer</h2>
        <div class="company-name">Test Company</div>
        <a class="job-link" href="/jobs/123">View Job</a>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(remotive_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://remotive.com/jobs/123"

def test_fetch_html_workingnomads(fetcher):
    """Test fetching from WorkingNomads HTML feed."""
    workingnomads_feed = Feed(
        name="workingnomads",
        url="https://www.workingnomads.com/jobs",
        type="html",
        parser="workingnomads",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card">
        <h2 class="job-title">Python Developer</h2>
        <div class="company-name">Test Company</div>
        <a class="job-link" href="/jobs/123">View Job</a>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(workingnomads_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://www.workingnomads.com/jobs/123"

def test_fetch_html_cryptojobslist(fetcher):
    """Test fetching from CryptoJobsList HTML feed."""
    cryptojobslist_feed = Feed(
        name="cryptojobslist",
        url="https://cryptojobslist.com/jobs",
        type="html",
        parser="cryptojobslist",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card">
        <h2 class="job-title">Python Developer</h2>
        <div class="company-name">Test Company</div>
        <a class="job-link" href="/jobs/123">View Job</a>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(cryptojobslist_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://cryptojobslist.com/jobs/123"

def test_fetch_html_remote3(fetcher):
    """Test fetching from Remote3 HTML feed."""
    remote3_feed = Feed(
        name="remote3",
        url="https://www.remote3.co/jobs",
        type="html",
        parser="remote3",
        fetch_method="html",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card">
        <h2 class="job-title">Python Developer</h2>
        <div class="company-name">Test Company</div>
        <a class="job-link" href="/jobs/123">View Job</a>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(remote3_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://www.remote3.co/jobs/123"

def test_fetch_html_mindtel(fetcher):
    """Test fetching from Mindtel HTML feed."""
    mindtel_feed = Feed(
        name="mindtel",
        url="https://mindtel.atsmantra.com/jobs",
        type="html",
        parser="mindtel",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card">
        <h2 class="job-title">Python Developer</h2>
        <div class="company-name">Test Company</div>
        <a class="job-link" href="/jobs/123">View Job</a>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(mindtel_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://mindtel.atsmantra.com/jobs/123"

def test_fetch_html_nodesk(fetcher):
    """Test fetching from Nodesk HTML feed."""
    nodesk_feed = Feed(
        name="nodesk",
        url="https://nodesk.co/jobs",
        type="html",
        parser="nodesk",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card">
        <h2 class="job-title">Python Developer</h2>
        <div class="company-name">Test Company</div>
        <a class="job-link" href="/jobs/123">View Job</a>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(nodesk_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://nodesk.co/jobs/123"

def test_fetch_html_cryptocurrencyjobs(fetcher):
    """Test fetching from CryptocurrencyJobs HTML feed."""
    cryptocurrencyjobs_feed = Feed(
        name="cryptocurrencyjobs",
        url="https://cryptocurrencyjobs.co/jobs",
        type="html",
        parser="cryptocurrencyjobs",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card">
        <h2 class="job-title">Python Developer</h2>
        <div class="company-name">Test Company</div>
        <a class="job-link" href="/jobs/123">View Job</a>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(cryptocurrencyjobs_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://cryptocurrencyjobs.co/jobs/123"

def test_fetch_html_nodesk_substack(fetcher):
    """Test fetching from Nodesk Substack HTML feed."""
    nodesk_substack_feed = Feed(
        name="nodesk_substack",
        url="https://nodesk.substack.com/jobs",
        type="html",
        parser="nodesk_substack",
        fetch_method="html",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card">
        <h2 class="job-title">Python Developer</h2>
        <div class="company-name">Test Company</div>
        <a class="job-link" href="/jobs/123">View Job</a>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(nodesk_substack_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://nodesk.substack.com/jobs/123"

def test_fetch_html_remotehabits(fetcher):
    """Test fetching from RemoteHabits HTML feed."""
    remotehabits_feed = Feed(
        name="remotehabits",
        url="https://remotehabits.com/jobs",
        type="html",
        parser="remotehabits",
        fetch_method="html",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card">
        <h2 class="job-title">Python Developer</h2>
        <div class="company-name">Test Company</div>
        <a class="job-link" href="/jobs/123">View Job</a>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(remotehabits_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://remotehabits.com/jobs/123"

def test_fetch_html_jobspresso(fetcher):
    """Test fetching from Jobspresso HTML feed."""
    jobspresso_feed = Feed(
        name="jobspresso",
        url="https://jobspresso.co/jobs",
        type="html",
        parser="jobspresso",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card">
        <h2 class="job-title">Python Developer</h2>
        <div class="company-name">Test Company</div>
        <a class="job-link" href="/jobs/123">View Job</a>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(jobspresso_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://jobspresso.co/jobs/123"

def test_fetch_html_weworkremotely_support(fetcher):
    """Test fetching from WeWorkRemotely Support HTML feed."""
    weworkremotely_support_feed = Feed(
        name="weworkremotely_support",
        url="https://weworkremotely.com/support-jobs",
        type="html",
        parser="weworkremotely_support",
        fetch_method="html",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card">
        <h2 class="job-title">Python Developer</h2>
        <div class="company-name">Test Company</div>
        <a class="job-link" href="/jobs/123">View Job</a>
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(weworkremotely_support_feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"
        assert jobs[0].company == "Test Company"
        assert jobs[0].url == "https://weworkremotely.com/jobs/123"

def test_fetch_html_empty_response(fetcher):
    """Test fetching from HTML feed with empty response."""
    feed = Feed(
        name="test",
        url="https://example.com/jobs",
        type="html",
        parser="test",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = "<html><body></body></html>"
    
    with patch('requests.get', return_value=mock_response):
        with pytest.raises(ValueError, match="No HTML parser implemented for: test"):
            fetcher.fetch(feed)

def test_fetch_html_malformed_response(fetcher):
    """Test fetching from HTML feed with malformed response."""
    feed = Feed(
        name="test",
        url="https://example.com/jobs",
        type="html",
        parser="test",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = "<html><body><div>Invalid HTML</div></body></html>"
    
    with patch('requests.get', return_value=mock_response):
        with pytest.raises(ValueError, match="No HTML parser implemented for: test"):
            fetcher.fetch(feed)

def test_fetch_html_missing_elements(fetcher):
    """Test fetching from HTML feed with missing elements."""
    feed = Feed(
        name="test",
        url="https://example.com/jobs",
        type="html",
        parser="test",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card">
        <h2 class="job-title">Python Developer</h2>
        <!-- Missing company name and link -->
    </div>
    """
    
    with patch('requests.get', return_value=mock_response):
        with pytest.raises(ValueError, match="No HTML parser implemented for: test"):
            fetcher.fetch(feed)

def test_fetch_method_rss(fetcher):
    feed = Feed(
        name="jobicy",
        url="https://jobicy.com/jobs-rss-feed",
        type="rss",
        parser="rss",
        fetch_method="rss",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    mock_response = Mock()
    mock_response.text = """
    <rss><channel><item><title>Remote Support</title><link>https://jobicy.com/job1</link><company>Jobicy</company></item></channel></rss>
    """
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Remote Support"
        assert jobs[0].company == "Jobicy"
        assert jobs[0].url == "https://jobicy.com/job1"

def test_fetch_method_json(fetcher):
    feed = Feed(
        name="github",
        url="https://jobs.github.com/positions.json?description=python&location=remote",
        type="json",
        parser="github",
        fetch_method="json",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    mock_response = Mock()
    mock_response.json.return_value = [{
        'id': '2',
        'title': 'Backend Engineer',
        'company': 'GitHub',
        'url': 'https://jobs.github.com/job2',
        'date': '2024-01-01'
    }]
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Backend Engineer"
        assert jobs[0].company == "GitHub"
        assert jobs[0].url == "https://jobs.github.com/job2"

def test_fetch_method_html(fetcher):
    feed = Feed(
        name="snaphunt",
        url="https://snaphunt.com/job-listing/all-locations/Remote/",
        type="html",
        parser="snaphunt",
        fetch_method="html",
        rate_limit={'requests_per_minute': 2, 'retry_after': 1}
    )
    mock_response = Mock()
    mock_response.text = """
    <div class="job-card"><h3 class="job-title">Support Agent</h3><div class="company-name">Snaphunt</div><a class="job-link" href="/job/123"></a></div>
    """
    with patch('requests.get', return_value=mock_response):
        jobs = fetcher.fetch(feed)
        assert len(jobs) == 1
        assert jobs[0].title == "Support Agent"
        assert jobs[0].company == "Snaphunt"
        assert jobs[0].url.endswith("/job/123")

def test_fetch_method_rss_new_boards(fetcher):
    boards = [
        ("himalayas", "https://rss.himalayas.app/jobs"),
        ("supportdriven", "https://supportdriven.com/jobs?format=rss"),
        ("web3career", "https://web3.career/remote-jobs.rss"),
        ("authenticjobs", "https://authenticjobs.com/rss/index.xml")
    ]
    for name, url in boards:
        feed = Feed(
            name=name,
            url=url,
            type="rss",
            parser="rss",
            fetch_method="rss",
            rate_limit={'requests_per_minute': 2, 'retry_after': 1}
        )
        mock_response = Mock()
        mock_response.text = f"""
        <rss><channel><item><title>{name.title()} Job</title><link>{url}/job1</link><company>{name.title()}</company></item></channel></rss>
        """
        with patch('requests.get', return_value=mock_response):
            jobs = fetcher.fetch(feed)
            assert len(jobs) == 1
            assert jobs[0].title == f"{name.title()} Job"
            assert jobs[0].company == name.title()
            assert jobs[0].url == f"{url}/job1"

def test_fetch_html_linkedin_duplicate_ids(fetcher):
    """Test LinkedIn parser handles duplicate IDs correctly."""
    linkedin_feed = Feed(
        name="linkedin",
        url="https://www.linkedin.com/jobs/search/?keywords=remote%20customer%20support",
        type="headless",
        parser="linkedin",
        fetch_method="headless"
    )
    
    # HTML with multiple jobs that would generate duplicate IDs
    html_content = """
    <div class="job-card-container">
        <h3 class="job-card-list__title">Customer Support Agent</h3>
        <h4 class="job-card-container__company-name">TechCorp</h4>
        <a class="job-card-list__title-link" href="/jobs/view/123456">View Job</a>
    </div>
    <div class="job-card-container">
        <h3 class="job-card-list__title">Customer Support Agent</h3>
        <h4 class="job-card-container__company-name">TechCorp</h4>
        <!-- No URL, will fallback to hash -->
    </div>
    <div class="job-card-container">
        <h3 class="job-card-list__title">Customer Support Agent</h3>
        <h4 class="job-card-container__company-name">TechCorp</h4>
        <!-- No URL, will fallback to hash -->
    </div>
    <div class="job-card-container">
        <h3 class="job-card-list__title">Customer Care Associate</h3>
        <h4 class="job-card-container__company-name">AnotherCorp</h4>
        <a class="job-card-list__title-link" href="/jobs/view/789012">View Job</a>
    </div>
    """
    
    # Test the parser directly instead of the full fetch process
    soup = BeautifulSoup(html_content, "html.parser")
    jobs = fetcher._parse_linkedin(soup, linkedin_feed)
    
    # Should have 4 jobs
    assert len(jobs) == 4
    
    # All jobs should have unique IDs
    job_ids = [job.id for job in jobs]
    assert len(job_ids) == len(set(job_ids)), "All job IDs should be unique"
    
    # First job should have URL-based ID
    assert jobs[0].id == "123456"
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/123456"
    
    # Fourth job should have different URL-based ID
    assert jobs[3].id == "789012"
    assert jobs[3].url == "https://www.linkedin.com/jobs/view/789012"
    
    # Jobs without URLs should have hash-based IDs with suffixes
    hash_based_jobs = [job for job in jobs if job.url == ""]
    assert len(hash_based_jobs) == 2
    
    # Check that duplicate titles get unique IDs
    duplicate_title_jobs = [job for job in jobs if job.title == "Customer Support Agent"]
    assert len(duplicate_title_jobs) == 3
    duplicate_ids = [job.id for job in duplicate_title_jobs]
    assert len(duplicate_ids) == len(set(duplicate_ids)), "Duplicate titles should have unique IDs"

def test_linkedin_parser_url_patterns(fetcher):
    """Test LinkedIn parser handles various URL patterns correctly."""
    from bs4 import BeautifulSoup
    from jobradar.models import Feed
    
    linkedin_feed = Feed(
        name="linkedin",
        url="https://www.linkedin.com/jobs/search/",
        type="html",
        parser="linkedin"
    )
    
    # Test various LinkedIn URL patterns
    test_cases = [
        {
            "url": "/jobs/view/123456789",
            "expected_id": "123456789",
            "description": "Standard job view URL"
        },
        {
            "url": "/jobs/search/?jobId=987654321",
            "expected_id": "987654321", 
            "description": "Job ID parameter"
        },
        {
            "url": "/jobs/search/?currentJobId=555666777",
            "expected_id": "555666777",
            "description": "Current job ID parameter"
        },
        {
            "url": "/jobs/collections/recommended/?job-111222333",
            "expected_id": "111222333",
            "description": "Job with dash format"
        },
        {
            "url": "/jobs/search/444555666/?refId=abc123def",
            "expected_id": "abc123def",  # refId pattern matches first
            "description": "URL with refId parameter"
        },
        {
            "url": "/jobs/search/444555666/",
            "expected_id": "444555666",  # Numeric ID at end (no query params)
            "description": "Numeric ID at end of URL"
        },
        {
            "url": "/jobs/search/?refId=xyz789&trackingId=track123",
            "expected_id": "xyz789",
            "description": "Reference ID parameter"
        }
    ]
    
    for i, test_case in enumerate(test_cases):
        html_content = f"""
        <div class="job-card-container">
            <h3 class="job-card-list__title">Test Job {i}</h3>
            <h4 class="job-card-container__company-name">Test Company {i}</h4>
            <a class="job-card-list__title-link" href="{test_case['url']}">View Job</a>
        </div>
        """
        
        soup = BeautifulSoup(html_content, "html.parser")
        jobs = fetcher._parse_linkedin(soup, linkedin_feed)
        
        assert len(jobs) == 1, f"Should parse one job for {test_case['description']}"
        assert jobs[0].id == test_case['expected_id'], f"ID mismatch for {test_case['description']}: expected {test_case['expected_id']}, got {jobs[0].id}"
        assert jobs[0].url == f"https://www.linkedin.com{test_case['url']}", f"URL mismatch for {test_case['description']}"

def test_linkedin_parser_fallback_id_generation(fetcher):
    """Test LinkedIn parser fallback ID generation for jobs without URLs."""
    from bs4 import BeautifulSoup
    from jobradar.models import Feed
    
    linkedin_feed = Feed(
        name="linkedin",
        url="https://www.linkedin.com/jobs/search/",
        type="html", 
        parser="linkedin"
    )
    
    # HTML with jobs that have no URLs (will use hash-based IDs)
    html_content = """
    <div class="job-card-container">
        <h3 class="job-card-list__title">Software Engineer</h3>
        <h4 class="job-card-container__company-name">TechCorp</h4>
    </div>
    <div class="job-card-container">
        <h3 class="job-card-list__title">Data Scientist</h3>
        <h4 class="job-card-container__company-name">DataCorp</h4>
    </div>
    <div class="job-card-container">
        <h3 class="job-card-list__title">Software Engineer</h3>
        <h4 class="job-card-container__company-name">TechCorp</h4>
    </div>
    """
    
    soup = BeautifulSoup(html_content, "html.parser")
    jobs = fetcher._parse_linkedin(soup, linkedin_feed)
    
    assert len(jobs) == 3, "Should parse three jobs"
    
    # All jobs should have unique IDs
    job_ids = [job.id for job in jobs]
    assert len(job_ids) == len(set(job_ids)), "All job IDs should be unique"
    
    # Jobs with same title/company should have different IDs due to position index
    duplicate_jobs = [job for job in jobs if job.title == "Software Engineer" and job.company == "TechCorp"]
    assert len(duplicate_jobs) == 2, "Should have two identical jobs"
    assert duplicate_jobs[0].id != duplicate_jobs[1].id, "Identical jobs should have different IDs"
    
    # IDs should be hash-based (16 characters) or hash-based with suffix
    for job in jobs:
        assert len(job.id) >= 16, f"Job ID should be at least 16 characters: {job.id}"
        # Should be alphanumeric (hash) or hash with underscore and number
        import re
        assert re.match(r'^[a-f0-9]{16}(_\d+)?$', job.id), f"Job ID should match hash pattern: {job.id}"

def test_linkedin_parser_complex_url_cleaning(fetcher):
    """Test LinkedIn parser handles complex URLs and cleans them properly."""
    from bs4 import BeautifulSoup
    from jobradar.models import Feed
    
    linkedin_feed = Feed(
        name="linkedin",
        url="https://www.linkedin.com/jobs/search/",
        type="html",
        parser="linkedin"
    )
    
    # Test complex URL that doesn't match standard patterns
    html_content = """
    <div class="job-card-container">
        <h3 class="job-card-list__title">Complex URL Job</h3>
        <h4 class="job-card-container__company-name">ComplexCorp</h4>
        <a class="job-card-list__title-link" href="/jobs/search/results/?keywords=test&location=remote&f_TPR=r86400&f_JT=F&f_E=2%2C3&start=25&sortBy=R">View Job</a>
    </div>
    """
    
    soup = BeautifulSoup(html_content, "html.parser")
    jobs = fetcher._parse_linkedin(soup, linkedin_feed)
    
    assert len(jobs) == 1, "Should parse one job"
    
    # ID should be cleaned URL path (no numeric ID found in patterns)
    expected_id = "jobs-search-results--keywords=test-location=remote-f_TPR=r86400-f_JT=F-f_E=2%2C3-start=25-sortBy=R"
    assert jobs[0].id == expected_id[:100], "Should use cleaned URL path as ID (truncated to 100 chars)"
    assert jobs[0].url == "https://www.linkedin.com/jobs/search/results/?keywords=test&location=remote&f_TPR=r86400&f_JT=F&f_E=2%2C3&start=25&sortBy=R"

def test_linkedin_parser_uniqueness_stress_test(fetcher):
    """Stress test LinkedIn parser with many duplicate jobs."""
    from bs4 import BeautifulSoup
    from jobradar.models import Feed
    
    linkedin_feed = Feed(
        name="linkedin",
        url="https://www.linkedin.com/jobs/search/",
        type="html",
        parser="linkedin"
    )
    
    # Create HTML with 50 identical jobs (stress test for uniqueness)
    job_cards = []
    for i in range(50):
        job_cards.append("""
        <div class="job-card-container">
            <h3 class="job-card-list__title">Customer Support Agent</h3>
            <h4 class="job-card-container__company-name">SameCorp</h4>
        </div>
        """)
    
    html_content = "".join(job_cards)
    soup = BeautifulSoup(html_content, "html.parser")
    jobs = fetcher._parse_linkedin(soup, linkedin_feed)
    
    assert len(jobs) == 50, "Should parse all 50 jobs"
    
    # All jobs should have unique IDs
    job_ids = [job.id for job in jobs]
    assert len(job_ids) == len(set(job_ids)), "All 50 job IDs should be unique"
    
    # All jobs should have the same title and company
    for job in jobs:
        assert job.title == "Customer Support Agent"
        assert job.company == "SameCorp"
    
    # IDs should be hash-based (16 characters) since no URLs are provided
    # Each job gets a unique hash because position index is included in hash generation
    for job in jobs:
        assert len(job.id) == 16, f"Job ID should be 16-character hash: {job.id}"
        # Should be alphanumeric (hash)
        import re
        assert re.match(r'^[a-f0-9]{16}$', job.id), f"Job ID should be hex hash: {job.id}"

def test_linkedin_parser_mixed_scenarios(fetcher):
    """Test LinkedIn parser with mixed scenarios (URLs, no URLs, duplicates)."""
    from bs4 import BeautifulSoup
    from jobradar.models import Feed
    
    linkedin_feed = Feed(
        name="linkedin",
        url="https://www.linkedin.com/jobs/search/",
        type="html",
        parser="linkedin"
    )
    
    html_content = """
    <!-- Job with standard URL -->
    <div class="job-card-container">
        <h3 class="job-card-list__title">Senior Developer</h3>
        <h4 class="job-card-container__company-name">TechCorp</h4>
        <a class="job-card-list__title-link" href="/jobs/view/123456">View Job</a>
    </div>
    
    <!-- Job with parameter URL -->
    <div class="job-card-container">
        <h3 class="job-card-list__title">Junior Developer</h3>
        <h4 class="job-card-container__company-name">StartupCorp</h4>
        <a class="job-card-list__title-link" href="/jobs/search/?jobId=789012">View Job</a>
    </div>
    
    <!-- Job without URL (will use hash) -->
    <div class="job-card-container">
        <h3 class="job-card-list__title">Support Agent</h3>
        <h4 class="job-card-container__company-name">SupportCorp</h4>
    </div>
    
    <!-- Duplicate of first job (same title/company, no URL) -->
    <div class="job-card-container">
        <h3 class="job-card-list__title">Senior Developer</h3>
        <h4 class="job-card-container__company-name">TechCorp</h4>
    </div>
    
    <!-- Another duplicate (same title/company, no URL) -->
    <div class="job-card-container">
        <h3 class="job-card-list__title">Senior Developer</h3>
        <h4 class="job-card-container__company-name">TechCorp</h4>
    </div>
    
    <!-- Job with complex URL -->
    <div class="job-card-container">
        <h3 class="job-card-list__title">Product Manager</h3>
        <h4 class="job-card-container__company-name">ProductCorp</h4>
        <a class="job-card-list__title-link" href="/jobs/collections/recommended/?refId=abc123">View Job</a>
    </div>
    """
    
    soup = BeautifulSoup(html_content, "html.parser")
    jobs = fetcher._parse_linkedin(soup, linkedin_feed)
    
    assert len(jobs) == 6, "Should parse all 6 jobs"
    
    # All jobs should have unique IDs
    job_ids = [job.id for job in jobs]
    assert len(job_ids) == len(set(job_ids)), "All job IDs should be unique"
    
    # Check specific ID patterns
    assert jobs[0].id == "123456", "First job should have URL-based ID"
    assert jobs[1].id == "789012", "Second job should have parameter-based ID"
    assert jobs[5].id == "abc123", "Last job should have refId-based ID"
    
    # Jobs without URLs should have hash-based IDs
    no_url_jobs = [job for job in jobs if job.url == ""]
    assert len(no_url_jobs) == 3, "Should have 3 jobs without URLs"
    
    # Check that duplicate titles get unique IDs
    senior_dev_jobs = [job for job in jobs if job.title == "Senior Developer"]
    assert len(senior_dev_jobs) == 3, "Should have 3 Senior Developer jobs"
    senior_dev_ids = [job.id for job in senior_dev_jobs]
    assert len(senior_dev_ids) == len(set(senior_dev_ids)), "Senior Developer jobs should have unique IDs" 