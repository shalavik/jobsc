"""Job notification system."""

from .base import Notifier
from .email import EmailNotifier

__all__ = ['Notifier', 'EmailNotifier'] 