"""Tests for notification functionality."""
from typing import List
import os
import pytest
import requests_mock
import requests
from jobradar.notifiers.telegram import TelegramNotifier
from jobradar.notifiers.email_notifier import EmailNotifier
from jobradar.models import Job
from unittest.mock import patch, MagicMock
import smtplib

@pytest.fixture
def telegram_notifier(monkeypatch):
    with patch('jobradar.notifiers.telegram.get_config', return_value={
        'notifications': {
            'telegram': {
                'enabled': True,
                'bot_token': 'testtoken',
                'chat_id': '123456'
            }
        }
    }):
        return TelegramNotifier()

@pytest.fixture
def sample_jobs() -> List[Job]:
    """Create a list of sample jobs for testing.
    
    Returns:
        List[Job]: List of sample job objects
    """
    return [
        Job(
            id="1",
            title="Customer Support",
            company="ACME",
            url="https://example.com/job1",
            source="RemoteOK",
            date="2024-03-20"
        ),
        Job(
            id="2",
            title="Integration Engineer",
            company="TechCorp",
            url="https://example.com/job2",
            source="WorkingNomads",
            date="2024-03-20"
        )
    ]

@pytest.fixture
def email_config() -> dict:
    """Create email configuration for testing.
    
    Returns:
        dict: Email configuration
    """
    return {
        "enabled": True,
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "sender_email": "test@example.com",
        "recipient_email": "recipient@example.com",
        "password": "test_password"
    }

@pytest.fixture
def email_notifier(email_config: dict) -> EmailNotifier:
    """Create an EmailNotifier instance with test configuration.
    
    Args:
        email_config: Email configuration
        
    Returns:
        EmailNotifier: Email notifier instance
    """
    return EmailNotifier(email_config)

def test_telegram_notifier(requests_mock, telegram_notifier, sample_jobs):
    # Arrange
    requests_mock.post("https://api.telegram.org/bottesttoken/sendMessage", json={"ok": True})
    # Act
    response = telegram_notifier.notify(sample_jobs)
    assert response.json()["ok"] is True

def test_telegram_notifier_no_jobs(requests_mock: requests_mock.Mocker,
                                 telegram_notifier: TelegramNotifier) -> None:
    """Test handling of empty job list.
    
    Args:
        requests_mock: pytest fixture for mocking HTTP requests
        telegram_notifier: Telegram notifier instance
    """
    # Act & Assert
    with pytest.raises(ValueError, match="No jobs to notify"):
        telegram_notifier.notify([])

def test_telegram_notifier_missing_credentials():
    with patch('jobradar.notifiers.telegram.get_config', return_value={
        'notifications': {
            'telegram': {
                'enabled': True,
                'bot_token': None,
                'chat_id': None
            }
        }
    }):
        with pytest.raises(ValueError, match="Missing Telegram credentials"):
            TelegramNotifier()

def test_telegram_notifier_api_error(requests_mock, telegram_notifier, sample_jobs):
    requests_mock.post("https://api.telegram.org/bottesttoken/sendMessage", status_code=500)
    with pytest.raises(requests.exceptions.RequestException):
        telegram_notifier.notify(sample_jobs)

def test_email_notifier_disabled(sample_jobs: List[Job]) -> None:
    """Test that notifications are not sent when disabled."""
    # Arrange
    config = {"enabled": False}
    notifier = EmailNotifier(config)
    
    # Act & Assert
    notifier.notify(sample_jobs)  # Should not raise any exceptions

def test_email_notifier_empty_jobs(email_notifier: EmailNotifier) -> None:
    """Test handling of empty job list."""
    # Act & Assert
    email_notifier.notify([])  # Should not raise any exceptions

@patch('smtplib.SMTP')
def test_email_notifier_success(mock_smtp: MagicMock,
                              email_notifier: EmailNotifier,
                              sample_jobs: List[Job]) -> None:
    """Test successful email notification.
    
    Args:
        mock_smtp: Mocked SMTP client
        email_notifier: Email notifier instance
        sample_jobs: List of sample job objects
    """
    # Arrange
    mock_smtp_instance = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_smtp_instance
    
    # Act
    email_notifier.notify(sample_jobs)
    
    # Assert
    mock_smtp.assert_called_once_with("smtp.gmail.com", 587)
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("test@example.com", "test_password")
    mock_smtp_instance.sendmail.assert_called_once()
    
    # Verify email content
    call_args = mock_smtp_instance.sendmail.call_args[0]
    assert call_args[0] == "test@example.com"
    assert call_args[1] == "recipient@example.com"
    assert "Customer Support" in call_args[2]
    assert "Integration Engineer" in call_args[2]

@patch('smtplib.SMTP')
def test_email_notifier_smtp_error(mock_smtp: MagicMock,
                                 email_notifier: EmailNotifier,
                                 sample_jobs: List[Job]) -> None:
    """Test handling of SMTP errors.
    
    Args:
        mock_smtp: Mocked SMTP client
        email_notifier: Email notifier instance
        sample_jobs: List of sample job objects
    """
    # Arrange
    mock_smtp.return_value.__enter__.side_effect = smtplib.SMTPException("Test error")
    
    # Act & Assert
    with pytest.raises(smtplib.SMTPException):
        email_notifier.notify(sample_jobs) 