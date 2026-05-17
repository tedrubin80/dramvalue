"""
Spider for WhiskyAuction.com (whiskyauction.com).

Online whisky auction platform with historical price browser.
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


class WhiskyAuctionComSpider(BaseAuctionSpider):
    """
    Spider for scraping WhiskyAuction.com results.

    Site structure:
    - /auctions - Current and past auctions
    - /archive - Historical auction data
    - /lot/{id} - Individual lot pages
    """

    name = "whiskyauction_com"
    auction_house = "WHISKYAUCTION_COM"
    allowed_domains = ["whiskyauction.com", "www.whiskyauction.com"]

    start_urls = [
        "https://www.whiskyauction.com/wac/auctionBrowser",
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 4.0,
        "CONCURRENT_REQUESTS": 1,
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 90000,
    }

    DEFAULT_BUYERS_PREMIUM = 15.0

    def start_requests(self):
        """Generate initial requests."""
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                meta={
                    "playwright": True,
                    "playwright_include_page": False,
                    "playwright_page_goto_kwargs": {
                        "wait_until": "networkidle",
                        "timeout": 90000,
                    },
                },
                errback=self.handle_error,
            )

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """Parse auction browser page."""
        logger.info(f"Parsing auction browser: {response.url}")

        # whiskyauction.com (Drupal) exposes auctions as /node/{id} links
        auction_links = response.css("a[href*='/node/']::attr(href)").getall()
        auction_links += response.css("a[href*='/auction/']::attr(href)").getall()
        auction_links += response.css("a[href*='auction_id=']::attr(href)").getall()

        logger.info(f"Found {len(auction_links)} auction links")

        for auction_url in set(auction_links):
            full_url = urljoin(response.url, auction_url)
            yield scrapy.Request(
                full_url,
                callback=self.parse_auction,
                meta={
                    "playwright": True,
                    "playwright_include_page": False,
                    "playwright_page_goto_kwargs": {
                        "wait_until": "networkidle",
                        "timeout": 90000,
                    },
                },
                errback=self.handle_error,
            )

        # Pagination
        next_page = response.css("a.next::attr(href), a[rel='next']::attr(href)").get()
        if next_page:
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse,
                meta={
                    "playwright": True,
                    "playwright_include_page": False,
                    "playwright_page_goto_kwargs": {
                        "wait_until": "networkidle",
                        "timeout": 90000,
                    },
                },
                errback=self.handle_error,
            )

    def parse_auction(self, response: Response) -> Generator[Any, None, None]:
        """Parse auction page for lot listings."""
        auction_name = response.css("h1::text").get("").strip()
        auction_date = self._extract_auction_date(response)

        logger.info(f"Parsing auction: {auction_name}")

        # Extract lot links
        lot_links = response.css("a[href*='/lot/']::attr(href)").getall()
        lot_links += response.css("a[href*='lot_id=']::attr(href)").getall()

        for lot_url in set(lot_links):
            full_url = urljoin(response.url, lot_url)
            yield scrapy.Request(
                full_url,
                callback=self.parse_lot,
                meta={
                    "playwright": True,
                    "playwright_include_page": False,
                    "playwright_page_goto_kwargs": {
                        "wait_until": "networkidle",
                        "timeout": 90000,
                    },
                    "auction_name": auction_name,
                    "auction_date": auction_date,
                },
                errback=self.handle_error,
            )

        # Pagination
        next_page = response.css("a.next::attr(href), a[rel='next']::attr(href)").get()
        if next_page:
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse_auction,
                meta={
                    "playwright": True,
                    "playwright_include_page": False,
                    "playwright_page_goto_kwargs": {
                        "wait_until": "networkidle",
                        "timeout": 90000,
                    },
                },
                errback=self.handle_error,
            )

    def parse_lot(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """Parse individual lot page."""
        logger.debug(f"Parsing lot: {response.url}")

        source_id = self._extract_lot_id(response.url)
        if not source_id:
            return

        raw_title = response.css("h1::text, .lot-title::text").get()
        if not raw_title:
            return

        raw_title = raw_title.strip()
        raw_description = " ".join(
            response.css(".lot-description *::text").getall()
        ).strip()

        item = self.create_item(
            response=response,
            source_id=source_id,
            raw_title=raw_title,
            raw_description=raw_description,
            auction_name=response.meta.get("auction_name", ""),
        )

        item["hammer_price"] = self._extract_hammer_price(response)
        item["buyers_premium_pct"] = self.DEFAULT_BUYERS_PREMIUM
        item["currency"] = self._detect_currency(response)

        if item["hammer_price"]:
            premium_rate = item["buyers_premium_pct"] / 100
            item["total_price"] = item["hammer_price"] * (1 + premium_rate)
            item["sold"] = True
        else:
            item["sold"] = False
            item["total_price"] = None

        item["auction_date"] = response.meta.get("auction_date")
        item["image_url"] = response.css(".lot-image img::attr(src)").get()

        self.items_scraped += 1
        yield item

    def _extract_lot_id(self, url: str) -> str | None:
        """Extract lot ID from URL."""
        match = re.search(r"/lot/(\d+)", url)
        if match:
            return f"wac-{match.group(1)}"

        match = re.search(r"lot_id=(\d+)", url)
        if match:
            return f"wac-{match.group(1)}"

        return None

    def _extract_hammer_price(self, response: Response) -> float | None:
        """Extract hammer price."""
        selectors = [
            ".hammer-price::text",
            ".winning-bid::text",
            ".sold-price::text",
            ".result::text",
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
        page_text = " ".join(response.css("*::text").getall())
        if "€" in page_text or "EUR" in page_text:
            return "EUR"
        elif "£" in page_text or "GBP" in page_text:
            return "GBP"
        return "EUR"  # Default for this auction

    def _extract_auction_date(self, response: Response) -> str | None:
        """Extract auction date."""
        date_text = response.css(".auction-date::text, time::attr(datetime)").get()
        if date_text:
            from dateutil import parser
            try:
                parsed = parser.parse(date_text, dayfirst=True)
                return parsed.strftime("%Y-%m-%d")
            except Exception:
                pass
        return None
