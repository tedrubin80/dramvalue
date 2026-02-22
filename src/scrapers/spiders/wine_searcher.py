"""
Spider for Wine-Searcher (wine-searcher.com).

Price comparison site for wine and spirits with retail offers and price history.
"""

import re
import logging
from datetime import datetime
from typing import Generator, Any
from urllib.parse import urljoin, urlencode

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


class WineSearcherSpider(scrapy.Spider):
    """
    Spider for scraping Wine-Searcher spirits section.

    Site structure:
    - /find/{query}/spirits - Search results
    - /wine/{slug} - Product pages with price history
    - /merchant/{id} - Retailer listings

    Provides retail price comparison across regions.
    """

    name = "wine_searcher"
    allowed_domains = ["wine-searcher.com", "www.wine-searcher.com"]

    # Start with spirits category browsing
    start_urls = [
        "https://www.wine-searcher.com/find/whisky/1/worldwide/-/$/a",
        "https://www.wine-searcher.com/find/scotch+whisky/1/worldwide/-/$/a",
        "https://www.wine-searcher.com/find/bourbon/1/worldwide/-/$/a",
        "https://www.wine-searcher.com/find/japanese+whisky/1/worldwide/-/$/a",
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 6.0,  # Be respectful - commercial site
        "CONCURRENT_REQUESTS": 1,
        "ROBOTSTXT_OBEY": True,
        "USER_AGENT": "Mozilla/5.0 (compatible; DramValueBot/1.0; +https://dramvalue.com/bot)",
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
        """Parse search results page."""
        logger.info(f"Parsing search results: {response.url}")

        # Extract product links
        product_links = response.css("a[href*='/wine/']::attr(href)").getall()
        product_links += response.css(".wine-card a::attr(href)").getall()

        logger.info(f"Found {len(product_links)} product links")

        for link in set(product_links):
            if "/wine/" in link:
                full_url = urljoin(response.url, link)
                yield scrapy.Request(
                    full_url,
                    callback=self.parse_product,
                    errback=self.handle_error,
                )

        # Pagination
        next_page = response.css("a.next::attr(href), a[rel='next']::attr(href)").get()
        if not next_page:
            # Try page number links
            current_page = response.css(".pagination .active::text").get()
            if current_page:
                try:
                    next_num = int(current_page) + 1
                    next_page = response.css(f".pagination a:contains('{next_num}')::attr(href)").get()
                except ValueError:
                    pass

        if next_page:
            yield scrapy.Request(
                urljoin(response.url, next_page),
                callback=self.parse,
                errback=self.handle_error,
            )

    def parse_product(self, response: Response) -> Generator[RetailPriceItem, None, None]:
        """Parse product page with prices from multiple retailers."""
        logger.debug(f"Parsing product: {response.url}")

        raw_title = response.css("h1::text, .wine-name::text").get()
        if not raw_title:
            return

        raw_title = raw_title.strip()

        # Skip if not a whisky/spirit
        title_lower = raw_title.lower()
        if not any(w in title_lower for w in ["whisky", "whiskey", "bourbon", "scotch", "rye", "malt"]):
            return

        raw_description = " ".join(
            response.css(".wine-description *::text, .product-info *::text").getall()
        ).strip()

        # Extract prices from multiple retailers
        price_rows = response.css(".price-row, .offer-row, .merchant-price")

        if not price_rows:
            # Single price display
            price = self._extract_main_price(response)
            if price:
                item = self._create_item(response, raw_title, raw_description, price)
                if item:
                    yield item
            return

        # Multiple retailer prices
        for row in price_rows:
            price = self._extract_row_price(row)
            if not price or price <= 0:
                continue

            merchant = row.css(".merchant-name::text, .retailer::text").get("").strip()
            region = row.css(".region::text, .location::text").get("").strip()

            item = self._create_item(
                response,
                raw_title,
                raw_description,
                price,
                merchant=merchant,
                region=region,
            )
            if item:
                yield item

    def _create_item(
        self,
        response: Response,
        raw_title: str,
        raw_description: str,
        price: float,
        merchant: str = "",
        region: str = "",
    ) -> RetailPriceItem | None:
        """Create a RetailPriceItem."""
        source_id = self._generate_source_id(response.url, merchant)

        item = RetailPriceItem()

        # Source info
        item["source_id"] = source_id
        item["source_url"] = response.url
        item["source_name"] = f"Wine-Searcher ({merchant})" if merchant else "Wine-Searcher"
        item["source_type"] = "retail"

        # Raw content
        item["raw_title"] = raw_title
        item["raw_description"] = raw_description

        # Clean title
        item["bottle_name"] = clean_title(raw_title)

        # Extract bottle info
        full_text = f"{raw_title} {raw_description}"
        distillery, extracted_region = extract_distillery(full_text)
        item["distillery"] = distillery
        item["region"] = region or extracted_region
        item["age_statement"] = extract_age(full_text)
        item["size_ml"] = extract_size_ml(full_text) or 700
        item["abv"] = extract_abv(full_text)

        # Price
        item["price"] = price
        item["currency"] = self._detect_currency(response)
        item["original_price"] = None

        # Availability
        item["in_stock"] = True  # Listed means available

        # Image
        item["image_url"] = response.css(".wine-image img::attr(src), .product-image img::attr(src)").get()

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

    def _extract_main_price(self, response: Response) -> float | None:
        """Extract main price from product page."""
        selectors = [
            ".price::text",
            ".wine-price::text",
            "*[itemprop='price']::attr(content)",
            ".average-price::text",
        ]

        for selector in selectors:
            price_text = response.css(selector).get()
            if price_text:
                price = parse_price(price_text)
                if price and price > 0:
                    return price

        return None

    def _extract_row_price(self, row) -> float | None:
        """Extract price from a retailer row."""
        price_text = row.css(".price::text, .offer-price::text").get()
        if price_text:
            return parse_price(price_text)
        return None

    def _generate_source_id(self, url: str, merchant: str) -> str:
        """Generate unique source ID."""
        # Extract wine ID from URL
        match = re.search(r"/wine/([^/]+)", url)
        wine_slug = match.group(1) if match else "unknown"

        # Create ID from URL slug and merchant
        merchant_slug = re.sub(r"[^a-z0-9]", "", merchant.lower())[:20] if merchant else "ws"
        return f"ws-{wine_slug[:30]}-{merchant_slug}"

    def _detect_currency(self, response: Response) -> str:
        """Detect currency from page."""
        # Check URL for region
        url = response.url.lower()
        if "/uk/" in url or "gbp" in url:
            return "GBP"
        elif "/eu/" in url or "eur" in url:
            return "EUR"

        # Check page content
        page_text = " ".join(response.css(".price *::text").getall())
        if "£" in page_text:
            return "GBP"
        elif "€" in page_text:
            return "EUR"

        return "USD"  # Default

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
            f"  Items scraped: {self.items_scraped}\n"
            f"  Errors: {self.items_errored}"
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
