"""
Spider for Bottle Blue Book (bottlebluebook.com).

Auction sales data and bottle valuations for bourbon, whiskey, scotch, and wine.
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


class BottleBlueBookSpider(BaseAuctionSpider):
    """
    Spider for scraping Bottle Blue Book auction data.

    Site structure:
    - /type/Bourbon - Bourbon category
    - /type/Rye%20Whiskey - Rye whiskey category
    - /type/Scotch - Scotch category
    - /type/Japanese%20Whisky - Japanese whisky category
    - /bottle/{id}/{name} - Individual bottle pages

    Provides auction sales data with prices and dates.
    """

    name = "bottle_blue_book"
    auction_house = "BOTTLE_BLUE_BOOK"
    allowed_domains = ["bottlebluebook.com", "www.bottlebluebook.com"]

    start_urls = [
        "https://bottlebluebook.com/type/Bourbon",
        "https://bottlebluebook.com/type/Rye%20Whiskey",
        "https://bottlebluebook.com/type/Scotch",
        "https://bottlebluebook.com/type/Japanese%20Whisky",
        "https://bottlebluebook.com/type/Whiskey",
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 4.0,
        "CONCURRENT_REQUESTS": 1,
        "ROBOTSTXT_OBEY": True,
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 60000,
    }

    PLAYWRIGHT_META = {
        "playwright": True,
        "playwright_include_page": False,
        "playwright_page_goto_kwargs": {
            "wait_until": "networkidle",
            "timeout": 60000,
        },
    }

    def start_requests(self):
        """Generate initial requests with Playwright for AngularJS rendering."""
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                meta=dict(self.PLAYWRIGHT_META),
                errback=self.handle_error,
            )

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """Parse category page to get bottle listings."""
        logger.info(f"Parsing category: {response.url}")

        # Extract bottle links
        bottle_links = response.css("a[href*='/bottle/']::attr(href)").getall()

        logger.info(f"Found {len(bottle_links)} bottle links")

        for link in set(bottle_links):
            full_url = urljoin(response.url, link)
            yield scrapy.Request(
                full_url,
                callback=self.parse_bottle,
                meta=dict(self.PLAYWRIGHT_META),
                errback=self.handle_error,
            )

        # Pagination
        next_page = response.css("a[rel='next']::attr(href), a.next::attr(href)").get()
        if next_page:
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse,
                meta=dict(self.PLAYWRIGHT_META),
                errback=self.handle_error,
            )

    def parse_lot(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """Redirect to parse_bottle."""
        yield from self.parse_bottle(response)

    def parse_bottle(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """
        Parse individual bottle page with sales history.

        Each bottle page shows multiple auction sales.
        """
        logger.debug(f"Parsing bottle: {response.url}")

        raw_title = response.css("h1::text").get()
        if not raw_title:
            raw_title = response.css(".bottle-name::text, .product-title::text").get()

        if not raw_title:
            return

        raw_title = raw_title.strip()

        raw_description = " ".join(
            response.css(".bottle-description *::text, .details *::text").getall()
        ).strip()

        # Extract sales history from "Recent Recorded Transactions"
        # Structure: <ul class="recent_trans"><li><span class="rt_text"><strong>Sold: </strong>$275 on <i>10/12/2025</i></span>
        sales_rows = response.css("ul.recent_trans li")

        url_parts = response.url.rstrip("/").split("/")
        bottle_id = url_parts[-2] if len(url_parts) >= 2 else "0"
        bottle_slug = url_parts[-1][:20]

        if sales_rows:
            for idx, row in enumerate(sales_rows):
                rt_text = " ".join(row.css("span.rt_text::text, span.rt_text *::text").getall())
                price_match = re.search(r"\$([\d,]+(?:\.\d{2})?)", rt_text)
                if not price_match:
                    continue
                price = parse_price(price_match.group(1))
                if not price or price <= 0:
                    continue

                date_text = row.css("span.rt_text i::text").get()
                auction_date = self._parse_date(date_text) if date_text else None

                source_text = row.css("div.rt_source::text").get()

                source_id = f"bbb-{bottle_id}-{bottle_slug}-{idx}"

                item = self.create_item(
                    response=response,
                    source_id=source_id,
                    raw_title=raw_title,
                    raw_description=raw_description,
                )

                item["hammer_price"] = price
                item["total_price"] = price
                item["currency"] = "USD"
                item["auction_date"] = auction_date
                item["auction_name"] = source_text.strip() if source_text else "Bottle Blue Book"
                item["sold"] = True

                self.items_scraped += 1
                yield item
        else:
            # Try to extract average/current value
            avg_price = self._extract_average_price(response)
            if avg_price:
                source_id = f"bbb-{bottle_id}-{bottle_slug}-avg"

                item = self.create_item(
                    response=response,
                    source_id=source_id,
                    raw_title=raw_title,
                    raw_description=raw_description,
                )

                item["hammer_price"] = avg_price
                item["total_price"] = avg_price
                item["currency"] = "USD"
                item["auction_name"] = "Bottle Blue Book Average"
                item["sold"] = True

                self.items_scraped += 1
                yield item

    def _extract_average_price(self, response: Response) -> float | None:
        """Extract average/current value from page."""
        selectors = [
            ".average-price::text",
            ".current-value::text",
            ".estimated-value::text",
            ".valuation::text",
        ]

        for selector in selectors:
            price_text = response.css(selector).get()
            if price_text:
                price = parse_price(price_text)
                if price and price > 0:
                    return price

        # Try regex in page text
        page_text = " ".join(response.css("*::text").getall())
        patterns = [
            r"average[:\s]*\$?([\d,]+(?:\.\d{2})?)",
            r"value[:\s]*\$?([\d,]+(?:\.\d{2})?)",
            r"worth[:\s]*\$?([\d,]+(?:\.\d{2})?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return parse_price(match.group(1))

        return None

    def _parse_date(self, date_text: str) -> str | None:
        """Parse date to ISO format."""
        if not date_text:
            return None

        date_text = date_text.strip()

        # Already ISO format
        if re.match(r"\d{4}-\d{2}-\d{2}", date_text):
            return date_text[:10]

        from dateutil import parser
        try:
            parsed = parser.parse(date_text)
            return parsed.strftime("%Y-%m-%d")
        except Exception:
            return None
