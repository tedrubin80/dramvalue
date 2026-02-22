"""
Spider for Whisky.Auction (whisky.auction).

Major UK auction house with regular timed auctions.
Provides individual lot results with hammer prices.
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


class WhiskyAuctionUKSpider(BaseAuctionSpider):
    """
    Spider for scraping Whisky.Auction results.

    Site structure:
    - /past-auctions - List of completed auctions
    - /auction/{id} - Individual auction with lots
    - /lot/{id} - Individual lot details

    Uses Playwright for JavaScript rendering.
    """

    name = "whisky_auction_uk"
    auction_house = "WHISKY_AUCTION_UK"
    allowed_domains = ["whisky.auction", "www.whisky.auction"]

    start_urls = [
        "https://www.whisky.auction/past-auctions",
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 5.0,
        "CONCURRENT_REQUESTS": 1,
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 90000,
    }

    DEFAULT_BUYERS_PREMIUM = 20.0

    def start_requests(self):
        """Generate initial requests with Playwright."""
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
        """Parse past auctions listing page."""
        logger.info(f"Parsing past auctions: {response.url}")

        # Extract auction links
        auction_links = response.css("a[href*='/auction/']::attr(href)").getall()

        if not auction_links:
            # Try alternative selectors
            auction_links = response.css(".auction-card a::attr(href)").getall()
            auction_links += response.css(".past-auction a::attr(href)").getall()

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

        # Handle pagination
        next_page = response.css("a[rel='next']::attr(href), .pagination .next a::attr(href)").get()
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
        """Parse individual auction to get lot listings."""
        auction_name = response.css("h1::text").get("").strip()
        auction_date = self._extract_auction_date(response)

        logger.info(f"Parsing auction: {auction_name}")

        # Extract lot links
        lot_links = response.css("a[href*='/lot/']::attr(href)").getall()

        if not lot_links:
            lot_links = response.css(".lot-card a::attr(href)").getall()
            lot_links += response.css(".lot-item a::attr(href)").getall()

        logger.info(f"Found {len(lot_links)} lots in auction: {auction_name}")

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

        # Handle pagination within auction
        next_page = response.css("a[rel='next']::attr(href)").get()
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

        # Extract lot ID
        source_id = self._extract_lot_id(response.url)
        if not source_id:
            logger.warning(f"Could not extract lot ID: {response.url}")
            return

        # Extract title
        raw_title = response.css("h1::text, .lot-title::text").get()
        if not raw_title:
            logger.warning(f"No title found: {response.url}")
            return

        raw_title = raw_title.strip()

        # Extract description
        raw_description = " ".join(
            response.css(".lot-description *::text, .description *::text").getall()
        ).strip()

        # Create item
        item = self.create_item(
            response=response,
            source_id=source_id,
            raw_title=raw_title,
            raw_description=raw_description,
            auction_name=response.meta.get("auction_name", ""),
        )

        # Extract price
        item["hammer_price"] = self._extract_hammer_price(response)
        item["buyers_premium_pct"] = self._extract_buyers_premium(response)
        item["currency"] = "GBP"

        if item["hammer_price"]:
            premium_rate = (item["buyers_premium_pct"] or self.DEFAULT_BUYERS_PREMIUM) / 100
            item["total_price"] = item["hammer_price"] * (1 + premium_rate)
            item["sold"] = True
        else:
            item["sold"] = self._check_if_sold(response)
            item["total_price"] = None

        # Extract estimates
        item["estimate_low"], item["estimate_high"] = self._extract_estimates(response)

        # Auction date
        item["auction_date"] = response.meta.get("auction_date") or self._extract_lot_date(response)

        # Image
        item["image_url"] = response.css(".lot-image img::attr(src), img.lot-photo::attr(src)").get()

        # Bid count
        item["num_bids"] = self._extract_bid_count(response)

        self.items_scraped += 1
        yield item

    def _extract_lot_id(self, url: str) -> str | None:
        """Extract lot ID from URL."""
        match = re.search(r"/lot/(\d+)", url)
        if match:
            return f"wauk-{match.group(1)}"
        return None

    def _extract_hammer_price(self, response: Response) -> float | None:
        """Extract hammer price."""
        selectors = [
            ".hammer-price::text",
            ".winning-bid::text",
            ".sold-price::text",
            ".final-price::text",
            ".result-price::text",
        ]

        for selector in selectors:
            price_text = response.css(selector).get()
            if price_text:
                price = parse_price(price_text)
                if price and price > 0:
                    return price

        # Try regex patterns in page text
        page_text = " ".join(response.css("*::text").getall())
        patterns = [
            r"hammer[:\s]*£([\d,]+)",
            r"sold[:\s]*£([\d,]+)",
            r"winning bid[:\s]*£([\d,]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return parse_price(match.group(1))

        return None

    def _extract_buyers_premium(self, response: Response) -> float:
        """Extract buyer's premium percentage."""
        premium_text = response.css(".buyers-premium::text").get()
        if premium_text:
            match = re.search(r"(\d+(?:\.\d+)?)\s*%", premium_text)
            if match:
                return float(match.group(1))
        return self.DEFAULT_BUYERS_PREMIUM

    def _extract_estimates(self, response: Response) -> tuple[float | None, float | None]:
        """Extract price estimates."""
        estimate_text = response.css(".estimate::text, .price-estimate::text").get()
        if not estimate_text:
            return None, None

        match = re.search(r"£([\d,]+)\s*[-–]\s*£?([\d,]+)", estimate_text)
        if match:
            return parse_price(match.group(1)), parse_price(match.group(2))

        return None, None

    def _check_if_sold(self, response: Response) -> bool:
        """Check if lot was sold."""
        page_text = " ".join(response.css("*::text").getall()).lower()
        unsold_indicators = ["unsold", "not sold", "passed", "withdrawn", "no sale"]
        return not any(ind in page_text for ind in unsold_indicators)

    def _extract_auction_date(self, response: Response) -> str | None:
        """Extract auction date from auction page."""
        date_text = response.css(".auction-date::text, time::attr(datetime)").get()
        return self._parse_date(date_text) if date_text else None

    def _extract_lot_date(self, response: Response) -> str | None:
        """Extract auction date from lot page."""
        date_text = response.css(".sold-date::text, .auction-end::text").get()
        return self._parse_date(date_text) if date_text else None

    def _extract_bid_count(self, response: Response) -> int | None:
        """Extract number of bids."""
        bid_text = response.css(".bid-count::text, .num-bids::text").get()
        if bid_text:
            match = re.search(r"(\d+)", bid_text)
            if match:
                return int(match.group(1))
        return None

    def _parse_date(self, date_text: str) -> str | None:
        """Parse date to ISO format."""
        if not date_text:
            return None

        if re.match(r"\d{4}-\d{2}-\d{2}", date_text):
            return date_text[:10]

        from dateutil import parser
        try:
            parsed = parser.parse(date_text, dayfirst=True)
            return parsed.strftime("%Y-%m-%d")
        except Exception:
            return None
