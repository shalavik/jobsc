"""Email notification functionality."""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any
from ..models import Job

class EmailNotifier:
    """Sends job notifications via email."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the notifier with email config."""
        self.enabled = config.get("enabled", False)
        self.smtp_server = config.get("smtp_server")
        self.smtp_port = config.get("smtp_port")
        self.sender_email = config.get("sender_email")
        self.recipient_email = config.get("recipient_email")
        self.password = config.get("password", None)  # Optional, for login

    def notify(self, jobs: List[Job]) -> None:
        """Send job notifications via email."""
        if not self.enabled or not jobs:
            return

        msg = MIMEMultipart()
        msg["Subject"] = f"New Job Openings ({len(jobs)})"
        msg["From"] = self.sender_email
        msg["To"] = self.recipient_email

        body = "\n\n".join(
            f"{job.title} at {job.company}\n{job.url}\nSource: {job.source}\nDate: {job.date}"
            for job in jobs
        )
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            if self.password:
                server.login(self.sender_email, self.password)
            server.sendmail(self.sender_email, self.recipient_email, msg.as_string()) 