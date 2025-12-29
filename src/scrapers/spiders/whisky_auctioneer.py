"""
Spider for Whisky Auctioneer (whiskyauctioneer.com).

UK-based online whisky auction platform with regular timed auctions.
Uses Playwright for JavaScript rendering.
"""

import re
import logging
from datetime import datetime
from typing import Generator, Any
from urllib.parse import urljoin, urlparse, parse_qs

import scrapy
from scrapy.http import Response

from src.scrapers.spiders.base import BaseAuctionSpider
from src.scrapers.items import AuctionLotItem
from src.scrapers.utils.text import parse_price

logger = logging.getLogger(__name__)


class WhiskyAuctioneerSpider(BaseAuctionSpider):
    """
    Spider for scraping Whisky Auctioneer auction results.

    Site structure (as of Dec 2024):
    - Auction results: /auction-results
    - Individual lots: /lot/{lot_id}/{slug}
    - Past auctions: /auctions (archived auctions list)

    This spider uses Playwright for JavaScript rendering as the site
    loads content dynamically.
    """

    name = "whisky_auctioneer"
    auction_house = "WHISKY_AUCTIONEER"
    allowed_domains = ["whiskyauctioneer.com", "www.whiskyauctioneer.com"]

    # Start with past auctions page to get auction listings
    start_urls = ["https://www.whiskyauctioneer.com/auctions?status=past"]

    # Spider-specific settings
    custom_settings = {
        "DOWNLOAD_DELAY": 3.0,
        "CONCURRENT_REQUESTS": 1,
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 30000,
    }

    # Default buyer's premium for Whisky Auctioneer
    DEFAULT_BUYERS_PREMIUM = 20.0  # 20%

    def start_requests(self):
        """Generate initial requests with Playwright enabled."""
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                meta={
                    "playwright": True,
                    "playwright_include_page": False,
                    "playwright_page_goto_kwargs": {
                        "wait_until": "networkidle",
                        "timeout": 30000,
                    },
                },
                errback=self.handle_error,
            )

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """
        Parse auctions listing page.

        Extracts links to individual auctions and follows pagination.
        """
        logger.info(f"Parsing auctions page: {response.url}")

        # Extract auction links
        # Selectors need to be validated against live site
        auction_links = response.css("a[href*='/auction/']::attr(href)").getall()

        if not auction_links:
            # Try alternative selectors
            auction_links = response.css(".auction-card a::attr(href)").getall()
            auction_links += response.css(".auction-item a::attr(href)").getall()

        logger.info(f"Found {len(auction_links)} auction links")

        # Follow each auction to get lot listings
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
                        "timeout": 30000,
                    },
                },
                errback=self.handle_error,
            )

        # Handle pagination
        next_page = response.css("a.pagination-next::attr(href)").get()
        if not next_page:
            next_page = response.css("a[rel='next']::attr(href)").get()
        if not next_page:
            next_page = response.css("li.next a::attr(href)").get()

        if next_page:
            logger.info(f"Following pagination: {next_page}")
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse,
                meta={
                    "playwright": True,
                    "playwright_include_page": False,
                    "playwright_page_goto_kwargs": {
                        "wait_until": "networkidle",
                        "timeout": 30000,
                    },
                },
                errback=self.handle_error,
            )

    def parse_auction(self, response: Response) -> Generator[Any, None, None]:
        """
        Parse individual auction page to get lot listings.

        Extracts links to individual lots within an auction.
        """
        logger.info(f"Parsing auction: {response.url}")

        # Extract auction metadata
        auction_name = response.css("h1::text").get("").strip()
        auction_date = self._extract_auction_date(response)

        # Extract lot links
        lot_links = response.css("a[href*='/lot/']::attr(href)").getall()

        if not lot_links:
            # Try alternative selectors
            lot_links = response.css(".lot-card a::attr(href)").getall()
            lot_links += response.css(".lot-item a::attr(href)").getall()

        logger.info(f"Found {len(lot_links)} lot links in auction: {auction_name}")

        # Follow each lot
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
                        "timeout": 30000,
                    },
                    "auction_name": auction_name,
                    "auction_date": auction_date,
                },
                errback=self.handle_error,
            )

        # Handle pagination within auction
        next_page = response.css("a.pagination-next::attr(href)").get()
        if not next_page:
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
                        "timeout": 30000,
                    },
                },
                errback=self.handle_error,
            )

    def parse_lot(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """
        Parse individual lot page to extract price data.

        This is where we extract the actual auction results.
        """
        logger.debug(f"Parsing lot: {response.url}")

        # Extract lot ID from URL
        source_id = self._extract_lot_id(response.url)
        if not source_id:
            logger.warning(f"Could not extract lot ID from: {response.url}")
            return

        # Extract title
        raw_title = response.css("h1.lot-title::text").get()
        if not raw_title:
            raw_title = response.css("h1::text").get()
        if not raw_title:
            raw_title = response.css(".lot-name::text").get()

        if not raw_title:
            logger.warning(f"Could not extract title from: {response.url}")
            return

        raw_title = raw_title.strip()

        # Extract description
        raw_description = " ".join(
            response.css(".lot-description *::text, .description *::text").getall()
        ).strip()

        # Create base item with auto-extraction
        item = self.create_item(
            response=response,
            source_id=source_id,
            raw_title=raw_title,
            raw_description=raw_description,
            auction_name=response.meta.get("auction_name", ""),
        )

        # Extract price information
        item["hammer_price"] = self._extract_hammer_price(response)
        item["buyers_premium_pct"] = self._extract_buyers_premium(response)
        item["currency"] = "GBP"

        # Calculate total price (hammer + premium)
        if item["hammer_price"]:
            premium_rate = (item["buyers_premium_pct"] or self.DEFAULT_BUYERS_PREMIUM) / 100
            item["total_price"] = item["hammer_price"] * (1 + premium_rate)
            item["sold"] = True
        else:
            # Check if explicitly marked as unsold
            item["sold"] = self._check_if_sold(response)
            item["total_price"] = None

        # Extract estimates
        item["estimate_low"], item["estimate_high"] = self._extract_estimates(response)

        # Extract auction date
        item["auction_date"] = (
            response.meta.get("auction_date") or
            self._extract_lot_date(response)
        )

        # Extract image
        item["image_url"] = response.css(".lot-image img::attr(src)").get()
        if not item["image_url"]:
            item["image_url"] = response.css("img.lot-img::attr(src)").get()

        # Number of bids
        item["num_bids"] = self._extract_bid_count(response)

        self.items_scraped += 1
        yield item

    def _extract_lot_id(self, url: str) -> str | None:
        """Extract lot ID from URL."""
        # Pattern: /lot/123456 or /lot/123456/whisky-name
        match = re.search(r"/lot/(\d+)", url)
        if match:
            return match.group(1)

        # Try query parameter
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "lot" in params:
            return params["lot"][0]

        return None

    def _extract_hammer_price(self, response: Response) -> float | None:
        """Extract hammer price from lot page."""
        # Try various selectors
        selectors = [
            ".hammer-price::text",
            ".winning-bid::text",
            ".final-price::text",
            ".sold-price::text",
            "*[data-hammer]::attr(data-hammer)",
            ".price-result::text",
        ]

        for selector in selectors:
            price_text = response.css(selector).get()
            if price_text:
                price = parse_price(price_text)
                if price and price > 0:
                    return price

        # Try to find price in text content
        price_patterns = [
            r"hammer\s*(?:price)?[:\s]*£([\d,]+)",
            r"sold\s*(?:for)?[:\s]*£([\d,]+)",
            r"winning\s*bid[:\s]*£([\d,]+)",
        ]

        page_text = " ".join(response.css("*::text").getall())
        for pattern in price_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return parse_price(match.group(1))

        return None

    def _extract_buyers_premium(self, response: Response) -> float:
        """Extract buyer's premium percentage."""
        # Try to find premium in page
        premium_text = response.css(".buyers-premium::text").get()
        if premium_text:
            match = re.search(r"(\d+(?:\.\d+)?)\s*%", premium_text)
            if match:
                return float(match.group(1))

        # Return default for Whisky Auctioneer
        return self.DEFAULT_BUYERS_PREMIUM

    def _extract_estimates(self, response: Response) -> tuple[float | None, float | None]:
        """Extract low and high estimates."""
        estimate_text = response.css(".estimate::text, .price-estimate::text").get()
        if not estimate_text:
            return None, None

        # Pattern: "£100 - £200" or "Estimate: £100-200"
        match = re.search(r"£([\d,]+)\s*[-–]\s*£?([\d,]+)", estimate_text)
        if match:
            low = parse_price(match.group(1))
            high = parse_price(match.group(2))
            return low, high

        return None, None

    def _check_if_sold(self, response: Response) -> bool:
        """Check if lot was sold based on page indicators."""
        # Look for "unsold", "not sold", "passed" indicators
        page_text = " ".join(response.css("*::text").getall()).lower()

        unsold_indicators = ["unsold", "not sold", "passed", "no sale", "withdrawn"]
        for indicator in unsold_indicators:
            if indicator in page_text:
                return False

        # If hammer price is present, it sold
        if self._extract_hammer_price(response):
            return True

        return False

    def _extract_auction_date(self, response: Response) -> str | None:
        """Extract auction date from auction page."""
        date_selectors = [
            ".auction-date::text",
            ".end-date::text",
            "time::attr(datetime)",
            "*[data-date]::attr(data-date)",
        ]

        for selector in date_selectors:
            date_text = response.css(selector).get()
            if date_text:
                return self._parse_date(date_text)

        return None

    def _extract_lot_date(self, response: Response) -> str | None:
        """Extract auction date from lot page."""
        date_selectors = [
            ".lot-date::text",
            ".auction-end::text",
            ".sold-date::text",
        ]

        for selector in date_selectors:
            date_text = response.css(selector).get()
            if date_text:
                return self._parse_date(date_text)

        return None

    def _extract_bid_count(self, response: Response) -> int | None:
        """Extract number of bids."""
        bid_text = response.css(".bid-count::text, .num-bids::text").get()
        if bid_text:
            match = re.search(r"(\d+)", bid_text)
            if match:
                return int(match.group(1))
        return None

    def _parse_date(self, date_text: str) -> str | None:
        """Parse date string to ISO format."""
        if not date_text:
            return None

        # Try ISO format first
        if re.match(r"\d{4}-\d{2}-\d{2}", date_text):
            return date_text[:10]

        # Try common date formats
        from dateutil import parser
        try:
            parsed = parser.parse(date_text, dayfirst=True)  # UK format
            return parsed.strftime("%Y-%m-%d")
        except Exception:
            return None
