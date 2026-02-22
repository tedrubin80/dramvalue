"""
Spider for WhiskyStats (whiskystats.net).

Auction indices and bottle-level price data with portfolio tracking.
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


class WhiskyStatsSpider(BaseAuctionSpider):
    """
    Spider for scraping WhiskyStats price data.

    Site structure:
    - /distilleries - List of distilleries
    - /distillery/{name} - Distillery detail with bottles
    - /bottle/{id} - Individual bottle with price history
    - /indices - Market indices

    Provides historical auction data aggregated from multiple sources.
    """

    name = "whiskystats"
    auction_house = "WHISKYSTATS"
    allowed_domains = ["whiskystats.net", "www.whiskystats.net"]

    start_urls = [
        "https://www.whiskystats.net/distilleries",
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
        """Parse distilleries listing page."""
        logger.info(f"Parsing distilleries: {response.url}")

        # Extract distillery links
        distillery_links = response.css("a[href*='/distillery/']::attr(href)").getall()
        distillery_links += response.css(".distillery-card a::attr(href)").getall()

        logger.info(f"Found {len(distillery_links)} distillery links")

        for link in set(distillery_links):
            full_url = urljoin(response.url, link)
            yield scrapy.Request(
                full_url,
                callback=self.parse_distillery,
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

    def parse_distillery(self, response: Response) -> Generator[Any, None, None]:
        """Parse distillery page to get bottle listings."""
        distillery_name = response.css("h1::text").get("").strip()
        logger.info(f"Parsing distillery: {distillery_name}")

        # Extract bottle links
        bottle_links = response.css("a[href*='/bottle/']::attr(href)").getall()

        for link in set(bottle_links):
            full_url = urljoin(response.url, link)
            yield scrapy.Request(
                full_url,
                callback=self.parse_bottle,
                meta={"distillery": distillery_name},
                errback=self.handle_error,
            )

        # Pagination
        next_page = response.css("a.next::attr(href), a[rel='next']::attr(href)").get()
        if next_page:
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse_distillery,
                errback=self.handle_error,
            )

    def parse_lot(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """Redirect to parse_bottle."""
        yield from self.parse_bottle(response)

    def parse_bottle(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """
        Parse bottle page with price history.

        WhiskyStats shows multiple historical prices per bottle.
        """
        logger.debug(f"Parsing bottle: {response.url}")

        raw_title = response.css("h1::text, .bottle-name::text").get()
        if not raw_title:
            return

        raw_title = raw_title.strip()

        raw_description = " ".join(
            response.css(".bottle-description *::text, .details *::text").getall()
        ).strip()

        distillery = response.meta.get("distillery") or self._extract_distillery(response)

        # Extract price history
        # WhiskyStats typically shows a table or list of historical prices
        price_entries = response.css(".price-history tr, .auction-record, .price-entry")

        if not price_entries:
            # Try extracting from JSON-LD or data attributes
            price_entries = response.css("*[data-price]")

        for idx, entry in enumerate(price_entries):
            # Extract date
            date_text = entry.css("td:first-child::text, .date::text, *[data-date]::attr(data-date)").get()
            auction_date = self._parse_date(date_text) if date_text else None

            # Extract price
            price_text = entry.css("td:nth-child(2)::text, .price::text, *[data-price]::attr(data-price)").get()
            if not price_text:
                continue

            hammer_price = parse_price(price_text)
            if not hammer_price or hammer_price <= 0:
                continue

            # Extract source auction
            source_name = entry.css("td:nth-child(3)::text, .source::text").get("").strip()

            # Generate unique ID
            source_id = f"wst-{response.url.split('/')[-1]}-{idx}"

            item = self.create_item(
                response=response,
                source_id=source_id,
                raw_title=raw_title,
                raw_description=raw_description,
                distillery=distillery,
            )

            item["hammer_price"] = hammer_price
            item["total_price"] = hammer_price
            item["currency"] = self._detect_currency(price_text)
            item["auction_date"] = auction_date
            item["auction_name"] = source_name or "WhiskyStats"
            item["sold"] = True

            self.items_scraped += 1
            yield item

        # If no price history, try to get current/average price
        if not price_entries:
            avg_price = self._extract_average_price(response)
            if avg_price:
                source_id = f"wst-{response.url.split('/')[-1]}-avg"

                item = self.create_item(
                    response=response,
                    source_id=source_id,
                    raw_title=raw_title,
                    raw_description=raw_description,
                    distillery=distillery,
                )

                item["hammer_price"] = avg_price
                item["total_price"] = avg_price
                item["currency"] = "GBP"
                item["auction_name"] = "WhiskyStats Average"
                item["sold"] = True

                self.items_scraped += 1
                yield item

    def _extract_distillery(self, response: Response) -> str | None:
        """Extract distillery from page."""
        breadcrumb = response.css(".breadcrumb a::text").getall()
        for crumb in breadcrumb:
            if crumb.strip() and crumb.strip().lower() not in ["home", "distilleries"]:
                return crumb.strip()

        distillery = response.css(".distillery::text").get()
        return distillery.strip() if distillery else None

    def _extract_average_price(self, response: Response) -> float | None:
        """Extract average/current price from page."""
        selectors = [
            ".average-price::text",
            ".current-value::text",
            ".price-value::text",
            "*[data-average]::attr(data-average)",
        ]

        for selector in selectors:
            price_text = response.css(selector).get()
            if price_text:
                price = parse_price(price_text)
                if price and price > 0:
                    return price

        return None

    def _detect_currency(self, price_text: str) -> str:
        """Detect currency from price text."""
        if "£" in price_text:
            return "GBP"
        elif "€" in price_text:
            return "EUR"
        elif "$" in price_text:
            return "USD"
        return "GBP"

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
