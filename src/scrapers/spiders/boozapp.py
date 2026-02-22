"""
Spider for BoozApp (boozapp.com).

MSRP plus secondary market expectations, bourbon-oriented.
Useful for sanity-checking hype pricing in North America.
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


class BoozAppSpider(scrapy.Spider):
    """
    Spider for scraping BoozApp price data.

    Site structure:
    - /browse - Browse all spirits
    - /spirit/{id} - Individual spirit pages
    - /search - Search functionality

    Provides MSRP and secondary market price expectations.
    """

    name = "boozapp"
    allowed_domains = ["boozapp.com", "www.boozapp.com"]

    start_urls = [
        "https://www.boozapp.com/browse/whiskey",
        "https://www.boozapp.com/browse/bourbon",
        "https://www.boozapp.com/browse/scotch",
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 4.0,
        "CONCURRENT_REQUESTS": 1,
        "ROBOTSTXT_OBEY": True,
    }

    def __init__(self, *args, scrape_run_id: int = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.scrape_run_id = scrape_run_id
        self.started_at = datetime.utcnow()
        self.items_scraped = 0
        self.items_errored = 0
        self.errors = []

    def start_requests(self):
        """Generate initial requests."""
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                errback=self.handle_error,
            )

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """Parse browse/category page."""
        logger.info(f"Parsing category: {response.url}")

        # Extract spirit links
        spirit_links = response.css("a[href*='/spirit/']::attr(href)").getall()
        spirit_links += response.css(".spirit-card a::attr(href)").getall()

        logger.info(f"Found {len(spirit_links)} spirit links")

        for link in set(spirit_links):
            full_url = urljoin(response.url, link)
            yield scrapy.Request(
                full_url,
                callback=self.parse_spirit,
                errback=self.handle_error,
            )

        # Pagination
        next_page = response.css("a.next::attr(href), a[rel='next']::attr(href)").get()
        if next_page:
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse,
                errback=self.handle_error,
            )

    def parse_spirit(self, response: Response) -> Generator[RetailPriceItem, None, None]:
        """Parse individual spirit page."""
        logger.debug(f"Parsing spirit: {response.url}")

        raw_title = response.css("h1::text, .spirit-name::text").get()
        if not raw_title:
            return

        raw_title = raw_title.strip()

        raw_description = " ".join(
            response.css(".spirit-description *::text, .details *::text").getall()
        ).strip()

        # Extract MSRP
        msrp = self._extract_msrp(response)

        # Extract secondary market price
        secondary_price = self._extract_secondary_price(response)

        # Create item for MSRP if available
        if msrp:
            item = self._create_item(
                response, raw_title, raw_description, msrp, "retail", "MSRP"
            )
            if item:
                yield item

        # Create item for secondary price if available
        if secondary_price:
            item = self._create_item(
                response, raw_title, raw_description, secondary_price, "secondary", "Secondary"
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
        price_type: str,
    ) -> RetailPriceItem | None:
        """Create a RetailPriceItem."""
        source_id = f"booz-{response.url.split('/')[-1]}-{price_type.lower()}"

        item = RetailPriceItem()

        # Source info
        item["source_id"] = source_id
        item["source_url"] = response.url
        item["source_name"] = f"BoozApp ({price_type})"
        item["source_type"] = source_type

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
        item["size_ml"] = extract_size_ml(full_text) or 750  # US default
        item["abv"] = extract_abv(full_text)

        # Determine country based on category
        if any(w in raw_title.lower() for w in ["bourbon", "rye", "tennessee"]):
            item["country"] = "USA"
        elif "scotch" in raw_title.lower():
            item["country"] = "Scotland"
        elif "japanese" in raw_title.lower():
            item["country"] = "Japan"

        # Price
        item["price"] = price
        item["currency"] = "USD"
        item["original_price"] = None

        # Availability
        item["in_stock"] = True

        # Image
        item["image_url"] = response.css(".spirit-image img::attr(src)").get()

        # Metadata
        item["scraped_at"] = datetime.utcnow().isoformat()
        item["spider_name"] = self.name

        # Processing flags
        item["normalization_confidence"] = 0.0
        item["matched_bottle_id"] = None
        item["requires_review"] = False
        item["is_duplicate"] = False

        self.items_scraped += 1
        return item

    def _extract_msrp(self, response: Response) -> float | None:
        """Extract MSRP from page."""
        selectors = [
            ".msrp::text",
            ".retail-price::text",
            "*[data-msrp]::attr(data-msrp)",
            ".price-msrp::text",
        ]

        for selector in selectors:
            price_text = response.css(selector).get()
            if price_text:
                price = parse_price(price_text)
                if price and price > 0:
                    return price

        # Try regex in page text
        page_text = " ".join(response.css("*::text").getall())
        match = re.search(r"MSRP[:\s]*\$?([\d,]+(?:\.\d{2})?)", page_text, re.IGNORECASE)
        if match:
            return parse_price(match.group(1))

        return None

    def _extract_secondary_price(self, response: Response) -> float | None:
        """Extract secondary market price from page."""
        selectors = [
            ".secondary-price::text",
            ".market-price::text",
            ".resale-price::text",
            "*[data-secondary]::attr(data-secondary)",
        ]

        for selector in selectors:
            price_text = response.css(selector).get()
            if price_text:
                price = parse_price(price_text)
                if price and price > 0:
                    return price

        # Try regex patterns
        page_text = " ".join(response.css("*::text").getall())
        patterns = [
            r"secondary[:\s]*\$?([\d,]+(?:\.\d{2})?)",
            r"resale[:\s]*\$?([\d,]+(?:\.\d{2})?)",
            r"market[:\s]*\$?([\d,]+(?:\.\d{2})?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return parse_price(match.group(1))

        return None

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
            f"  Items scraped: {self.items_scraped}"
        )

    def get_stats(self) -> dict:
        """Get spider statistics."""
        return {
            "spider_name": self.name,
            "scrape_run_id": self.scrape_run_id,
            "started_at": self.started_at.isoformat(),
            "items_scraped": self.items_scraped,
            "items_errored": self.items_errored,
            "errors": self.errors,
        }
