"""
WTracker Web Scrapers.

This module contains Scrapy spiders and pipelines for scraping
auction and retail whisky price data.

Supported sources:
- Whisky Auctioneer (whiskyauctioneer.com)
- Scotch Whisky Auctions (scotchwhiskyauctions.com)

Usage:
    # Run spider from command line
    scrapy crawl whisky_auctioneer -s SCRAPY_SETTINGS_MODULE=src.scrapers.settings

    # Run via Celery task
    from src.tasks.scraping import scrape_source
    scrape_source.delay("whisky_auctioneer")
"""
