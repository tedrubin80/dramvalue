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
from src.scrapers.spider_settings import HTTP_ONLY_SETTINGS
from src.scrapers.utils.text import parse_price

logger = logging.getLogger(__name__)


class WhiskyAuctionUKSpider(BaseAuctionSpider):
    """
    Spider for scraping Whisky.Auction past auction results.

    Site structure (as of Jul 2026):
    - /auctions - Past auctions listing
    - /auctions/auction/{id} - Individual auction with lots
    - /auctions/lot/{id}/{slug} - Individual lot details

    Server-rendered HTML — no Playwright required.
    """

    name = "whisky_auction_uk"
    auction_house = "WHISKY_AUCTION_UK"
    allowed_domains = ["whisky.auction"]

    start_urls = [
        "https://whisky.auction/auctions",
    ]

    custom_settings = {
        **HTTP_ONLY_SETTINGS,
        "DOWNLOAD_DELAY": 2.0,
        "CONCURRENT_REQUESTS": 1,
        "ROBOTSTXT_OBEY": True,
        "CLOSESPIDER_ITEMCOUNT": 200,
    }

    DEFAULT_BUYERS_PREMIUM = 20.0

    def __init__(self, *args, scrape_run_id: int = None, max_auctions: int = None, **kwargs):
        super().__init__(*args, scrape_run_id=scrape_run_id, **kwargs)
        self.max_auctions = int(max_auctions) if max_auctions else 5
        self._auctions_processed = 0

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """Parse past auctions listing page."""
        logger.info(f"Parsing past auctions: {response.url}")

        auction_links = response.css("a[href*='/auctions/auction/']::attr(href)").getall()

        # Sort by auction ID descending (highest = most recent)
        def _auction_num(href: str) -> int:
            m = re.search(r"/auctions/auction/(\d+)", href)
            return int(m.group(1)) if m else 0

        unique_links = list(dict.fromkeys(auction_links))
        recent = sorted(unique_links, key=_auction_num, reverse=True)

        logger.info(f"Found {len(unique_links)} auction links")

        for auction_url in recent:
            if self._auctions_processed >= self.max_auctions:
                logger.info(f"Reached max_auctions limit ({self.max_auctions}), stopping")
                return

            self._auctions_processed += 1
            full_url = urljoin(response.url, auction_url)
            yield scrapy.Request(
                full_url,
                callback=self.parse_auction,
                errback=self.handle_error,
            )

        if self._auctions_processed < self.max_auctions:
            next_page = response.css("a[rel='next']::attr(href), .pagination .next a::attr(href)").get()
            if next_page:
                yield scrapy.Request(
                    urljoin(response.url, next_page),
                    callback=self.parse,
                    errback=self.handle_error,
                )

    def parse_auction(self, response: Response) -> Generator[Any, None, None]:
        """Parse individual auction to get lot listings."""
        auction_name = response.css("h1::text, .title-main::text").get("").strip()
        auction_date = self._extract_auction_date(response)

        logger.info(f"Parsing auction: {auction_name or response.url}")

        lot_links = response.css("a[href*='/auctions/lot/']::attr(href)").getall()

        logger.info(f"Found {len(set(lot_links))} lots in auction")

        for lot_url in set(lot_links):
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

        next_page = response.css("a[rel='next']::attr(href)").get()
        if next_page:
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse_auction,
                meta=response.meta,
                errback=self.handle_error,
            )

    def parse_lot(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """Parse individual lot page."""
        source_id = self._extract_lot_id(response.url)
        if not source_id:
            logger.warning(f"Could not extract lot ID: {response.url}")
            return

        raw_title = " ".join(
            t.strip() for t in response.css("h1.product-title ::text").getall() if t.strip()
        )
        if not raw_title:
            raw_title = response.css("h1::text").get()
        if not raw_title:
            logger.warning(f"No title found: {response.url}")
            return

        raw_title = raw_title.strip()

        # Skip live/preview lots — only persist closed auction results
        auction_status = response.css("[data-auction-status]::attr(data-auction-status)").get()
        if auction_status and auction_status.lower() != "close":
            logger.debug(f"Skipping non-closed lot {source_id} (status={auction_status})")
            return

        hammer_price = self._extract_hammer_price(response)
        if not hammer_price:
            logger.debug(f"No hammer price for lot {source_id}, skipping")
            return

        raw_description = " ".join(
            response.css(".lot-description *::text, .product-description *::text").getall()
        ).strip()

        item = self.create_item(
            response=response,
            source_id=source_id,
            raw_title=raw_title,
            raw_description=raw_description,
            auction_name=response.meta.get("auction_name", ""),
        )

        item["hammer_price"] = hammer_price
        item["buyers_premium_pct"] = self.DEFAULT_BUYERS_PREMIUM
        item["currency"] = "GBP"
        premium_rate = item["buyers_premium_pct"] / 100
        item["total_price"] = hammer_price * (1 + premium_rate)
        item["sold"] = True
        item["auction_date"] = response.meta.get("auction_date") or self._extract_lot_date(response)
        item["image_url"] = response.css(
            ".product-info img::attr(src), .lot-item img::attr(src)"
        ).get()

        self.items_scraped += 1
        yield item

    def _extract_lot_id(self, url: str) -> str | None:
        """Extract lot ID from URL."""
        match = re.search(r"/auctions/lot/(\d+)", url)
        if match:
            return f"wauk-{match.group(1)}"
        return None

    def _extract_hammer_price(self, response: Response) -> float | None:
        """Extract hammer price from data attributes or page text."""
        winning_bid = response.css("[data-winningbid]::attr(data-winningbid)").get()
        if winning_bid:
            price = parse_price(winning_bid)
            if price and price > 0:
                return price

        for selector in [".hammerprice .winningBid::text", ".hammer-price::text", ".winning-bid::text"]:
            price_text = response.css(selector).get()
            if price_text:
                price = parse_price(price_text)
                if price and price > 0:
                    return price

        meta_price = response.css('meta[itemprop="price"]::attr(content)').get()
        if meta_price:
            price = parse_price(meta_price)
            if price and price > 5:  # ignore placeholder £5 lots
                return price

        return None

    def _extract_auction_date(self, response: Response) -> str | None:
        """Extract auction date from auction page."""
        date_text = response.css(".auction-date::text, time::attr(datetime)").get()
        return self._parse_date(date_text) if date_text else None

    def _extract_lot_date(self, response: Response) -> str | None:
        """Extract auction end date from lot page data attribute."""
        end_date = response.css("[data-enddate]::attr(data-enddate)").get()
        if end_date:
            return self._parse_date(end_date)
        date_text = response.css(".sold-date::text, .auction-end::text").get()
        return self._parse_date(date_text) if date_text else None

    def _parse_date(self, date_text: str) -> str | None:
        """Parse date to ISO format."""
        if not date_text:
            return None

        if re.match(r"\d{4}-\d{2}-\d{2}", date_text):
            return date_text[:10]

        from dateutil import parser
        try:
            parsed = parser.parse(date_text, dayfirst=False)
            return parsed.strftime("%Y-%m-%d")
        except Exception:
            return None
