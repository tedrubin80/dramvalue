"""
Celery tasks for WTracker background processing.

Task modules:
- scraping: Spider execution and scheduling
- maintenance: Statistics refresh and cleanup
"""

from src.tasks.celery_app import celery_app

__all__ = ["celery_app"]
