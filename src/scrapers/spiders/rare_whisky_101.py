"""
Spider for Rare Whisky 101 (rarewhisky101.com).

Provides Icon 100 and other indices for collectible Scotch at UK auctions.
"""

import re
import logging
from datetime import datetime
from typing import Generator, Any
from urllib.parse import urljoin

import scrapy
from scrapy.http import Response

from src.scrapers.spiders.base import BaseAuctionSpider
from src.scrapers.items import AuctionLotItem
from src.scrapers.utils.text import parse_price

logger = logging.getLogger(__name__)


class RareWhisky101Spider(BaseAuctionSpider):
    """
    Spider for scraping Rare Whisky 101 index data.

    Site structure:
    - /indices - Market indices (Icon 100, etc.)
    - /data - Historical data downloads
    - /bottles - Individual bottle tracking

    Focuses on collectible and investment-grade Scotch whisky.
    """

    name = "rare_whisky_101"
    auction_house = "RARE_WHISKY_101"
    allowed_domains = ["rarewhisky101.com", "www.rarewhisky101.com"]

    start_urls = [
        "https://www.rarewhisky101.com/indices",
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 5.0,
        "CONCURRENT_REQUESTS": 1,
        "ROBOTSTXT_OBEY": True,
    }

    def start_requests(self):
        """Generate initial requests."""
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                errback=self.handle_error,
            )

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """Parse indices/main page."""
        logger.info(f"Parsing indices: {response.url}")

        # Extract links to individual indices or bottle data
        index_links = response.css("a[href*='/index/']::attr(href)").getall()
        bottle_links = response.css("a[href*='/bottle/']::attr(href)").getall()
        data_links = response.css("a[href*='/data/']::attr(href)").getall()

        all_links = set(index_links + bottle_links + data_links)
        logger.info(f"Found {len(all_links)} links")

        for link in index_links:
            full_url = urljoin(response.url, link)
            yield scrapy.Request(
                full_url,
                callback=self.parse_index,
                errback=self.handle_error,
            )

        for link in bottle_links:
            full_url = urljoin(response.url, link)
            yield scrapy.Request(
                full_url,
                callback=self.parse_lot,
                errback=self.handle_error,
            )

    def parse_index(self, response: Response) -> Generator[Any, None, None]:
        """Parse index page to extract constituent bottles."""
        index_name = response.css("h1::text").get("").strip()
        logger.info(f"Parsing index: {index_name}")

        # Extract bottle links from index
        bottle_links = response.css("a[href*='/bottle/']::attr(href)").getall()
        bottle_links += response.css(".constituent a::attr(href)").getall()

        for link in set(bottle_links):
            full_url = urljoin(response.url, link)
            yield scrapy.Request(
                full_url,
                callback=self.parse_lot,
                meta={"index_name": index_name},
                errback=self.handle_error,
            )

    def parse_lot(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """Parse individual bottle page with price data."""
        logger.debug(f"Parsing bottle: {response.url}")

        raw_title = response.css("h1::text, .bottle-name::text").get()
        if not raw_title:
            return

        raw_title = raw_title.strip()

        raw_description = " ".join(
            response.css(".bottle-description *::text, .details *::text").getall()
        ).strip()

        # Extract price data points
        price_entries = response.css(".price-history tr, .auction-result, .price-point")

        for idx, entry in enumerate(price_entries):
            date_text = entry.css("td:first-child::text, .date::text").get()
            auction_date = self._parse_date(date_text) if date_text else None

            price_text = entry.css("td:nth-child(2)::text, .price::text").get()
            if not price_text:
                continue

            hammer_price = parse_price(price_text)
            if not hammer_price or hammer_price <= 0:
                continue

            source_id = f"rw101-{response.url.split('/')[-1]}-{idx}"

            item = self.create_item(
                response=response,
                source_id=source_id,
                raw_title=raw_title,
                raw_description=raw_description,
            )

            item["hammer_price"] = hammer_price
            item["total_price"] = hammer_price
            item["currency"] = "GBP"
            item["auction_date"] = auction_date
            item["auction_name"] = response.meta.get("index_name", "Rare Whisky 101")
            item["sold"] = True

            self.items_scraped += 1
            yield item

        # If no history, get current value
        if not price_entries:
            current_value = self._extract_current_value(response)
            if current_value:
                source_id = f"rw101-{response.url.split('/')[-1]}-current"

                item = self.create_item(
                    response=response,
                    source_id=source_id,
                    raw_title=raw_title,
                    raw_description=raw_description,
                )

                item["hammer_price"] = current_value
                item["total_price"] = current_value
                item["currency"] = "GBP"
                item["auction_name"] = "Rare Whisky 101"
                item["sold"] = True

                self.items_scraped += 1
                yield item

    def _extract_current_value(self, response: Response) -> float | None:
        """Extract current/average value."""
        selectors = [
            ".current-value::text",
            ".index-value::text",
            ".average-price::text",
        ]

        for selector in selectors:
            price_text = response.css(selector).get()
            if price_text:
                price = parse_price(price_text)
                if price and price > 0:
                    return price

        return None

    def _parse_date(self, date_text: str) -> str | None:
        """Parse date to ISO format."""
        if not date_text:
            return None

        date_text = date_text.strip()

        if re.match(r"\d{4}-\d{2}-\d{2}", date_text):
            return date_text[:10]

        from dateutil import parser
        try:
            parsed = parser.parse(date_text, dayfirst=True)
            return parsed.strftime("%Y-%m-%d")
        except Exception:
            return None
