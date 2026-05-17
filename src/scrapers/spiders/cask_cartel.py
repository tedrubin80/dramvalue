"""
CaskCartel retail spider.

Scrapes whisky prices from caskcartel.com - a US-based Shopify retailer
specialising in American whiskey, bourbon, scotch, and world whiskies.

Uses Shopify's /products.json API for efficient data extraction across
multiple whiskey-related collections.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Generator

import scrapy
from scrapy.http import Response

from src.scrapers.items import RetailPriceItem
from src.scrapers.utils.text import (
    clean_title,
    extract_age,
    extract_abv,
    extract_size_ml,
    extract_vintage,
    extract_distillery,
)

logger = logging.getLogger(__name__)

# Whiskey-related collections to scrape on caskcartel.com
COLLECTIONS = [
    "whiskey",
    "bourbon",
    "scotch-whisky",
    "japanese-whisky",
    "irish-whiskey",
    "rye-whisky",
]


class CaskCartelSpider(scrapy.Spider):
    """
    Spider for caskcartel.com retail prices.

    CaskCartel is a US Shopify store with:
    - Large selection of American whiskey, bourbon, scotch, and world whiskies
    - USD pricing
    - Multiple whiskey-specific collections
    - Shopify JSON API available
    """

    name = "cask_cartel"
    allowed_domains = ["caskcartel.com"]

    # Start from the first collection, first page
    start_urls = [
        f"https://caskcartel.com/collections/{COLLECTIONS[0]}/products.json?limit=250&page=1"
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 2.0,
        "CONCURRENT_REQUESTS": 1,
        "ROBOTSTXT_OBEY": True,
        "USER_AGENT": "DramValue/1.0 (whisky price tracker)",
    }

    def __init__(self, *args, max_pages: int = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_pages = int(max_pages) if max_pages else 20
        self.items_scraped = 0
        self.started_at = datetime.utcnow()

        # Track seen source_id values to deduplicate across collections
        self._seen_ids: set = set()

        # Per-collection page tracking: {collection: current_page}
        self._collection_pages: dict = {col: 1 for col in COLLECTIONS}

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """Parse a Shopify products.json response for a collection page."""
        # Determine which collection this response belongs to
        collection = self._collection_from_url(response.url)
        current_page = self._collection_pages.get(collection, 1)

        try:
            data = json.loads(response.text)
            products = data.get("products", [])

            logger.info(
                f"CaskCartel [{collection}] page {current_page}: "
                f"found {len(products)} products"
            )

            for product in products:
                source_id = str(product.get("id", ""))
                if source_id in self._seen_ids:
                    logger.debug(f"Skipping duplicate product id={source_id}")
                    continue
                self._seen_ids.add(source_id)

                item = self.parse_product(product)
                if item:
                    self.items_scraped += 1
                    yield item

            # Paginate within the same collection if the page was full
            if len(products) == 250 and current_page < self.max_pages:
                next_page = current_page + 1
                self._collection_pages[collection] = next_page
                next_url = (
                    f"https://caskcartel.com/collections/{collection}"
                    f"/products.json?limit=250&page={next_page}"
                )
                yield scrapy.Request(next_url, callback=self.parse)
            else:
                # Move on to the next collection (if any remain)
                yield from self._next_collection_request(collection)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from {response.url}: {e}")
            # Still try the next collection so one bad response doesn't stall all
            yield from self._next_collection_request(collection)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _collection_from_url(self, url: str) -> str:
        """Extract the collection slug from a products.json URL."""
        for col in COLLECTIONS:
            if f"/collections/{col}/" in url:
                return col
        # Fallback: parse from URL path
        match = re.search(r"/collections/([^/]+)/products\.json", url)
        return match.group(1) if match else COLLECTIONS[0]

    def _next_collection_request(
        self, finished_collection: str
    ) -> Generator[scrapy.Request, None, None]:
        """Yield a Request for the first page of the next unstarted collection."""
        idx = COLLECTIONS.index(finished_collection) if finished_collection in COLLECTIONS else -1
        for col in COLLECTIONS[idx + 1 :]:
            url = (
                f"https://caskcartel.com/collections/{col}"
                f"/products.json?limit=250&page=1"
            )
            logger.info(f"CaskCartel: moving to collection '{col}'")
            yield scrapy.Request(url, callback=self.parse)
            return  # Only kick off one collection at a time (sequential)

    def parse_product(self, product: dict) -> RetailPriceItem | None:
        """Parse a single product from Shopify JSON into a RetailPriceItem."""
        try:
            title = product.get("title", "")
            if not title:
                return None

            # First available variant is the canonical listing
            variants = product.get("variants", [])
            if not variants:
                return None

            variant = variants[0]
            price_str = variant.get("price", "0") or "0"
            price = float(price_str)
            if price <= 0:
                return None

            compare_str = variant.get("compare_at_price")
            original_price = float(compare_str) if compare_str else None

            in_stock = variant.get("available", False)

            handle = product.get("handle", "")
            source_url = f"https://caskcartel.com/products/{handle}"

            images = product.get("images", [])
            image_url = images[0].get("src") if images else None

            tags = product.get("tags", [])
            vendor = product.get("vendor", "")

            # Extract metadata from tags where possible
            abv = None
            size_ml = None
            region = None
            bottler = None

            for tag in tags:
                tag_lower = tag.lower()

                # ABV
                abv_match = re.search(r"(\d+(?:\.\d+)?)\s*%", tag)
                if abv_match and abv is None:
                    abv = float(abv_match.group(1))

                # Size (cl or ml)
                size_cl = re.search(r"(\d+)\s*cl", tag_lower)
                if size_cl and size_ml is None:
                    size_ml = int(size_cl.group(1)) * 10

                size_ml_tag = re.search(r"(\d+)\s*ml", tag_lower)
                if size_ml_tag and size_ml is None:
                    size_ml = int(size_ml_tag.group(1))

                # Region keywords
                if tag_lower in (
                    "speyside", "islay", "highland", "lowland",
                    "campbeltown", "islands", "kentucky", "tennessee",
                ):
                    region = tag.title()

                # Bottler
                if "independent" in tag_lower or tag_lower in (
                    "signatory", "gordon & macphail", "cadenhead",
                ):
                    bottler = tag

            # Fall back to title-level extraction
            if not abv:
                abv = extract_abv(title)
            if not size_ml:
                # US standard is 750 ml
                size_ml = extract_size_ml(title) or 750

            distillery, extracted_region = extract_distillery(title)
            if not region and extracted_region:
                region = extracted_region

            item = RetailPriceItem()
            item["source_id"] = str(product.get("id", ""))
            item["source_url"] = source_url
            item["source_name"] = "CaskCartel"
            item["source_type"] = "retail"

            item["raw_title"] = title
            item["raw_description"] = (
                product.get("body_html", "")[:500]
                if product.get("body_html")
                else ""
            )
            item["bottle_name"] = clean_title(title)

            item["distillery"] = distillery or vendor
            item["region"] = region
            item["age_statement"] = extract_age(title)
            item["vintage"] = extract_vintage(title)
            item["size_ml"] = size_ml
            item["abv"] = abv
            item["bottler"] = bottler

            # USD pricing — no conversion needed
            item["price"] = price
            item["original_price"] = original_price
            item["currency"] = "USD"
            item["price_usd"] = round(price, 2)

            item["in_stock"] = in_stock
            item["image_url"] = image_url
            item["scraped_at"] = datetime.utcnow().isoformat()
            item["spider_name"] = self.name

            return item

        except Exception as e:
            logger.error(f"Error parsing CaskCartel product: {e}")
            return None

    def closed(self, reason: str):
        """Log summary statistics when spider finishes."""
        duration = (datetime.utcnow() - self.started_at).total_seconds()
        logger.info(
            f"CaskCartel spider closed: {reason}\n"
            f"  Duration: {duration:.1f}s\n"
            f"  Items scraped: {self.items_scraped}\n"
            f"  Unique product IDs seen: {len(self._seen_ids)}"
        )
