"""
Spider for WhiskyFindr (whiskyfindr.com).

US-focused bourbon/whisky price comparison across retailers.
Tracks retail prices and secondary market values.
"""

import re
import logging
from datetime import datetime
from typing import Generator, Any
from urllib.parse import urljoin

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


class WhiskyFindrSpider(scrapy.Spider):
    """
    Spider for scraping WhiskyFindr price data.

    Site structure:
    - /most-traded-bourbon - Most actively traded bottles
    - /bourbon-price-drops - Recent price drops
    - /bourbon-release-calendar - Upcoming releases
    - Individual bottle pages with price comparisons

    Focuses on US bourbon market with retail and secondary prices.
    """

    name = "whiskyfindr"
    allowed_domains = ["whiskyfindr.com", "www.whiskyfindr.com"]

    start_urls = [
        "https://whiskyfindr.com/most-traded-bourbon",
        "https://whiskyfindr.com/bourbon-price-drops",
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 5.0,
        "CONCURRENT_REQUESTS": 1,
        "ROBOTSTXT_OBEY": True,
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 60000,
    }

    def __init__(self, *args, scrape_run_id: int = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.scrape_run_id = scrape_run_id
        self.started_at = datetime.utcnow()
        self.items_scraped = 0
        self.items_errored = 0
        self.errors = []

    def start_requests(self):
        """Generate initial requests with Playwright for JS rendering."""
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                meta={
                    "playwright": True,
                    "playwright_include_page": False,
                    "playwright_page_goto_kwargs": {
                        "wait_until": "networkidle",
                        "timeout": 60000,
                    },
                },
                errback=self.handle_error,
            )

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """Parse listing page (most traded, price drops, etc.)."""
        logger.info(f"Parsing: {response.url}")

        # Extract bottle links
        bottle_links = response.css("a[href*='/bottle/']::attr(href)").getall()
        bottle_links += response.css("a[href*='/bourbon/']::attr(href)").getall()
        bottle_links += response.css("a[href*='/whisky/']::attr(href)").getall()

        logger.info(f"Found {len(bottle_links)} bottle links")

        for link in set(bottle_links):
            full_url = urljoin(response.url, link)
            yield scrapy.Request(
                full_url,
                callback=self.parse_bottle,
                meta={
                    "playwright": True,
                    "playwright_include_page": False,
                    "playwright_page_goto_kwargs": {
                        "wait_until": "networkidle",
                        "timeout": 60000,
                    },
                },
                errback=self.handle_error,
            )

        # Pagination
        next_page = response.css("a[rel='next']::attr(href), a.next::attr(href)").get()
        if next_page:
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse,
                meta={
                    "playwright": True,
                    "playwright_include_page": False,
                    "playwright_page_goto_kwargs": {
                        "wait_until": "networkidle",
                        "timeout": 60000,
                    },
                },
                errback=self.handle_error,
            )

    def parse_bottle(self, response: Response) -> Generator[RetailPriceItem, None, None]:
        """Parse individual bottle page with prices from multiple retailers."""
        logger.debug(f"Parsing bottle: {response.url}")

        raw_title = response.css("h1::text").get()
        if not raw_title:
            raw_title = response.css(".bottle-name::text, .product-title::text").get()

        if not raw_title:
            return

        raw_title = raw_title.strip()

        raw_description = " ".join(
            response.css(".bottle-description *::text, .product-info *::text").getall()
        ).strip()

        # Extract retail prices from different stores
        price_rows = response.css(".price-row, .retailer-price, .store-price")

        if price_rows:
            for row in price_rows:
                retailer = row.css(".retailer-name::text, .store-name::text").get("").strip()
                price = self._extract_row_price(row)

                if price and price > 0:
                    item = self._create_item(
                        response, raw_title, raw_description,
                        price, "retail", retailer
                    )
                    if item:
                        yield item
        else:
            # Single price display
            retail_price = self._extract_price(response, "retail")
            if retail_price:
                item = self._create_item(
                    response, raw_title, raw_description,
                    retail_price, "retail", ""
                )
                if item:
                    yield item

        # Extract secondary market price
        secondary_price = self._extract_price(response, "secondary")
        if secondary_price:
            item = self._create_item(
                response, raw_title, raw_description,
                secondary_price, "secondary", "Secondary Market"
            )
            if item:
                yield item

    def _create_item(
        self,
        response: Response,
        raw_title: str,
        raw_description: str,
        price: float,
        source_type: str,
        retailer: str,
    ) -> RetailPriceItem | None:
        """Create a RetailPriceItem."""
        retailer_slug = re.sub(r"[^a-z0-9]", "", retailer.lower())[:20] if retailer else "wf"
        source_id = f"wf-{response.url.split('/')[-1][:30]}-{retailer_slug}"

        item = RetailPriceItem()

        item["source_id"] = source_id
        item["source_url"] = response.url
        item["source_name"] = f"WhiskyFindr ({retailer})" if retailer else "WhiskyFindr"
        item["source_type"] = source_type

        item["raw_title"] = raw_title
        item["raw_description"] = raw_description
        item["bottle_name"] = clean_title(raw_title)

        full_text = f"{raw_title} {raw_description}"
        distillery, region = extract_distillery(full_text)
        item["distillery"] = distillery
        item["region"] = region
        item["age_statement"] = extract_age(full_text)
        item["size_ml"] = extract_size_ml(full_text) or 750  # US default
        item["abv"] = extract_abv(full_text)
        item["country"] = "USA"  # WhiskyFindr focuses on US market

        item["price"] = price
        item["currency"] = "USD"
        item["original_price"] = None
        item["in_stock"] = True

        item["image_url"] = response.css(".bottle-image img::attr(src)").get()
        item["scraped_at"] = datetime.utcnow().isoformat()
        item["spider_name"] = self.name

        item["normalization_confidence"] = 0.0
        item["matched_bottle_id"] = None
        item["requires_review"] = False
        item["is_duplicate"] = False

        self.items_scraped += 1
        return item

    def _extract_price(self, response: Response, price_type: str) -> float | None:
        """Extract price by type (retail or secondary)."""
        if price_type == "secondary":
            selectors = [
                ".secondary-price::text",
                ".resale-price::text",
                ".market-value::text",
                "*[data-secondary]::attr(data-secondary)",
            ]
        else:
            selectors = [
                ".retail-price::text",
                ".msrp::text",
                ".price::text",
                "*[data-price]::attr(data-price)",
            ]

        for selector in selectors:
            price_text = response.css(selector).get()
            if price_text:
                price = parse_price(price_text)
                if price and price > 0:
                    return price

        return None

    def _extract_row_price(self, row) -> float | None:
        """Extract price from a retailer row."""
        price_text = row.css(".price::text, .amount::text").get()
        if price_text:
            return parse_price(price_text)
        return None

    def handle_error(self, failure):
        logger.error(f"Request failed: {failure.request.url} - {failure.value}")
        self.items_errored += 1
        self.errors.append({
            "url": failure.request.url,
            "error": str(failure.value),
            "timestamp": datetime.utcnow().isoformat(),
        })

    def closed(self, reason: str):
        duration = (datetime.utcnow() - self.started_at).total_seconds()
        logger.info(f"Spider {self.name} closed: {reason}, items: {self.items_scraped}")

    def get_stats(self) -> dict:
        return {
            "spider_name": self.name,
            "scrape_run_id": self.scrape_run_id,
            "started_at": self.started_at.isoformat(),
            "items_scraped": self.items_scraped,
            "items_errored": self.items_errored,
            "errors": self.errors,
        }
