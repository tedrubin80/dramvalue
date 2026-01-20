"""
Fine Drams retail spider.

Scrapes whisky prices from finedrams.com - a European retailer
with excellent metadata (ABV, vintage, age, region, bottler).
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


class FineDramsSpider(scrapy.Spider):
    """
    Spider for finedrams.com retail prices.

    Fine Drams is a European retailer with:
    - 1,500+ whisky products
    - EUR pricing
    - Excellent metadata (ABV, volume, vintage, bottler, region)
    - Pagination via ?page=N
    """

    name = "fine_drams"
    allowed_domains = ["finedrams.com"]
    start_urls = ["https://www.finedrams.com/whisky?page=1"]

    custom_settings = {
        "DOWNLOAD_DELAY": 2.0,
        "CONCURRENT_REQUESTS": 1,
        "ROBOTSTXT_OBEY": True,
        "USER_AGENT": "WTracker/1.0 (Educational whisky price tracker)",
    }

    # EUR to USD conversion rate (update periodically)
    EUR_TO_USD = 1.08

    def __init__(self, *args, max_pages: int = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_pages = int(max_pages) if max_pages else None
        self.current_page = 1
        self.items_scraped = 0
        self.started_at = datetime.utcnow()

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """Parse product listing page."""
        # Extract products from the page
        products = response.css("div.product-item, article.product")

        if not products:
            # Try alternative selectors
            products = response.css("div[class*='product']")

        logger.info(f"Found {len(products)} products on page {self.current_page}")

        for product in products:
            item = self.parse_product(response, product)
            if item:
                self.items_scraped += 1
                yield item

        # Handle pagination
        # Look for next page link or increment page number
        next_page = response.css("a.next::attr(href), a[rel='next']::attr(href)").get()

        if not next_page:
            # Try to find pagination by page number
            current_url = response.url
            if "page=" in current_url:
                self.current_page += 1
                next_page = re.sub(r"page=\d+", f"page={self.current_page}", current_url)

        if next_page and (self.max_pages is None or self.current_page < self.max_pages):
            # Check if there are still products (stop if empty page)
            if products:
                yield response.follow(next_page, callback=self.parse)

    def parse_product(self, response: Response, product) -> RetailPriceItem | None:
        """Parse a single product from the listing."""
        try:
            # Extract product URL and name
            link = product.css("a::attr(href)").get()
            title = product.css("h2::text, h3::text, .product-title::text, a::text").get()

            if not title:
                title = product.css("a::attr(title)").get()

            if not title or not link:
                return None

            title = title.strip()

            # Extract price
            price_text = product.css(".price::text, .product-price::text, span[class*='price']::text").get()
            price = None
            original_price = None

            if price_text:
                # Parse price like "36,00 €" or "€36.00"
                price_match = re.search(r"([\d,\.]+)\s*€|€\s*([\d,\.]+)", price_text)
                if price_match:
                    price_str = price_match.group(1) or price_match.group(2)
                    price_str = price_str.replace(",", ".")
                    price = float(price_str)

            # Check for original/sale price
            original_text = product.css(".original-price::text, .was-price::text, del::text").get()
            if original_text:
                orig_match = re.search(r"([\d,\.]+)\s*€|€\s*([\d,\.]+)", original_text)
                if orig_match:
                    orig_str = orig_match.group(1) or orig_match.group(2)
                    orig_str = orig_str.replace(",", ".")
                    original_price = float(orig_str)

            # Extract ABV and volume from title or separate fields
            abv_text = product.css(".abv::text, [class*='alcohol']::text").get()
            vol_text = product.css(".volume::text, [class*='volume']::text").get()

            abv = None
            size_ml = None

            if abv_text:
                abv_match = re.search(r"([\d\.]+)\s*%", abv_text)
                if abv_match:
                    abv = float(abv_match.group(1))

            if vol_text:
                vol_match = re.search(r"(\d+)\s*cl", vol_text, re.I)
                if vol_match:
                    size_ml = int(vol_match.group(1)) * 10
                else:
                    vol_match = re.search(r"(\d+)\s*ml", vol_text, re.I)
                    if vol_match:
                        size_ml = int(vol_match.group(1))

            # If not found in separate fields, extract from title
            if not abv:
                abv = extract_abv(title)
            if not size_ml:
                size_ml = extract_size_ml(title) or 700

            # Check stock status
            in_stock = True
            stock_text = product.css(".stock::text, .availability::text").get()
            if stock_text and ("out of stock" in stock_text.lower() or "sold out" in stock_text.lower()):
                in_stock = False

            # Get image
            image_url = product.css("img::attr(src), img::attr(data-src)").get()

            # Extract source ID from URL
            source_id = link.split("/")[-1] if link else None

            # Build full URL
            full_url = response.urljoin(link) if link else response.url

            # Create item
            item = RetailPriceItem()
            item["source_id"] = source_id
            item["source_url"] = full_url
            item["source_name"] = "Fine Drams"
            item["source_type"] = "retail"

            item["raw_title"] = title
            item["bottle_name"] = clean_title(title)

            # Extract structured data
            distillery, region = extract_distillery(title)
            item["distillery"] = distillery
            item["region"] = region
            item["age_statement"] = extract_age(title)
            item["vintage"] = extract_vintage(title)
            item["size_ml"] = size_ml
            item["abv"] = abv

            item["price"] = price
            item["original_price"] = original_price
            item["currency"] = "EUR"
            item["price_usd"] = round(price * self.EUR_TO_USD, 2) if price else None

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
            f"Fine Drams spider closed: {reason}\n"
            f"  Duration: {duration:.1f}s\n"
            f"  Items scraped: {self.items_scraped}\n"
            f"  Pages crawled: {self.current_page}"
        )
