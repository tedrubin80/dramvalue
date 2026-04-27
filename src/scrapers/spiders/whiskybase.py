"""
Spider for Whiskybase Market (whiskybase.com/market).

Peer-to-peer marketplace with listing prices and large bottle database.
"""

import re
import logging
from datetime import datetime
from typing import Generator, Any
from urllib.parse import urljoin, urlencode

import scrapy
from scrapy.http import Response

from src.scrapers.items import RetailPriceItem
from src.scrapers.utils.text import (
    clean_title,
    extract_age,
    extract_size_ml,
    extract_abv,
    extract_distillery,
    parse_price,
)

logger = logging.getLogger(__name__)


class WhiskybaseSpider(scrapy.Spider):
    """
    Spider for scraping Whiskybase Market listings.

    Site structure:
    - /market - Main marketplace
    - /market/search - Search results
    - /whiskies/{id} - Individual whisky pages
    - /market/listing/{id} - Individual listings

    Note: Uses RetailPriceItem as this is marketplace (ask) pricing.
    """

    name = "whiskybase"
    allowed_domains = ["whiskybase.com", "www.whiskybase.com"]

    # Start with market search sorted by recently added
    start_urls = [
        "https://www.whiskybase.com/market?sort=latest",
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 5.0,
        "CONCURRENT_REQUESTS": 1,
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 90000,
        "ROBOTSTXT_OBEY": True,
    }

    def __init__(self, *args, scrape_run_id: int = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.scrape_run_id = scrape_run_id
        self.started_at = datetime.utcnow()
        self.items_scraped = 0
        self.items_new = 0
        self.items_updated = 0
        self.items_skipped = 0
        self.items_errored = 0
        self.errors = []

    def start_requests(self):
        """Generate initial requests with Playwright."""
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                meta={},
                errback=self.handle_error,
            )

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """Parse market listings page."""
        logger.info(f"Parsing market: {response.url}")

        # Extract listing links
        listing_links = response.css("a[href*='/market/listing/']::attr(href)").getall()
        whisky_links = response.css("a[href*='/whiskies/']::attr(href)").getall()

        all_links = set(listing_links + whisky_links)
        logger.info(f"Found {len(all_links)} listing/whisky links")

        for link in all_links:
            full_url = urljoin(response.url, link)

            if "/market/listing/" in link:
                yield scrapy.Request(
                    full_url,
                    callback=self.parse_listing,
                    meta={},
                    errback=self.handle_error,
                )
            elif "/whiskies/" in link:
                yield scrapy.Request(
                    full_url,
                    callback=self.parse_whisky,
                    meta={},
                    errback=self.handle_error,
                )

        # Pagination
        next_page = response.css("a.next::attr(href), a[rel='next']::attr(href)").get()
        if not next_page:
            next_page = response.css(".pagination a:contains('Next')::attr(href)").get()

        if next_page:
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse,
                meta={},
                errback=self.handle_error,
            )

    def parse_whisky(self, response: Response) -> Generator[Any, None, None]:
        """Parse whisky page to get market listings."""
        logger.debug(f"Parsing whisky page: {response.url}")

        # Extract listing links from whisky page
        listing_links = response.css("a[href*='/market/listing/']::attr(href)").getall()

        for link in set(listing_links):
            full_url = urljoin(response.url, link)
            yield scrapy.Request(
                full_url,
                callback=self.parse_listing,
                meta={
                    "whisky_url": response.url,
                },
                errback=self.handle_error,
            )

    def parse_listing(self, response: Response) -> Generator[RetailPriceItem, None, None]:
        """Parse individual market listing."""
        logger.debug(f"Parsing listing: {response.url}")

        source_id = self._extract_listing_id(response.url)
        if not source_id:
            return

        raw_title = response.css("h1::text, .listing-title::text").get()
        if not raw_title:
            raw_title = response.css(".whisky-name::text").get()

        if not raw_title:
            return

        raw_title = raw_title.strip()

        raw_description = " ".join(
            response.css(".listing-description *::text, .whisky-details *::text").getall()
        ).strip()

        item = RetailPriceItem()

        # Source info
        item["source_id"] = source_id
        item["source_url"] = response.url
        item["source_name"] = "Whiskybase"
        item["source_type"] = "secondary"

        # Raw content
        item["raw_title"] = raw_title
        item["raw_description"] = raw_description

        # Clean title
        item["bottle_name"] = clean_title(raw_title)

        # Extract bottle info
        full_text = f"{raw_title} {raw_description}"
        distillery, region = extract_distillery(full_text)
        item["distillery"] = distillery
        item["region"] = region
        item["age_statement"] = extract_age(full_text)
        item["size_ml"] = extract_size_ml(full_text) or 700
        item["abv"] = extract_abv(full_text)

        # Price
        item["price"] = self._extract_price(response)
        item["currency"] = self._detect_currency(response)
        item["original_price"] = None

        # Availability
        item["in_stock"] = self._check_availability(response)

        # Image
        item["image_url"] = response.css(".listing-image img::attr(src), .whisky-image img::attr(src)").get()

        # Metadata
        item["scraped_at"] = datetime.utcnow().isoformat()
        item["spider_name"] = self.name

        # Processing flags
        item["normalization_confidence"] = 0.0
        item["matched_bottle_id"] = None
        item["requires_review"] = False
        item["is_duplicate"] = False

        self.items_scraped += 1
        yield item

    def _extract_listing_id(self, url: str) -> str | None:
        """Extract listing ID from URL."""
        match = re.search(r"/listing/(\d+)", url)
        if match:
            return f"wb-{match.group(1)}"
        return None

    def _extract_price(self, response: Response) -> float | None:
        """Extract price from listing."""
        selectors = [
            ".listing-price::text",
            ".price::text",
            ".asking-price::text",
            "*[itemprop='price']::attr(content)",
        ]

        for selector in selectors:
            price_text = response.css(selector).get()
            if price_text:
                price = parse_price(price_text)
                if price and price > 0:
                    return price

        return None

    def _detect_currency(self, response: Response) -> str:
        """Detect currency from page."""
        page_text = " ".join(response.css(".price *::text, .listing-price *::text").getall())
        if "€" in page_text:
            return "EUR"
        elif "£" in page_text:
            return "GBP"
        elif "$" in page_text:
            return "USD"
        return "EUR"  # Default

    def _check_availability(self, response: Response) -> bool:
        """Check if listing is available."""
        page_text = " ".join(response.css("*::text").getall()).lower()
        sold_indicators = ["sold", "unavailable", "no longer available"]
        return not any(ind in page_text for ind in sold_indicators)

    def handle_error(self, failure):
        """Handle request failures."""
        logger.error(f"Request failed: {failure.request.url} - {failure.value}")
        self.items_errored += 1
        self.errors.append({
            "url": failure.request.url,
            "error": str(failure.value),
            "timestamp": datetime.utcnow().isoformat(),
        })

    def closed(self, reason: str):
        """Spider closed callback."""
        duration = (datetime.utcnow() - self.started_at).total_seconds()
        logger.info(
            f"Spider {self.name} closed: {reason}\n"
            f"  Duration: {duration:.1f}s\n"
            f"  Items scraped: {self.items_scraped}\n"
            f"  Errors: {self.items_errored}"
        )

    def get_stats(self) -> dict:
        """Get spider statistics."""
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
