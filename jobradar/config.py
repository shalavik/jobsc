"""Configuration loader for feeds."""
from pathlib import Path
from typing import List
import yaml
from .models import Feed

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