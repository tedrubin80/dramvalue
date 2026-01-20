"""
The Whisky Barrel retail spider.

Scrapes whisky prices from thewhiskybarrel.com - a UK Shopify retailer
with focus on independent bottlings.

Uses Shopify's /products.json API for efficient data extraction.
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


class WhiskyBarrelSpider(scrapy.Spider):
    """
    Spider for thewhiskybarrel.com retail prices.

    The Whisky Barrel is a UK Shopify store with:
    - 900+ whisky products
    - GBP pricing
    - Focus on independent bottlings
    - Shopify JSON API available
    """

    name = "whisky_barrel"
    allowed_domains = ["thewhiskybarrel.com"]

    # Shopify stores expose products via JSON API
    # Format: /products.json?limit=250&page=N
    start_urls = ["https://www.thewhiskybarrel.com/products.json?limit=250&page=1"]

    custom_settings = {
        "DOWNLOAD_DELAY": 2.0,
        "CONCURRENT_REQUESTS": 1,
        "ROBOTSTXT_OBEY": True,
        "USER_AGENT": "WTracker/1.0 (Educational whisky price tracker)",
    }

    # GBP to USD conversion rate
    GBP_TO_USD = 1.27

    def __init__(self, *args, max_pages: int = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_pages = int(max_pages) if max_pages else 20
        self.current_page = 1
        self.items_scraped = 0
        self.started_at = datetime.utcnow()

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """Parse Shopify products.json response."""
        try:
            data = json.loads(response.text)
            products = data.get("products", [])

            logger.info(f"Found {len(products)} products on page {self.current_page}")

            for product in products:
                # Filter for whisky products
                product_type = product.get("product_type", "").lower()
                tags = [t.lower() for t in product.get("tags", [])]

                # Include if it's whisky-related
                if any(kw in product_type for kw in ["whisky", "whiskey", "bourbon", "scotch"]) or \
                   any(kw in " ".join(tags) for kw in ["whisky", "whiskey", "bourbon", "scotch", "single malt"]):
                    item = self.parse_product(product)
                    if item:
                        self.items_scraped += 1
                        yield item

            # Paginate if more products
            if len(products) == 250 and self.current_page < self.max_pages:
                self.current_page += 1
                next_url = f"https://www.thewhiskybarrel.com/products.json?limit=250&page={self.current_page}"
                yield scrapy.Request(next_url, callback=self.parse)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")

    def parse_product(self, product: dict) -> RetailPriceItem | None:
        """Parse a single product from Shopify JSON."""
        try:
            title = product.get("title", "")
            if not title:
                return None

            # Get the first variant (usually the main product)
            variants = product.get("variants", [])
            if not variants:
                return None

            variant = variants[0]
            price = float(variant.get("price", 0))
            compare_price = variant.get("compare_at_price")
            original_price = float(compare_price) if compare_price else None

            # Check availability
            in_stock = variant.get("available", False)

            # Get product URL
            handle = product.get("handle", "")
            source_url = f"https://www.thewhiskybarrel.com/products/{handle}"

            # Get image
            images = product.get("images", [])
            image_url = images[0].get("src") if images else None

            # Extract from tags
            tags = product.get("tags", [])
            vendor = product.get("vendor", "")

            # Try to extract metadata from tags
            abv = None
            size_ml = None
            region = None
            bottler = None

            for tag in tags:
                tag_lower = tag.lower()

                # ABV
                abv_match = re.search(r"(\d+(?:\.\d+)?)\s*%", tag)
                if abv_match:
                    abv = float(abv_match.group(1))

                # Size
                size_match = re.search(r"(\d+)\s*cl", tag_lower)
                if size_match:
                    size_ml = int(size_match.group(1)) * 10

                # Region
                if tag_lower in ["speyside", "islay", "highland", "lowland", "campbeltown", "islands"]:
                    region = tag.title()

                # Independent bottler
                if "independent" in tag_lower or tag_lower in ["signatory", "gordon & macphail", "cadenhead"]:
                    bottler = tag

            # Extract from title if not in tags
            if not abv:
                abv = extract_abv(title)
            if not size_ml:
                size_ml = extract_size_ml(title) or 700

            # Extract distillery
            distillery, extracted_region = extract_distillery(title)
            if not region and extracted_region:
                region = extracted_region

            # Create item
            item = RetailPriceItem()
            item["source_id"] = str(product.get("id", ""))
            item["source_url"] = source_url
            item["source_name"] = "The Whisky Barrel"
            item["source_type"] = "retail"

            item["raw_title"] = title
            item["raw_description"] = product.get("body_html", "")[:500] if product.get("body_html") else ""
            item["bottle_name"] = clean_title(title)

            item["distillery"] = distillery or vendor
            item["region"] = region
            item["age_statement"] = extract_age(title)
            item["vintage"] = extract_vintage(title)
            item["size_ml"] = size_ml
            item["abv"] = abv
            item["bottler"] = bottler

            item["price"] = price
            item["original_price"] = original_price
            item["currency"] = "GBP"
            item["price_usd"] = round(price * self.GBP_TO_USD, 2) if price else None

            item["in_stock"] = in_stock
            item["image_url"] = image_url
            item["scraped_at"] = datetime.utcnow().isoformat()
            item["spider_name"] = self.name

            return item

        except Exception as e:
            logger.error(f"Error parsing product: {e}")
            return None

    def closed(self, reason: str):
        """Log statistics when spider closes."""
        duration = (datetime.utcnow() - self.started_at).total_seconds()
        logger.info(
            f"Whisky Barrel spider closed: {reason}\n"
            f"  Duration: {duration:.1f}s\n"
            f"  Items scraped: {self.items_scraped}\n"
            f"  Pages crawled: {self.current_page}"
        )
