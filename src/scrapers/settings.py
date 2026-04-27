"""
Scrapy settings for WTracker auction scrapers.

Integrates with FastAPI app configuration for consistent settings.
"""

import os

# Try to load from app config, fall back to defaults
try:
    from src.core.config import get_settings
    app_settings = get_settings()
    USER_AGENT = app_settings.scraper_user_agent
    ROBOTSTXT_OBEY = app_settings.scraper_respect_robots_txt
    DEBUG = app_settings.debug
except Exception:
    USER_AGENT = "WTracker/1.0 (Educational Project)"
    ROBOTSTXT_OBEY = True
    DEBUG = False

# Scrapy core settings
BOT_NAME = "wtracker"
SPIDER_MODULES = ["src.scrapers.spiders"]
NEWSPIDER_MODULE = "src.scrapers.spiders"

# Crawl responsibly - identify ourselves
USER_AGENT = USER_AGENT

# Obey robots.txt rules
ROBOTSTXT_OBEY = ROBOTSTXT_OBEY

# Configure maximum concurrent requests
CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1

# Configure a delay for requests to the same website
DOWNLOAD_DELAY = 3.0  # 3 seconds between requests
RANDOMIZE_DOWNLOAD_DELAY = True  # Random delay between 1.5-4.5 seconds

# Disable cookies (unless needed for specific sites)
COOKIES_ENABLED = True

# Disable Telnet Console (security)
TELNETCONSOLE_ENABLED = False

# Override default request headers (realistic browser headers)
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# Enable AutoThrottle for adaptive rate limiting
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 3
AUTOTHROTTLE_MAX_DELAY = 30
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
AUTOTHROTTLE_DEBUG = DEBUG

# Retry configuration
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

# Configure item pipelines (order matters - lower number runs first)
ITEM_PIPELINES = {
    "src.scrapers.pipelines.validation.ValidationPipeline": 100,
    "src.scrapers.pipelines.normalization.NormalizationPipeline": 200,
    "src.scrapers.pipelines.deduplication.DeduplicationPipeline": 300,
    "src.scrapers.pipelines.database.DatabasePipeline": 400,
}

# Enable and configure downloader middlewares
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "src.scrapers.middlewares.user_agent.RotatingUserAgentMiddleware": 400,
}

# Logging configuration
LOG_LEVEL = "DEBUG" if DEBUG else "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# Playwright settings for JavaScript-rendered sites
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
PLAYWRIGHT_BROWSER_TYPE = "chromium"

# Tor SOCKS5 proxy configuration (docker-compose service name is `tor`)
TOR_PROXY_HOST = os.getenv("TOR_PROXY_HOST", "tor")
TOR_PROXY_PORT = os.getenv("TOR_PROXY_PORT", "9050")
USE_TOR_PROXY = os.getenv("USE_TOR_PROXY", "true").lower() == "true"

PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "timeout": 60000,  # Increased timeout for Tor
    # Proxy configuration for Tor
    "proxy": {
        "server": f"socks5://{TOR_PROXY_HOST}:{TOR_PROXY_PORT}"
    } if USE_TOR_PROXY else None,
    # Anti-detection settings
    "args": [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
    ],
}

# Remove None proxy if not using Tor
if not USE_TOR_PROXY and "proxy" in PLAYWRIGHT_LAUNCH_OPTIONS:
    del PLAYWRIGHT_LAUNCH_OPTIONS["proxy"]

# Context options for more realistic browser fingerprint
PLAYWRIGHT_CONTEXTS = {
    "default": {
        "viewport": {"width": 1920, "height": 1080},
        "locale": "en-GB",
        "timezone_id": "Europe/London",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
}

# Request fingerprinting (for deduplication)
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

# Database URL (used by database pipeline)
try:
    DATABASE_URL = str(app_settings.database_url)
except Exception:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://wtracker:wtracker_dev_password_2024@db:5432/wtracker"
    )

# Feed exports (optional - for debugging)
# FEEDS = {
#     "output/%(name)s_%(time)s.json": {
#         "format": "json",
#         "encoding": "utf8",
#         "store_empty": False,
#     },
# }
