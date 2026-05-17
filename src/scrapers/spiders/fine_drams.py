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
        # Site structure: <li><a class="product" href="/...">...</a></li>
        products = response.css("a.product")

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
        """Parse a single product from the listing.

        Site HTML: <a class="product" href="/slug.html">
          <div class="details"><h5 class="name">Title</h5><span class="name_extra">70 cl, 43%</span></div>
          <div class="price">36,00 €<div class="price_before">41,00 €</div></div>
        </a>
        """
        try:
            link = product.attrib.get("href")
            title = product.css("h5.name::text").get()

            if not title or not link:
                return None

            title = title.strip()

            # Price is the direct text node of div.price (excludes child div.price_before)
            price_text = product.css("div.price::text").get()
            price = None
            original_price = None

            if price_text:
                price_match = re.search(r"([\d]+[,.][\d]+)", price_text)
                if price_match:
                    price = float(price_match.group(1).replace(",", "."))

            # Original/before-sale price
            original_text = product.css("div.price_before::text").get()
            if original_text:
                orig_match = re.search(r"([\d]+[,.][\d]+)", original_text)
                if orig_match:
                    original_price = float(orig_match.group(1).replace(",", "."))

            # Size and ABV come from "name_extra" span: e.g. "70 cl, 43%"
            name_extra = product.css("span.name_extra::text").get() or ""
            abv = None
            size_ml = None

            vol_match = re.search(r"(\d+)\s*cl", name_extra, re.I)
            if vol_match:
                size_ml = int(vol_match.group(1)) * 10
            abv_match = re.search(r"([\d.]+)\s*%", name_extra)
            if abv_match:
                abv = float(abv_match.group(1))

            if not abv:
                abv = extract_abv(title)
            if not size_ml:
                size_ml = extract_size_ml(title) or 700

            # Stock: div.quantity text is "In stock" or similar
            quantity_text = product.css("div.quantity::text").get() or ""
            in_stock = "out of stock" not in quantity_text.lower() and "sold out" not in quantity_text.lower()

            image_url = product.css("img::attr(src)").get()

            # Source ID: slug from URL (strip .html extension)
            source_id = link.rstrip("/").split("/")[-1].replace(".html", "")

            full_url = response.urljoin(link)

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
