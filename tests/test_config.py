"""Tests for configuration loading functionality."""
from pathlib import Path
from typing import List
import pytest
from jobradar.models import Feed
from jobradar.config import load_feeds

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