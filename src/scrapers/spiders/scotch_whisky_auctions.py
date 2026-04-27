"""
Spider for Scotch Whisky Auctions (scotchwhiskyauctions.com).

UK-based online whisky auction platform with regular timed auctions.
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


class ScotchWhiskyAuctionsSpider(BaseAuctionSpider):
    """
    Spider for scraping Scotch Whisky Auctions results.

    Site structure (as of Jan 2025):
    - Past auctions: /auctions/past
    - Auction results: /auctions/{id}-{slug}/
    - Individual lots: /auctions/{auction_id}-{slug}/{lot_id}-{lot_slug}/

    Note: This site uses relative URLs and &pound; entities for prices.
    """

    name = "scotch_whisky_auctions"
    auction_house = "SCOTCH_WHISKY_AUCTIONS"
    allowed_domains = ["scotchwhiskyauctions.com", "www.scotchwhiskyauctions.com"]

    # Start with auctions listing page (shows all auctions, past and current)
    start_urls = ["https://www.scotchwhiskyauctions.com/auctions/"]

    # Spider-specific settings
    custom_settings = {
        "DOWNLOAD_DELAY": 3.0,
        "CONCURRENT_REQUESTS": 1,
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 30000,
    }

    # Default buyer's premium for Scotch Whisky Auctions
    DEFAULT_BUYERS_PREMIUM = 15.0  # 15%

    def start_requests(self):
        """Generate initial requests with Playwright enabled."""
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                meta={},
                errback=self.handle_error,
            )

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """
        Parse auctions listing page.

        Extracts links to individual completed auctions.
        Site shows all auctions (past and current) on one page.
        """
        logger.info(f"Parsing auctions page: {response.url}")

        # Extract auction links - pattern: /auctions/{id}-the-{nth}-auction/
        # Example: /auctions/224-the-175th-auction/
        auction_links = response.css("a[href*='/auctions/']::attr(href)").getall()

        # Filter to actual auction links (not lot pages which have additional path segments)
        # Auction: /auctions/224-the-175th-auction/
        # Lot: /auctions/224-the-175th-auction/855445-bottle-name/
        filtered_links = []
        for link in set(auction_links):
            # Skip if it's the main auctions page
            if link.rstrip('/') == '/auctions' or link.rstrip('/') == 'auctions':
                continue
            # Match auction pattern: /auctions/{id}-{slug}/ with exactly 2 path segments
            parts = link.strip('/').split('/')
            if len(parts) == 2 and parts[0] == 'auctions' and re.match(r'\d+-', parts[1]):
                filtered_links.append(link)

        auction_links = filtered_links
        logger.info(f"Found {len(auction_links)} auction links")

        # Follow each auction
        for auction_url in auction_links:
            full_url = urljoin(response.url, auction_url)
            yield scrapy.Request(
                full_url,
                callback=self.parse_auction,
                meta={},
                errback=self.handle_error,
            )

        # Handle pagination
        next_page = self._find_next_page(response)
        if next_page:
            logger.info(f"Following pagination: {next_page}")
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse,
                meta={},
                errback=self.handle_error,
            )

    def parse_auction(self, response: Response) -> Generator[Any, None, None]:
        """
        Parse individual auction page to get lot listings.

        Lot URLs: /auctions/{auction-id}-{auction-slug}/{lot-id}-{lot-slug}/
        Example: /auctions/224-the-175th-auction/855445-1800-reposado-tequila/
        """
        logger.info(f"Parsing auction: {response.url}")

        # Extract auction metadata
        auction_name = response.css("h1::text").get("").strip()
        if not auction_name:
            auction_name = response.css(".auction-title::text, title::text").get("").strip()

        auction_date = self._extract_auction_date(response)

        # Extract lot links
        # Pattern: /auctions/{auction}/{lot_id}-{slug}/
        all_links = response.css("a[href*='/auctions/']::attr(href)").getall()

        lot_links = []
        for link in set(all_links):
            parts = link.strip('/').split('/')
            # Lot pages have 3 parts: auctions/{auction-slug}/{lot-slug}
            if len(parts) == 3 and parts[0] == 'auctions':
                # Check that lot segment starts with a number
                if re.match(r'\d+-', parts[2]):
                    lot_links.append(link)

        logger.info(f"Found {len(lot_links)} lot links in: {auction_name}")

        # Follow each lot
        for lot_url in lot_links:
            full_url = urljoin(response.url, lot_url)
            yield scrapy.Request(
                full_url,
                callback=self.parse_lot,
                meta={
                    "auction_name": auction_name,
                    "auction_date": auction_date,
                },
                errback=self.handle_error,
            )

        # Handle pagination within auction
        next_page = self._find_next_page(response)
        if next_page:
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse_auction,
                meta={},
                errback=self.handle_error,
            )

    def parse_lot(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """
        Parse individual lot page to extract price data.
        """
        logger.debug(f"Parsing lot: {response.url}")

        # Extract lot ID from URL
        source_id = self._extract_lot_id(response.url)
        if not source_id:
            logger.warning(f"Could not extract lot ID from: {response.url}")
            return

        # Extract title
        raw_title = (
            response.css("h1.lot-title::text").get() or
            response.css("h1::text").get() or
            response.css(".lot-name::text").get() or
            response.css(".lot-header h1::text").get()
        )

        if not raw_title:
            logger.warning(f"Could not extract title from: {response.url}")
            return

        raw_title = raw_title.strip()

        # Extract description
        raw_description = " ".join(
            response.css(".lot-description *::text, .description *::text, .lot-info *::text").getall()
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

        # Calculate total price
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
        item["auction_date"] = (
            response.meta.get("auction_date") or
            self._extract_lot_date(response)
        )

        # Image
        item["image_url"] = (
            response.css(".lot-image img::attr(src)").get() or
            response.css("img.lot-img::attr(src)").get() or
            response.css(".lot-photo img::attr(src)").get()
        )

        # Number of bids
        item["num_bids"] = self._extract_bid_count(response)

        self.items_scraped += 1
        yield item

    def _find_next_page(self, response: Response) -> str | None:
        """Find next page link."""
        selectors = [
            "a.pagination-next::attr(href)",
            "a[rel='next']::attr(href)",
            "li.next a::attr(href)",
            ".pagination a.next::attr(href)",
            "a:contains('Next')::attr(href)",
            "a:contains('>')::attr(href)",
        ]

        for selector in selectors:
            next_page = response.css(selector).get()
            if next_page:
                return next_page

        return None

    def _extract_lot_id(self, url: str) -> str | None:
        """Extract lot ID from URL."""
        # Pattern for this site: /auctions/{auction}/{lot_id}-{slug}/
        # Example: /auctions/208-the-160th-auction/770298-a-fine-christmas-malt.../
        match = re.search(r"/auctions/[^/]+/(\d+)-", url)
        if match:
            return match.group(1)

        # Fallback: /lot/123 or /lots/456
        match = re.search(r"/lots?/(\d+)", url)
        if match:
            return match.group(1)

        # Try query parameter
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "lot" in params:
            return params["lot"][0]
        if "id" in params:
            return params["id"][0]

        return None

    def _extract_hammer_price(self, response: Response) -> float | None:
        """Extract hammer price from lot page.

        Site displays prices as "Sold for £XX in Month Year"
        """
        # Try CSS selectors first
        selectors = [
            ".bidinfo.won::text",
            ".winning-bid::text",
            ".hammer-price::text",
            ".sold-price::text",
            ".result-price::text",
            ".final-price::text",
            ".price::text",
            ".lot-result::text",
        ]

        for selector in selectors:
            price_text = response.css(selector).get()
            if price_text:
                price = parse_price(price_text)
                if price and price > 0:
                    return price

        # Get page text to find price patterns
        page_text = " ".join(response.css("*::text").getall())
        page_html = response.text

        # Site uses "Sold for £XX" format
        price_patterns = [
            r"[Ss]old\s+for\s+£([\d,]+(?:\.\d{2})?)",
            r"[Ss]old\s+for\s+&pound;([\d,]+(?:\.\d{2})?)",
            r"[Ww]inning\s+bid[:\s]*£([\d,]+(?:\.\d{2})?)",
            r"[Ww]inning\s+bid[:\s]*&pound;([\d,]+(?:\.\d{2})?)",
            r"[Hh]ammer[:\s]*£([\d,]+(?:\.\d{2})?)",
            r"[Hh]ammer[:\s]*&pound;([\d,]+(?:\.\d{2})?)",
            r"£([\d,]+(?:\.\d{2})?)\s+(?:hammer|won|sold)",
        ]

        # Try in page text first
        for pattern in price_patterns:
            match = re.search(pattern, page_text)
            if match:
                return parse_price(match.group(1))

        # Try in raw HTML for &pound; entities
        for pattern in price_patterns:
            match = re.search(pattern, page_html)
            if match:
                return parse_price(match.group(1))

        return None

    def _extract_buyers_premium(self, response: Response) -> float:
        """Extract buyer's premium percentage."""
        premium_text = response.css(".buyers-premium::text, .premium::text").get()
        if premium_text:
            match = re.search(r"(\d+(?:\.\d+)?)\s*%", premium_text)
            if match:
                return float(match.group(1))

        return self.DEFAULT_BUYERS_PREMIUM

    def _extract_estimates(self, response: Response) -> tuple[float | None, float | None]:
        """Extract low and high estimates."""
        estimate_text = response.css(".estimate::text, .lot-estimate::text").get()
        if not estimate_text:
            return None, None

        # Pattern: "£100 - £200" or "Est. £100-£200"
        match = re.search(r"£([\d,]+)\s*[-–]\s*£?([\d,]+)", estimate_text)
        if match:
            low = parse_price(match.group(1))
            high = parse_price(match.group(2))
            return low, high

        return None, None

    def _check_if_sold(self, response: Response) -> bool:
        """Check if lot was sold."""
        page_text = " ".join(response.css("*::text").getall()).lower()

        unsold_indicators = ["unsold", "not sold", "passed", "no sale", "withdrawn", "reserve not met"]
        for indicator in unsold_indicators:
            if indicator in page_text:
                return False

        if self._extract_hammer_price(response):
            return True

        return False

    def _extract_auction_date(self, response: Response) -> str | None:
        """Extract auction date from page."""
        selectors = [
            ".auction-date::text",
            ".end-date::text",
            ".closing-date::text",
            "time::attr(datetime)",
        ]

        for selector in selectors:
            date_text = response.css(selector).get()
            if date_text:
                return self._parse_date(date_text)

        # Try to find date in page content
        page_text = " ".join(response.css("*::text").getall())
        date_patterns = [
            r"(?:closed|ended|finished)\s*(?:on)?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
            r"(\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+\d{4})",
        ]

        for pattern in date_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return self._parse_date(match.group(1))

        return None

    def _extract_lot_date(self, response: Response) -> str | None:
        """Extract date from lot page."""
        return self._extract_auction_date(response)

    def _extract_bid_count(self, response: Response) -> int | None:
        """Extract number of bids."""
        bid_text = response.css(".bid-count::text, .bids::text").get()
        if bid_text:
            match = re.search(r"(\d+)", bid_text)
            if match:
                return int(match.group(1))
        return None

    def _parse_date(self, date_text: str) -> str | None:
        """Parse date string to ISO format."""
        if not date_text:
            return None

        date_text = date_text.strip()

        # Already ISO format
        if re.match(r"\d{4}-\d{2}-\d{2}", date_text):
            return date_text[:10]

        from dateutil import parser
        try:
            parsed = parser.parse(date_text, dayfirst=True)
            return parsed.strftime("%Y-%m-%d")
        except Exception:
            return None
