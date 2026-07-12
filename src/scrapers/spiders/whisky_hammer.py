"""
Spider for Whisky Hammer (whiskyhammer.com).

UK-based whisky auction platform with regular timed auctions.
All pages are static HTML — no Playwright required.

Site structure:
- Past auctions listing: /previous-auctions
  → Links to /auction/past/auc-{id}/
- Individual auction page: /auction/past/auc-{id}/
  → Links to /item/{id}/{Distillery}/{slug}.html
- Individual lot page: /item/{id}/{Distillery}/{slug}.html
  → Title: h1::text
  → Price: span.GBP.show::text  (or .multiprice .GBP::text)
  → Date: text matching "Sold DD/MM/YYYY"
  → Distillery: 3rd URL segment, hyphens → spaces
  → Source ID: 2nd URL segment (numeric lot ID)
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


class WhiskyHammerSpider(BaseAuctionSpider):
    """
    Spider for scraping Whisky Hammer past auction results.

    Site structure (as of May 2026):
    - Past auctions: /previous-auctions
    - Auction results: /auction/past/auc-{id}/
    - Individual lots: /item/{lot_id}/{Distillery}/{slug}.html

    Prices are displayed as GBP with buyer's premium already included
    in the 'span.GBP.show' element.  The hammer price (before premium)
    is not separately shown, so total_price == the displayed GBP figure
    and hammer_price is back-calculated using DEFAULT_BUYERS_PREMIUM.
    """

    name = "whisky_hammer"
    auction_house = "WHISKY_HAMMER"
    allowed_domains = ["whiskyhammer.com", "www.whiskyhammer.com"]

    start_urls = ["https://www.whiskyhammer.com/previous-auctions"]

    custom_settings = {
        "DOWNLOAD_DELAY": 3.0,
        "CONCURRENT_REQUESTS": 1,
        "ROBOTSTXT_OBEY": True,
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 60000,
        "CLOSESPIDER_ITEMCOUNT": 50,
    }

    DEFAULT_BUYERS_PREMIUM = 15.0  # 15%

    # Only crawl the N most recent past auctions to avoid timeouts
    MAX_RECENT_AUCTIONS = 5

    # ------------------------------------------------------------------ #
    # Level 1 – past-auctions listing page
    # ------------------------------------------------------------------ #

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """
        Parse /previous-auctions listing page.

        Extracts links to individual past auction pages, keeps only the
        MAX_RECENT_AUCTIONS most recent (highest auc-N number), and
        follows pagination if present.
        """
        logger.info(f"Parsing past-auctions listing: {response.url}")

        # Collect all hrefs that match /auction/past/auc-{N}/
        raw_links = response.css("a[href*='/auction/past/auc-']::attr(href)").getall()

        # Deduplicate while preserving order
        seen = set()
        unique_links = []
        for link in raw_links:
            normalised = link.rstrip("/")
            if normalised not in seen:
                seen.add(normalised)
                unique_links.append(link)

        # Sort by auction number descending (highest = most recent)
        def _auction_num(href: str) -> int:
            m = re.search(r"/auc-(\d+)", href)
            return int(m.group(1)) if m else 0

        recent = sorted(unique_links, key=_auction_num, reverse=True)[: self.MAX_RECENT_AUCTIONS]
        logger.info(
            f"Found {len(unique_links)} past-auction links; "
            f"following {len(recent)} most recent (limit={self.MAX_RECENT_AUCTIONS})"
        )

        for auction_href in recent:
            yield scrapy.Request(
                urljoin(response.url, auction_href),
                callback=self.parse_auction,
                errback=self.handle_error,
            )

        # Follow pagination on the listing page
        next_page = self._find_next_page(response)
        if next_page:
            logger.info(f"Following pagination to: {next_page}")
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse,
                errback=self.handle_error,
            )

    # ------------------------------------------------------------------ #
    # Level 2 – individual auction page
    # ------------------------------------------------------------------ #

    def parse_auction(self, response: Response) -> Generator[Any, None, None]:
        """
        Parse individual past auction page, e.g. /auction/past/auc-128/.

        Extracts links to individual lot pages and the auction name/date.
        """
        logger.info(f"Parsing auction page: {response.url}")

        # Auction name from <h1> or page <title>
        auction_name = (
            response.css("h1::text").get("").strip()
            or response.css("title::text").get("").strip()
        )

        # Try to get a date from the auction page itself
        auction_date = self._extract_auction_date(response)

        # Lot links: /item/{numeric_id}/{Distillery}/{slug}.html
        lot_hrefs = response.css("a[href*='/item/']::attr(href)").getall()
        lot_hrefs = [h for h in lot_hrefs if re.search(r"/item/\d+/", h)]

        # Deduplicate
        lot_hrefs = list(dict.fromkeys(lot_hrefs))

        logger.info(
            f"Auction '{auction_name}': found {len(lot_hrefs)} lot links"
        )

        for lot_href in lot_hrefs:
            yield scrapy.Request(
                urljoin(response.url, lot_href),
                callback=self.parse_lot,
                meta={
                    "auction_name": auction_name,
                    "auction_date": auction_date,
                },
                errback=self.handle_error,
            )

        # Pagination within the auction page
        next_page = self._find_next_page(response)
        if next_page:
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse_auction,
                meta={
                    "auction_name": auction_name,
                    "auction_date": auction_date,
                },
                errback=self.handle_error,
            )

    # ------------------------------------------------------------------ #
    # Level 3 – individual lot page
    # ------------------------------------------------------------------ #

    def parse_lot(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """
        Parse individual lot page, e.g. /item/234081/Springbank/...html.

        Extracts title, price, date, distillery and image.
        """
        logger.debug(f"Parsing lot: {response.url}")

        # --- Source ID (2nd URL path segment, the numeric lot ID) ---
        source_id = self._extract_source_id(response.url)
        if not source_id:
            logger.warning(f"Could not extract source_id from: {response.url}")
            return

        # --- Title ---
        raw_title = response.css("h1::text").get("").strip()
        if not raw_title:
            logger.warning(f"No title found at: {response.url}")
            return

        # --- Description ---
        raw_description = " ".join(
            response.css(
                ".lot-description *::text, .description *::text, "
                ".item-description *::text, .lot-detail *::text"
            ).getall()
        ).strip()

        # --- Distillery hint from URL (3rd path segment, hyphens → spaces) ---
        url_distillery = self._distillery_from_url(response.url)

        # Build base item (auto-extracts age, ABV, vintage, etc.)
        item = self.create_item(
            response=response,
            source_id=source_id,
            raw_title=raw_title,
            raw_description=raw_description,
            auction_name=response.meta.get("auction_name", ""),
        )

        # If auto-extraction didn't find a distillery, use the URL hint
        if not item.get("distillery") and url_distillery:
            item["distillery"] = url_distillery

        # --- Price ---
        total_price = self._extract_total_price(response)
        item["currency"] = "GBP"

        if total_price and total_price > 0:
            item["total_price"] = total_price
            # Back-calculate hammer price from the displayed total
            premium_rate = self.DEFAULT_BUYERS_PREMIUM / 100
            item["hammer_price"] = round(total_price / (1 + premium_rate), 2)
            item["buyers_premium_pct"] = self.DEFAULT_BUYERS_PREMIUM
            item["sold"] = True
        else:
            item["total_price"] = None
            item["hammer_price"] = None
            item["buyers_premium_pct"] = self.DEFAULT_BUYERS_PREMIUM
            item["sold"] = self._check_if_sold(response)

        # --- Date ---
        lot_date = self._extract_sold_date(response)
        item["auction_date"] = lot_date or response.meta.get("auction_date")

        # --- Image ---
        item["image_url"] = self._extract_image(response)

        self.items_scraped += 1
        yield item

    # ------------------------------------------------------------------ #
    # Extraction helpers
    # ------------------------------------------------------------------ #

    def _extract_source_id(self, url: str) -> str | None:
        """
        Extract numeric lot ID from URL.

        URL pattern: /item/{lot_id}/{Distillery}/{slug}.html
        """
        m = re.search(r"/item/(\d+)/", url)
        return m.group(1) if m else None

    def _distillery_from_url(self, url: str) -> str | None:
        """
        Derive distillery name from the 3rd URL path segment.

        e.g. /item/234081/Springbank/... → "Springbank"
             /item/234081/Glen-Grant/...  → "Glen Grant"
        """
        m = re.search(r"/item/\d+/([^/]+)/", url)
        if m:
            raw = m.group(1)
            # Replace hyphens with spaces and title-case
            return raw.replace("-", " ").title()
        return None

    def _extract_total_price(self, response: Response) -> float | None:
        """
        Extract the displayed GBP price (total including buyer's premium).

        Primary selector:  span.GBP.show::text  → "£2,541.67"
        Fallback selector: .multiprice .GBP::text
        Fallback text:     regex on full page text
        """
        # Primary CSS selectors
        selectors = [
            "span.GBP.show::text",
            ".multiprice .GBP::text",
            ".price.GBP::text",
            ".winning-price::text",
            ".hammer-price::text",
            ".sold-price::text",
            ".result-price::text",
        ]
        for selector in selectors:
            text = response.css(selector).get()
            if text:
                price = parse_price(text)
                if price and price > 0:
                    return price

        # Fallback: scan page text for "Sold DD/MM/YYYY £X,XXX" or similar
        page_text = " ".join(response.css("*::text").getall())
        patterns = [
            r"(?:sold|hammer)[^£$]*£\s*([\d,]+(?:\.\d{2})?)",
            r"£\s*([\d,]+(?:\.\d{2})?)\s*(?:sold|hammer|won)",
            r"winning\s+bid[^£$]*£\s*([\d,]+(?:\.\d{2})?)",
        ]
        for pattern in patterns:
            m = re.search(pattern, page_text, re.IGNORECASE)
            if m:
                price = parse_price(m.group(1))
                if price and price > 0:
                    return price

        return None

    def _extract_sold_date(self, response: Response) -> str | None:
        """
        Extract sale date from text matching "Sold DD/MM/YYYY".

        Falls back to dateutil for other date formats found on the page.
        """
        page_text = " ".join(response.css("*::text").getall())

        # Primary: "Sold 25/01/2026"
        m = re.search(r"[Ss]old\s+(\d{2}/\d{2}/\d{4})", page_text)
        if m:
            return self._parse_date_dmy(m.group(1))

        # Secondary: any date near "sold"
        m = re.search(
            r"[Ss]old[^\d]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})", page_text
        )
        if m:
            return self._parse_date_dmy(m.group(1))

        # Tertiary: <time datetime="...">
        datetime_attr = response.css("time::attr(datetime)").get()
        if datetime_attr:
            return self._parse_date_dmy(datetime_attr)

        return None

    def _extract_auction_date(self, response: Response) -> str | None:
        """Extract a generic date from an auction listing page."""
        selectors = [
            ".auction-date::text",
            ".closing-date::text",
            ".end-date::text",
            "time::attr(datetime)",
        ]
        for selector in selectors:
            text = response.css(selector).get()
            if text:
                parsed = self._parse_date_dmy(text.strip())
                if parsed:
                    return parsed

        # Regex fallback on page text
        page_text = " ".join(response.css("*::text").getall())
        m = re.search(
            r"(?:closed|ended|finished)[^\d]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
            page_text,
            re.IGNORECASE,
        )
        if m:
            return self._parse_date_dmy(m.group(1))

        return None

    def _extract_image(self, response: Response) -> str | None:
        """Extract primary lot image URL."""
        selectors = [
            "img.lot-image::attr(src)",
            ".item-image img::attr(src)",
            "img[class*='whisky']::attr(src)",
            ".main-image img::attr(src)",
            ".product-image img::attr(src)",
            ".item-photo img::attr(src)",
        ]
        for selector in selectors:
            src = response.css(selector).get()
            if src:
                return urljoin(response.url, src)

        return None

    def _check_if_sold(self, response: Response) -> bool:
        """Determine whether the lot sold."""
        page_text = " ".join(response.css("*::text").getall()).lower()

        unsold_markers = [
            "unsold", "not sold", "passed", "no sale",
            "withdrawn", "reserve not met",
        ]
        for marker in unsold_markers:
            if marker in page_text:
                return False

        if self._extract_total_price(response):
            return True

        return False

    def _find_next_page(self, response: Response) -> str | None:
        """Return the href of the next pagination page, or None."""
        selectors = [
            "a.next::attr(href)",
            "a[rel='next']::attr(href)",
            "li.next a::attr(href)",
            ".pagination a.next::attr(href)",
            ".pagination-next a::attr(href)",
            "a:contains('Next')::attr(href)",
            "a:contains('›')::attr(href)",
            "a:contains('»')::attr(href)",
        ]
        for selector in selectors:
            href = response.css(selector).get()
            if href:
                return href
        return None

    # ------------------------------------------------------------------ #
    # Date parsing
    # ------------------------------------------------------------------ #

    def _parse_date_dmy(self, date_text: str) -> str | None:
        """
        Parse a date string to ISO format (YYYY-MM-DD).

        Handles:
        - DD/MM/YYYY  (primary Whisky Hammer format)
        - ISO 8601 passthrough
        - Any format via dateutil (dayfirst=True)
        """
        if not date_text:
            return None

        date_text = date_text.strip()

        # Already ISO
        if re.match(r"\d{4}-\d{2}-\d{2}", date_text):
            return date_text[:10]

        # DD/MM/YYYY
        m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", date_text)
        if m:
            day, month, year = m.group(1), m.group(2), m.group(3)
            return f"{year}-{month}-{day}"

        # Generic fallback via dateutil
        try:
            from dateutil import parser as dateutil_parser
            parsed = dateutil_parser.parse(date_text, dayfirst=True)
            return parsed.strftime("%Y-%m-%d")
        except Exception:
            return None
