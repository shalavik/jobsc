"""Email notifier for job alerts."""
import logging
from typing import List
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .base import Notifier
from jobradar.domain.job import Job

logger = logging.getLogger(__name__)

class EmailNotifier(Notifier):
    """Email notifier for job alerts."""
    
    def __init__(self, config: dict):
        """Initialize the email notifier.
        
        Args:
            config: Configuration dictionary with SMTP settings
        """
        super().__init__(config)
        self.smtp_host = config.get('smtp_host', 'smtp.gmail.com')
        self.smtp_port = config.get('smtp_port', 587)
        self.smtp_user = config.get('smtp_user')
        self.smtp_password = config.get('smtp_password')
        self.recipient = config.get('recipient')
        
        if not all([self.smtp_user, self.smtp_password, self.recipient]):
            raise ValueError("SMTP user, password, and recipient are required")
    
    async def notify(self, jobs: List[Job]) -> bool:
        """Send email notification about new jobs.
        
        Args:
            jobs: List of jobs to notify about
            
        Returns:
            True if notification was successful
        """
        if not jobs:
            return True
            
        try:
            # Create message
            msg = MIMEMultipart()
            msg['Subject'] = f"New Job Alerts ({len(jobs)} jobs)"
            msg['From'] = self.smtp_user
            msg['To'] = self.recipient
            
            # Create HTML content
            html_content = "<html><body>"
            html_content += "<h1>New Job Alerts</h1>"
            
            for job in jobs:
                html_content += "<div style='margin-bottom: 20px; padding: 10px; border: 1px solid #ddd;'>"
                html_content += f"<h2>{job.title}</h2>"
                html_content += f"<p><strong>Company:</strong> {job.company}</p>"
                html_content += f"<p><strong>Location:</strong> {job.location}</p>"
                
                if job.salary_range:
                    html_content += f"<p><strong>Salary:</strong> {job.salary_range}</p>"
                    
                if job.job_type:
                    html_content += f"<p><strong>Type:</strong> {job.job_type}</p>"
                    
                if job.experience_level:
                    html_content += f"<p><strong>Experience:</strong> {job.experience_level}</p>"
                    
                if job.remote:
                    html_content += "<p><strong>Remote:</strong> Yes</p>"
                    
                html_content += f"<p><a href='{job.url}'>View Job</a></p>"
                html_content += "</div>"
            
            html_content += "</body></html>"
            
            msg.attach(MIMEText(html_content, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
                
            logger.info(f"Sent email notification with {len(jobs)} jobs to {self.recipient}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email notification: {str(e)}")
            return False 