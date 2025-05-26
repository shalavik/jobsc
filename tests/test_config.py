"""Tests for configuration loading functionality."""
from pathlib import Path
from typing import List
import pytest
from jobradar.models import Feed
from jobradar.config import load_feeds
import os
import tempfile
from unittest.mock import patch
from jobradar.config import Config

def test_config_loads_feeds(tmp_path: Path) -> None:
    """Test that feeds.yml is properly loaded and parsed into Feed objects.
    
    Args:
        tmp_path: pytest fixture providing temporary directory
    """
    # Arrange
    feeds_content = """
    - name: RemoteOK
      url: https://remoteok.com/feed
      type: rss
      fetch_method: rss
    - name: WorkingNomads
      url: https://www.workingnomads.com/jobsapi
      type: json
      fetch_method: json
    """
    feeds_file = tmp_path / "feeds.yml"
    feeds_file.write_text(feeds_content)
    
    # Act
    feeds: List[Feed] = load_feeds(feeds_file)
    
    # Assert
    assert len(feeds) == 2
    assert feeds[0].name == "RemoteOK"
    assert feeds[0].url == "https://remoteok.com/feed"
    assert feeds[0].type == "rss"
    assert feeds[0].fetch_method == "rss"
    assert feeds[1].name == "WorkingNomads"
    assert feeds[1].url == "https://www.workingnomads.com/jobsapi"
    assert feeds[1].type == "json"
    assert feeds[1].fetch_method == "json"

def test_config_handles_missing_file() -> None:
    """Test that appropriate error is raised when feeds.yml is missing."""
    with pytest.raises(FileNotFoundError):
        load_feeds(Path("nonexistent.yml"))

def test_config_validates_schema(tmp_path: Path) -> None:
    """Test that invalid feed configurations are rejected.
    
    Args:
        tmp_path: pytest fixture providing temporary directory
    """
    # Arrange
    invalid_content = """
    - name: InvalidFeed
      type: unknown
    """
    feeds_file = tmp_path / "feeds.yml"
    feeds_file.write_text(invalid_content)
    
    # Act & Assert
    with pytest.raises(ValueError, match="Invalid feed type"):
        load_feeds(feeds_file)

def test_config_defaults_fetch_method_to_type(tmp_path: Path) -> None:
    """Test that fetch_method defaults to type if not specified.
    
    Args:
        tmp_path: pytest fixture providing temporary directory
    """
    # Arrange
    feeds_content = """
    - name: TestFeed
      url: https://example.com/feed
      type: rss
    """
    feeds_file = tmp_path / "feeds.yml"
    feeds_file.write_text(feeds_content)
    
    # Act
    feeds: List[Feed] = load_feeds(feeds_file)
    
    # Assert
    assert len(feeds) == 1
    assert feeds[0].fetch_method == "rss"  # Should default to type 

class TestConfig:
    """Test configuration management functionality."""
    
    def test_config_loads_from_environment(self):
        """Test that configuration loads from environment variables."""
        with patch.dict(os.environ, {
            'DATABASE_URL': 'postgresql://test:test@localhost/test',
            'SMTP_HOST': 'smtp.test.com',
            'ENABLE_PROXIES': 'true'
        }, clear=True):
            config = Config()
            
            assert config.get('DATABASE_URL') == 'postgresql://test:test@localhost/test'
            assert config.get('SMTP_HOST') == 'smtp.test.com'
            assert config.get_bool('ENABLE_PROXIES') is True
    
    def test_config_loads_from_env_file(self):
        """Test that configuration loads from .env file."""
        # Create temporary .env file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env') as f:
            f.write("DATABASE_URL=sqlite:///test.db\n")
            f.write("SMTP_PORT=465\n")
            f.write("ENABLE_DEDUPLICATION=false\n")
            env_file = f.name
        
        try:
            with patch.dict(os.environ, {}, clear=True):
                config = Config(env_file=env_file)
                
                assert config.get('DATABASE_URL') == 'sqlite:///test.db'
                assert config.get_int('SMTP_PORT') == 465
                assert config.get_bool('ENABLE_DEDUPLICATION') is False
        finally:
            os.unlink(env_file)
    
    def test_config_defaults(self):
        """Test that configuration provides sensible defaults."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            
            # Test default values
            assert config.get('NONEXISTENT_KEY', 'default') == 'default'
            assert config.get_bool('NONEXISTENT_BOOL', True) is True
            assert config.get_int('NONEXISTENT_INT', 42) == 42
            assert config.get_float('NONEXISTENT_FLOAT', 3.14) == 3.14
            assert config.get_list('NONEXISTENT_LIST', ['a', 'b']) == ['a', 'b']
    
    def test_config_type_conversions(self):
        """Test that configuration correctly converts types."""
        with patch.dict(os.environ, {
            'BOOL_TRUE': 'true',
            'BOOL_FALSE': 'false',
            'BOOL_ONE': '1',
            'BOOL_ZERO': '0',
            'INT_VALUE': '123',
            'FLOAT_VALUE': '45.67',
            'LIST_VALUE': 'item1,item2,item3'
        }, clear=True):
            config = Config()
            
            # Test boolean conversions
            assert config.get_bool('BOOL_TRUE') is True
            assert config.get_bool('BOOL_FALSE') is False
            assert config.get_bool('BOOL_ONE') is True
            assert config.get_bool('BOOL_ZERO') is False
            
            # Test numeric conversions
            assert config.get_int('INT_VALUE') == 123
            assert config.get_float('FLOAT_VALUE') == 45.67
            
            # Test list conversion
            assert config.get_list('LIST_VALUE') == ['item1', 'item2', 'item3']
    
    def test_config_invalid_type_conversions(self):
        """Test that invalid type conversions use defaults."""
        with patch.dict(os.environ, {
            'INVALID_INT': 'not_a_number',
            'INVALID_FLOAT': 'not_a_float'
        }, clear=True):
            config = Config()
            
            # Should use defaults for invalid values
            assert config.get_int('INVALID_INT', 999) == 999
            assert config.get_float('INVALID_FLOAT', 1.23) == 1.23
    
    def test_required_config_validation(self):
        """Test that required configuration validation works."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            
            # Should raise error for missing required key
            with pytest.raises(ValueError, match="Required configuration key 'REQUIRED_KEY' is missing"):
                config.get('REQUIRED_KEY', required=True)
    
    def test_database_config(self):
        """Test database configuration parsing."""
        with patch.dict(os.environ, {
            'DATABASE_URL': 'postgresql://user:pass@host:5432/db',
            'DATABASE_ECHO': 'true',
            'DATABASE_POOL_SIZE': '10'
        }, clear=True):
            config = Config()
            db_config = config.get_database_config()
            
            assert db_config['url'] == 'postgresql://user:pass@host:5432/db'
            assert db_config['echo'] is True
            assert db_config['pool_size'] == 10
    
    def test_email_config(self):
        """Test email configuration parsing."""
        with patch.dict(os.environ, {
            'SMTP_HOST': 'smtp.gmail.com',
            'SMTP_PORT': '587',
            'SMTP_USER': 'test@example.com',
            'SMTP_PASSWORD': 'secret',
            'FROM_EMAIL': 'noreply@example.com',
            'TO_EMAILS': 'user1@example.com,user2@example.com'
        }, clear=True):
            config = Config()
            email_config = config.get_email_config()
            
            assert email_config['smtp_host'] == 'smtp.gmail.com'
            assert email_config['smtp_port'] == 587
            assert email_config['smtp_user'] == 'test@example.com'
            assert email_config['smtp_password'] == 'secret'
            assert email_config['from_email'] == 'noreply@example.com'
            assert email_config['to_emails'] == ['user1@example.com', 'user2@example.com']
    
    def test_telegram_config(self):
        """Test Telegram configuration parsing."""
        with patch.dict(os.environ, {
            'TELEGRAM_BOT_TOKEN': 'bot123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11',
            'TELEGRAM_CHAT_ID': '-123456789'
        }, clear=True):
            config = Config()
            telegram_config = config.get_telegram_config()
            
            assert telegram_config['bot_token'] == 'bot123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'
            assert telegram_config['chat_id'] == '-123456789'
    
    def test_proxy_config(self):
        """Test proxy configuration parsing."""
        with patch.dict(os.environ, {
            'ENABLE_PROXIES': 'true',
            'PROXY_LIST_PATH': '/path/to/proxies.txt',
            'PROXY_COUNTRY_CODE': 'US',
            'VALIDATE_PROXIES': 'false'
        }, clear=True):
            config = Config()
            proxy_config = config.get_proxy_config()
            
            assert proxy_config['enabled'] is True
            assert proxy_config['proxy_list_path'] == '/path/to/proxies.txt'
            assert proxy_config['country_code'] == 'US'
            assert proxy_config['validate_proxies'] is False
    
    def test_rate_limit_config(self):
        """Test rate limiting configuration parsing."""
        with patch.dict(os.environ, {
            'RATE_LIMIT_GLOBAL_MAX_TOKENS': '100',
            'RATE_LIMIT_GLOBAL_REFILL_RATE': '10.5',
            'RATE_LIMIT_INITIAL_BACKOFF': '2.0',
            'RATE_LIMIT_MAX_BACKOFF': '600.0'
        }, clear=True):
            config = Config()
            rate_config = config.get_rate_limit_config()
            
            assert rate_config['global_max_tokens'] == 100
            assert rate_config['global_refill_rate'] == 10.5
            assert rate_config['initial_backoff'] == 2.0
            assert rate_config['max_backoff'] == 600.0
    
    def test_job_sources_config(self):
        """Test job sources configuration parsing."""
        with patch.dict(os.environ, {
            'ENABLED_JOB_SOURCES': 'linkedin,indeed,stackoverflow',
            'JOB_FETCH_INTERVAL': '1800',
            'MAX_JOBS_PER_SOURCE': '50',
            'JOB_EXPIRY_DAYS': '14'
        }, clear=True):
            config = Config()
            sources_config = config.get_job_sources_config()
            
            assert sources_config['enabled_sources'] == ['linkedin', 'indeed', 'stackoverflow']
            assert sources_config['fetch_interval'] == 1800
            assert sources_config['max_jobs_per_source'] == 50
            assert sources_config['job_expiry_days'] == 14
    
    def test_ci_environment_skips_validation(self):
        """Test that CI environment skips Telegram tests as mentioned in improvements."""
        with patch.dict(os.environ, {
            'CI': 'true',
            'GITHUB_ACTIONS': 'true'
        }, clear=True):
            config = Config()
            
            # Should not raise any errors in CI environment
            config.validate_required_config()
            
            # Verify CI detection
            assert config.get_bool('CI') is True
            assert config.get_bool('GITHUB_ACTIONS') is True
    
    def test_config_validation_warnings(self):
        """Test that configuration validation provides helpful warnings."""
        with patch.dict(os.environ, {
            'SMTP_HOST': 'smtp.example.com',
            # Missing other required email fields
            'TELEGRAM_BOT_TOKEN': 'bot123456:token'
            # Missing TELEGRAM_CHAT_ID
        }, clear=True):
            config = Config()
            
            # Should not raise errors but log warnings
            config.validate_required_config()
    
    def test_get_all_config(self):
        """Test that get_all_config returns complete configuration."""
        with patch.dict(os.environ, {
            'DATABASE_URL': 'sqlite:///test.db',
            'SMTP_HOST': 'smtp.test.com'
        }, clear=True):
            config = Config()
            all_config = config.get_all_config()
            
            # Should contain all configuration sections
            expected_sections = [
                'database', 'email', 'telegram', 'slack', 'proxy',
                'rate_limit', 'job_sources', 'matching', 'web'
            ]
            
            for section in expected_sections:
                assert section in all_config
                assert isinstance(all_config[section], dict)
    
    def test_web_config(self):
        """Test web server configuration parsing."""
        with patch.dict(os.environ, {
            'WEB_HOST': '127.0.0.1',
            'WEB_PORT': '9000',
            'WEB_DEBUG': 'true',
            'WEB_WORKERS': '4'
        }, clear=True):
            config = Config()
            web_config = config.get_web_config()
            
            assert web_config['host'] == '127.0.0.1'
            assert web_config['port'] == 9000
            assert web_config['debug'] is True
            assert web_config['workers'] == 4 