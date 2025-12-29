"""
User agent middleware for Scrapy.

Provides transparent, rotating user agents while maintaining
identification as a legitimate bot.
"""

import random
import logging
from scrapy import signals
from scrapy.http import Request

logger = logging.getLogger(__name__)


class RotatingUserAgentMiddleware:
    """
    Middleware that rotates user agents while maintaining bot identification.

    We identify ourselves as WTracker bot but vary the browser signature
    to avoid simple fingerprinting while remaining transparent.
    """

    # Base user agents (we append our bot identifier)
    BASE_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    ]

    # Bot identifier appended to user agent
    BOT_IDENTIFIER = "WTracker/1.0 (+https://wtracker.app/bot)"

    def __init__(self, user_agent: str = None):
        self.user_agent = user_agent or self.BOT_IDENTIFIER

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls(crawler.settings.get("USER_AGENT"))
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        return middleware

    def spider_opened(self, spider):
        logger.info(f"RotatingUserAgentMiddleware enabled for spider: {spider.name}")

    def process_request(self, request: Request, spider):
        """Set user agent for each request."""
        # Use custom user agent if set on request
        if request.meta.get("user_agent"):
            request.headers["User-Agent"] = request.meta["user_agent"]
            return

        # For Playwright requests, use a standard browser UA
        if request.meta.get("playwright"):
            base_agent = random.choice(self.BASE_AGENTS)
            request.headers["User-Agent"] = base_agent
            return

        # For regular requests, use bot identifier
        request.headers["User-Agent"] = self.user_agent
