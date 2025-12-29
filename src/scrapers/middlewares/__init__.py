"""
Scrapy downloader middlewares for WTracker.

Middlewares:
- RotatingUserAgentMiddleware: Rotates user agents to avoid detection
"""

from src.scrapers.middlewares.user_agent import RotatingUserAgentMiddleware

__all__ = ["RotatingUserAgentMiddleware"]
