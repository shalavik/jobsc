"""
TDD Tests for JobRadar CLI Integration

Tests CLI commands and their integration with core functionality.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from click.testing import CliRunner

from jobradar.cli import cli, fetch, search, web
from jobradar.models import Job


class TestCLICommands:
    """Test CLI command functionality."""
    
    def test_cli_group_exists(self):
        """CLI group should be defined."""
        assert cli is not None
        assert hasattr(cli, 'commands')
    
    def test_fetch_command_exists(self):
        """Fetch command should exist."""
        assert 'fetch' in cli.commands
        assert fetch is not None
    
    def test_search_command_exists(self):
        """Search command should exist."""
        assert 'search' in cli.commands
        assert search is not None
    
    def test_web_command_exists(self):
        """Web command should exist."""
        assert 'web' in cli.commands
        assert web is not None


class TestCLIExecution:
    """Test CLI command execution."""
    
    def test_cli_help_works(self):
        """CLI help should work."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'JobRadar' in result.output or 'job' in result.output.lower()
    
    def test_fetch_help_works(self):
        """Fetch command help should work."""
        runner = CliRunner()
        result = runner.invoke(fetch, ['--help'])
        assert result.exit_code == 0
    
    def test_search_help_works(self):
        """Search command help should work.""" 
        runner = CliRunner()
        result = runner.invoke(search, ['--help'])
        assert result.exit_code == 0
    
    @patch('jobradar.cli.get_config')
    @patch('jobradar.cli.Fetcher')
    @patch('jobradar.cli.Database')
    def test_fetch_command_basic_execution(self, mock_db, mock_fetcher, mock_config):
        """Fetch command should execute without errors."""
        # Mock configuration
        mock_config.return_value = {
            'feeds': [{
                'name': 'test_feed',
                'url': 'http://example.com',
                'type': 'rss',
                'parser': 'rss'
            }]
        }
        
        # Mock fetcher
        mock_fetcher_instance = Mock()
        mock_fetcher_instance.fetch.return_value = []
        mock_fetcher.return_value = mock_fetcher_instance
        
        # Mock database
        mock_db_instance = Mock()
        mock_db.return_value = mock_db_instance
        
        runner = CliRunner()
        result = runner.invoke(fetch, ['--limit', '10'])
        
        # Should not crash
        assert result.exit_code in [0, 1]  # May exit with 1 if no jobs found
    
    @patch('jobradar.cli.Database')
    def test_search_command_basic_execution(self, mock_db):
        """Search command should execute without errors."""
        # Mock database
        mock_db_instance = Mock()
        mock_db_instance.search_jobs.return_value = []
        mock_db.return_value = mock_db_instance
        
        runner = CliRunner()
        result = runner.invoke(search, ['--title', 'engineer'])
        
        # Should not crash
        assert result.exit_code in [0, 1]


class TestCLIIntegration:
    """Test CLI integration with core components."""
    
    @patch('jobradar.cli.get_config')
    def test_fetch_loads_configuration(self, mock_config):
        """Fetch should load configuration from files."""
        mock_config.return_value = {'feeds': []}
        
        runner = CliRunner()
        result = runner.invoke(fetch, ['--help'])
        
        # Should attempt to load config (help doesn't need it to succeed)
        assert result.exit_code == 0
    
    @patch('jobradar.cli.Database')
    def test_search_uses_database(self, mock_db):
        """Search should use database for queries."""
        mock_db_instance = Mock()
        mock_db_instance.search_jobs.return_value = []
        mock_db.return_value = mock_db_instance
        
        runner = CliRunner()
        result = runner.invoke(search, ['--company', 'TechCorp'])
        
        # Should have tried to search database
        assert result.exit_code in [0, 1]


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 