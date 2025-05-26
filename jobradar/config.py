"""Configuration loader for feeds."""
from pathlib import Path
from typing import List, Optional, Dict, Any
import yaml
from .models import Feed
import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

VALID_FEED_TYPES = {"rss", "json", "html", "headless"}

DEFAULT_CONFIG_FILES = ["feeds.yml", "projectrules"]

def load_feeds(path: Path = None) -> List[Feed]:
    """Load and validate feeds from a YAML file.
    
    Args:
        path: Path to feeds.yml or projectrules
    Returns:
        List of Feed objects
    Raises:
        FileNotFoundError: If the file does not exist
        ValueError: If a feed has an invalid type
    """
    if path is None:
        for fname in DEFAULT_CONFIG_FILES:
            if Path(fname).exists():
                path = Path(fname)
                break
        else:
            raise FileNotFoundError("No feeds config file found (feeds.yml or projectrules)")
    if not path.exists():
        raise FileNotFoundError(f"Feeds file not found: {path}")
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    # Support both top-level list and feeds key
    if isinstance(data, dict) and 'feeds' in data:
        feeds_data = data['feeds']
    else:
        feeds_data = data
    feeds = []
    for item in feeds_data:
        feed_type = item.get("type")
        if feed_type not in VALID_FEED_TYPES:
            raise ValueError("Invalid feed type")
        feeds.append(Feed(
            name=item.get("name", ""),
            url=item.get("url", ""),
            type=feed_type,
            parser=item.get("parser", ""),
            fetch_method=item.get("fetch_method", feed_type),  # Default to type if not specified
            rate_limit=item.get("rate_limit", None)
        ))
    return feeds

def get_config(config_file: str = None) -> dict:
    """Load the full configuration from feeds.yml or projectrules."""
    if config_file is None:
        for fname in DEFAULT_CONFIG_FILES:
            if Path(fname).exists():
                config_file = fname
                break
        else:
            raise FileNotFoundError("No config file found (feeds.yml or projectrules)")
    try:
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to load config: {e}")

class Config:
    """Configuration manager with environment variable and .env file support."""
    
    def __init__(self, env_file: Optional[str] = None):
        """Initialize configuration.
        
        Args:
            env_file: Optional path to .env file
        """
        # Load .env file if it exists (fallback for local development)
        if env_file and os.path.exists(env_file):
            load_dotenv(env_file)
            logger.info(f"Loaded configuration from {env_file}")
        elif os.path.exists(".env"):
            load_dotenv(".env")
            logger.info("Loaded configuration from .env file")
        else:
            logger.info("No .env file found, using environment variables only")
    
    def get(self, key: str, default: Any = None, required: bool = False) -> Any:
        """Get configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            required: Whether the key is required
            
        Returns:
            Configuration value
            
        Raises:
            ValueError: If required key is missing
        """
        value = os.getenv(key, default)
        
        if required and value is None:
            raise ValueError(f"Required configuration key '{key}' is missing")
            
        return value
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get boolean configuration value.
        
        Args:
            key: Configuration key
            default: Default boolean value
            
        Returns:
            Boolean value
        """
        value = self.get(key, str(default).lower())
        return str(value).lower() in ('true', '1', 'yes', 'on')
    
    def get_int(self, key: str, default: int = 0) -> int:
        """Get integer configuration value.
        
        Args:
            key: Configuration key
            default: Default integer value
            
        Returns:
            Integer value
        """
        value = self.get(key, str(default))
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning(f"Invalid integer value for {key}: {value}, using default {default}")
            return default
    
    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get float configuration value.
        
        Args:
            key: Configuration key
            default: Default float value
            
        Returns:
            Float value
        """
        value = self.get(key, str(default))
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"Invalid float value for {key}: {value}, using default {default}")
            return default
    
    def get_list(self, key: str, default: Optional[list] = None, separator: str = ",") -> list:
        """Get list configuration value.
        
        Args:
            key: Configuration key
            default: Default list value
            separator: List item separator
            
        Returns:
            List value
        """
        if default is None:
            default = []
            
        value = self.get(key)
        if not value:
            return default
            
        return [item.strip() for item in str(value).split(separator) if item.strip()]
    
    def get_database_config(self) -> Dict[str, str]:
        """Get database configuration.
        
        Returns:
            Database configuration dictionary
        """
        return {
            'url': self.get('DATABASE_URL', 'sqlite:///jobs.db'),
            'echo': self.get_bool('DATABASE_ECHO', False),
            'pool_size': self.get_int('DATABASE_POOL_SIZE', 5),
            'max_overflow': self.get_int('DATABASE_MAX_OVERFLOW', 10)
        }
    
    def get_email_config(self) -> Dict[str, Any]:
        """Get email notification configuration.
        
        Returns:
            Email configuration dictionary
        """
        return {
            'smtp_host': self.get('SMTP_HOST'),
            'smtp_port': self.get_int('SMTP_PORT', 587),
            'smtp_user': self.get('SMTP_USER'),
            'smtp_password': self.get('SMTP_PASSWORD'),
            'smtp_use_tls': self.get_bool('SMTP_USE_TLS', True),
            'from_email': self.get('FROM_EMAIL'),
            'to_emails': self.get_list('TO_EMAILS')
        }
    
    def get_telegram_config(self) -> Dict[str, str]:
        """Get Telegram notification configuration.
        
        Returns:
            Telegram configuration dictionary
        """
        return {
            'bot_token': self.get('TELEGRAM_BOT_TOKEN'),
            'chat_id': self.get('TELEGRAM_CHAT_ID')
        }
    
    def get_slack_config(self) -> Dict[str, str]:
        """Get Slack notification configuration.
        
        Returns:
            Slack configuration dictionary
        """
        return {
            'webhook_url': self.get('SLACK_WEBHOOK_URL'),
            'channel': self.get('SLACK_CHANNEL', '#jobs'),
            'username': self.get('SLACK_USERNAME', 'JobRadar')
        }
    
    def get_proxy_config(self) -> Dict[str, Any]:
        """Get proxy configuration.
        
        Returns:
            Proxy configuration dictionary
        """
        return {
            'enabled': self.get_bool('ENABLE_PROXIES', False),
            'proxy_list_path': self.get('PROXY_LIST_PATH'),
            'country_code': self.get('PROXY_COUNTRY_CODE'),
            'validate_proxies': self.get_bool('VALIDATE_PROXIES', True),
            'rotation_interval': self.get_int('PROXY_ROTATION_INTERVAL', 300)  # 5 minutes
        }
    
    def get_rate_limit_config(self) -> Dict[str, Any]:
        """Get rate limiting configuration.
        
        Returns:
            Rate limiting configuration dictionary
        """
        return {
            'global_max_tokens': self.get_int('RATE_LIMIT_GLOBAL_MAX_TOKENS', 50),
            'global_refill_rate': self.get_float('RATE_LIMIT_GLOBAL_REFILL_RATE', 5.0),
            'source_max_tokens': self.get_int('RATE_LIMIT_SOURCE_MAX_TOKENS', 100),
            'source_refill_rate': self.get_float('RATE_LIMIT_SOURCE_REFILL_RATE', 10.0),
            'initial_backoff': self.get_float('RATE_LIMIT_INITIAL_BACKOFF', 1.0),
            'max_backoff': self.get_float('RATE_LIMIT_MAX_BACKOFF', 300.0)
        }
    
    def get_job_sources_config(self) -> Dict[str, Any]:
        """Get job sources configuration.
        
        Returns:
            Job sources configuration dictionary
        """
        return {
            'enabled_sources': self.get_list('ENABLED_JOB_SOURCES', [
                'linkedin', 'indeed', 'remote_ok', 'stackoverflow'
            ]),
            'fetch_interval': self.get_int('JOB_FETCH_INTERVAL', 3600),  # 1 hour
            'max_jobs_per_source': self.get_int('MAX_JOBS_PER_SOURCE', 100),
            'job_expiry_days': self.get_int('JOB_EXPIRY_DAYS', 7)
        }
    
    def get_matching_config(self) -> Dict[str, Any]:
        """Get job matching configuration.
        
        Returns:
            Job matching configuration dictionary
        """
        return {
            'categories': self.get_list('JOB_CATEGORIES', [
                'customer_support', 'technical_support', 'compliance_analyst', 'marketing'
            ]),
            'similarity_threshold': self.get_float('SIMILARITY_THRESHOLD', 0.9),
            'enable_deduplication': self.get_bool('ENABLE_DEDUPLICATION', True),
            'enable_expiration_check': self.get_bool('ENABLE_EXPIRATION_CHECK', True)
        }
    
    def get_web_config(self) -> Dict[str, Any]:
        """Get web server configuration.
        
        Returns:
            Web server configuration dictionary
        """
        return {
            'host': self.get('WEB_HOST', '0.0.0.0'),
            'port': self.get_int('WEB_PORT', 8000),
            'debug': self.get_bool('WEB_DEBUG', False),
            'reload': self.get_bool('WEB_RELOAD', False),
            'workers': self.get_int('WEB_WORKERS', 1)
        }
    
    def validate_required_config(self) -> None:
        """Validate that required configuration is present.
        
        Raises:
            ValueError: If required configuration is missing
        """
        # Check if we're in CI environment
        is_ci = self.get_bool('CI', False) or self.get_bool('GITHUB_ACTIONS', False)
        
        if is_ci:
            logger.info("Running in CI environment, skipping some validation")
            return
        
        # Validate email config if email notifications are enabled
        email_config = self.get_email_config()
        if any(email_config.values()):
            required_email_keys = ['smtp_host', 'smtp_user', 'smtp_password', 'from_email']
            for key in required_email_keys:
                if not email_config.get(key):
                    logger.warning(f"Email configuration incomplete: missing {key}")
        
        # Validate Telegram config if Telegram notifications are enabled
        telegram_config = self.get_telegram_config()
        if telegram_config.get('bot_token'):
            if not telegram_config.get('chat_id'):
                logger.warning("Telegram bot token provided but chat_id missing")
        
        logger.info("Configuration validation completed")
    
    def get_all_config(self) -> Dict[str, Any]:
        """Get all configuration as a dictionary.
        
        Returns:
            Complete configuration dictionary
        """
        return {
            'database': self.get_database_config(),
            'email': self.get_email_config(),
            'telegram': self.get_telegram_config(),
            'slack': self.get_slack_config(),
            'proxy': self.get_proxy_config(),
            'rate_limit': self.get_rate_limit_config(),
            'job_sources': self.get_job_sources_config(),
            'matching': self.get_matching_config(),
            'web': self.get_web_config()
        }

# Global configuration instance
config = Config() 