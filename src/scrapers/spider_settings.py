"""
Shared Scrapy custom_settings for spider types.

Retail/API spiders must bypass the global Playwright download handler
and Tor proxy — those are only needed for JS-heavy auction sites.
"""

HTTP_ONLY_SETTINGS = {
    "DOWNLOAD_HANDLERS": {
        "http": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
        "https": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
    },
    "TWISTED_REACTOR": "twisted.internet.selectreactor.SelectReactor",
}
