"""
Base spider class for WTracker auction scrapers.

Provides common functionality for all auction spiders:
- Statistics tracking
- Error handling
- Consistent item creation
- Playwright integration for JS sites
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Generator, Optional

import scrapy
from scrapy.http import Response

from src.scrapers.items import AuctionLotItem
from src.scrapers.utils.text import (
    clean_title,
    extract_age,
    extract_size_ml,
    extract_abv,
    extract_distillery,
    extract_vintage,
    extract_bottled_year,
    extract_cask_number,
)

logger = logging.getLogger(__name__)


class BaseAuctionSpider(scrapy.Spider, ABC):
    """
    Abstract base class for auction house spiders.

    Subclasses must implement:
    - name: Spider name
    - auction_house: Enum value for database
    - allowed_domains: List of allowed domains
    - start_urls: Initial URLs to crawl
    - parse(): Parse listing pages
    - parse_lot(): Parse individual lot pages
    """

    # Subclasses must define these
    name: str = None
    auction_house: str = None  # Value from AuctionHouse enum
    allowed_domains: list = []
    start_urls: list = []

    # Default settings (can be overridden by subclass)
    custom_settings = {
        "DOWNLOAD_DELAY": 3.0,
        "CONCURRENT_REQUESTS": 1,
    }

    def __init__(self, *args, scrape_run_id: int = None, **kwargs):
        """
        Initialize spider.

        Args:
            scrape_run_id: Database ID for tracking this run
            **kwargs: Standard Scrapy spider arguments
        """
        super().__init__(*args, **kwargs)

        # Run tracking
        self.scrape_run_id = scrape_run_id
        self.started_at = datetime.utcnow()

        # Statistics
        self.items_scraped = 0
        self.items_new = 0
        self.items_updated = 0
        self.items_skipped = 0
        self.items_errored = 0
        self.errors: list = []

        logger.info(f"Initialized spider {self.name} (run_id: {scrape_run_id})")

    @abstractmethod
    def parse(self, response: Response) -> Generator[Any, None, None]:
        """
        Parse auction listing page.

        Should yield:
        - scrapy.Request for individual lot pages
        - scrapy.Request for pagination (next page)
        """
        pass

    @abstractmethod
    def parse_lot(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """
        Parse individual lot page.

        Should yield:
        - AuctionLotItem with extracted data
        """
        pass

    def create_item(
        self,
        response: Response,
        source_id: str,
        raw_title: str,
        raw_description: str = "",
        **kwargs,
    ) -> AuctionLotItem:
        """
        Create an AuctionLotItem with common fields populated.

        Automatically extracts:
        - Distillery
        - Age statement
        - Size
        - ABV
        - Vintage
        - Bottled year
        - Cask number

        Args:
            response: Scrapy response object
            source_id: Unique ID from auction source
            raw_title: Original lot title
            raw_description: Original lot description
            **kwargs: Additional item fields

        Returns:
            Populated AuctionLotItem
        """
        item = AuctionLotItem()

        # Source identification
        item["source_id"] = source_id
        item["source_url"] = response.url
        item["auction_house"] = self.auction_house
        item["spider_name"] = self.name
        item["scraped_at"] = datetime.utcnow().isoformat()

        # Raw content
        item["raw_title"] = raw_title
        item["raw_description"] = raw_description

        # Clean the title for normalization
        item["bottle_name"] = clean_title(raw_title)

        # Auto-extract structured data from title + description
        full_text = f"{raw_title} {raw_description}"

        # Distillery and region
        distillery, region = extract_distillery(full_text)
        item["distillery"] = distillery

        # Bottle specifications
        item["age_statement"] = extract_age(full_text)
        item["size_ml"] = extract_size_ml(full_text) or 700  # Default 700ml
        item["abv"] = extract_abv(full_text)
        if item["abv"]:
            item["proof"] = item["abv"] * 2

        # Dating
        item["vintage"] = extract_vintage(full_text)
        item["bottled_year"] = extract_bottled_year(full_text)
        item["cask_number"] = extract_cask_number(full_text)

        # Default bottle count
        item["bottle_count"] = 1

        # Processing flags (set by pipelines)
        item["normalization_confidence"] = 0.0
        item["matched_bottle_id"] = None
        item["requires_review"] = False
        item["validation_errors"] = []
        item["is_duplicate"] = False

        # Merge any additional fields
        for key, value in kwargs.items():
            item[key] = value

        return item

    def handle_error(self, failure):
        """
        Handle request failures.

        Logs the error and tracks it for the scrape run record.
        """
        request = failure.request
        error_msg = str(failure.value)

        logger.error(f"Request failed: {request.url} - {error_msg}")

        self.items_errored += 1
        self.errors.append({
            "url": request.url,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def closed(self, reason: str):
        """
        Called when spider closes.

        Logs final statistics.
        """
        duration = (datetime.utcnow() - self.started_at).total_seconds()

        logger.info(
            f"Spider {self.name} closed: {reason}\n"
            f"  Duration: {duration:.1f}s\n"
            f"  Items scraped: {self.items_scraped}\n"
            f"  Items new: {self.items_new}\n"
            f"  Items updated: {self.items_updated}\n"
            f"  Items skipped: {self.items_skipped}\n"
            f"  Errors: {self.items_errored}"
        )

    def get_stats(self) -> dict:
        """Get current spider statistics."""
        return {
            "spider_name": self.name,
            "scrape_run_id": self.scrape_run_id,
            "started_at": self.started_at.isoformat(),
            "items_scraped": self.items_scraped,
            "items_new": self.items_new,
            "items_updated": self.items_updated,
            "items_skipped": self.items_skipped,
            "items_errored": self.items_errored,
            "errors": self.errors,
        }
