"""Telegram notification functionality."""
import os
from typing import List
import requests
from ..models import Job
from ..config import get_config

class TelegramNotifier:
    """Sends job notifications via Telegram."""
    
    def __init__(self):
        """Initialize the notifier.
        
        Raises:
            ValueError: If Telegram credentials are missing
        """
        config = get_config()
        telegram_config = config.get('notifications', {}).get('telegram', {})
        
        if not telegram_config.get('enabled'):
            raise ValueError("Telegram notifications are disabled")
            
        self.token = telegram_config.get('bot_token')
        self.chat_id = telegram_config.get('chat_id')
        
        if not self.token or not self.chat_id:
            raise ValueError("Missing Telegram credentials (bot_token, chat_id)")
    
    def notify(self, jobs: List[Job]) -> requests.Response:
        """Send job notifications.
        
        Args:
            jobs: List of jobs to notify about
            
        Returns:
            Response from Telegram API
            
        Raises:
            ValueError: If jobs list is empty
            requests.exceptions.RequestException: If the request fails
        """
        if not jobs:
            raise ValueError("No jobs to notify")
        
        # Format message
        message = self._format_message(jobs)
        
        # Send to Telegram
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, json=data)
        response.raise_for_status()
        
        return response
    
    def _format_message(self, jobs: List[Job]) -> str:
        """Format jobs into a Telegram message.
        
        Args:
            jobs: List of jobs to format
            
        Returns:
            Formatted message string
        """
        lines = ["*New Job Openings*"]
        
        for job in jobs:
            lines.extend([
                f"*{job.title}* at {job.company}",
                f"Source: {job.source}",
                f"Link: {job.url}",
                ""
            ])
        
        return "\n".join(lines) 