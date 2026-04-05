#!/usr/bin/env python3
"""
Script to scrape retail prices from online bottle shops.

Usage:
    python scripts/scrape_retail.py [spider_name] [--max-pages N]

Examples:
    python scripts/scrape_retail.py whisky_barrel --max-pages 5
    python scripts/scrape_retail.py dekanta
    python scripts/scrape_retail.py all
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from decimal import Decimal

import httpx

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.models.bottle import Bottle, SpiritCategory
from src.models.price import Price, PriceSource

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

import re
import unicodedata

def normalize_bottle_name(name: str) -> str:
    """Create a normalized, searchable version of a bottle name."""
    # Convert to lowercase
    name = name.lower()
    # Remove accents
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
    # Remove special characters, keep alphanumeric and spaces
    name = re.sub(r'[^a-z0-9\s]', '', name)
    # Normalize whitespace
    name = ' '.join(name.split())
    return name

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://wtracker:wtracker_dev_password_2024@localhost:5434/wtracker")
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Currency conversion rates
RATES = {
    "GBP": 1.27,
    "EUR": 1.08,
    "USD": 1.0,
}


async def fetch_shopify_products(base_url: str, max_pages: int = 20) -> list[dict]:
    """Fetch all products from a Shopify store via JSON API."""
    products = []
    page = 1

    async with httpx.AsyncClient(timeout=30.0) as client:
        while page <= max_pages:
            url = f"{base_url}/products.json?limit=250&page={page}"
            logger.info(f"Fetching page {page}: {url}")

            try:
                response = await client.get(url, headers={
                    "User-Agent": "WTracker/1.0 (Educational whisky price tracker)"
                })
                response.raise_for_status()
                data = response.json()

                page_products = data.get("products", [])
                if not page_products:
                    break

                products.extend(page_products)
                logger.info(f"  Found {len(page_products)} products")

                if len(page_products) < 250:
                    break

                page += 1
                await asyncio.sleep(2)  # Rate limiting

            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break

    return products


def is_whisky_product(product: dict) -> bool:
    """Check if a product is whisky-related."""
    product_type = product.get("product_type", "").lower()
    title = product.get("title", "").lower()
    tags = [t.lower() for t in product.get("tags", [])]

    whisky_keywords = [
        "whisky", "whiskey", "bourbon", "scotch", "single malt", "blended",
        "rye", "irish", "japanese", "speyside", "islay", "highland",
        "yamazaki", "hakushu", "hibiki", "nikka", "macallan", "glenfiddich",
        "ardbeg", "lagavulin", "laphroaig", "glenlivet", "balvenie"
    ]

    return any(kw in product_type for kw in whisky_keywords) or \
           any(kw in title for kw in whisky_keywords) or \
           any(kw in " ".join(tags) for kw in whisky_keywords)


def extract_abv(text: str) -> float | None:
    """Extract ABV from text."""
    import re
    match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:abv|vol)?", text, re.I)
    if match:
        return float(match.group(1))
    return None


def extract_size_ml(text: str) -> int | None:
    """Extract bottle size in ml."""
    import re
    # Try cl first
    match = re.search(r"(\d+)\s*cl", text, re.I)
    if match:
        return int(match.group(1)) * 10
    # Try ml
    match = re.search(r"(\d+)\s*ml", text, re.I)
    if match:
        return int(match.group(1))
    return 700  # Default


async def find_or_create_bottle(session: AsyncSession, name: str, category: str = None) -> Bottle:
    """Find existing bottle or create new one."""
    normalized = normalize_bottle_name(name)

    # Search by normalized name for better matching
    result = await session.execute(
        select(Bottle).where(Bottle.normalized_name == normalized)
    )
    bottle = result.scalar_one_or_none()

    if not bottle:
        bottle = Bottle(
            name=name,
            normalized_name=normalized,
            category=SpiritCategory.SCOTCH_SINGLE_MALT,  # Default
            is_active=True,
        )
        session.add(bottle)
        await session.flush()
        logger.info(f"  Created new bottle: {name}")

    return bottle


async def save_retail_price(
    session: AsyncSession,
    bottle: Bottle,
    price: float,
    currency: str,
    source_name: str,
    source_url: str,
) -> Price:
    """Save a retail price to the database."""
    price_usd = price * RATES.get(currency, 1.0)

    price_record = Price(
        bottle_id=bottle.id,
        price=Decimal(str(price)),
        currency=currency,
        price_usd=Decimal(str(round(price_usd, 2))),
        source=PriceSource.RETAIL,
        source_name=source_name,
        source_url=source_url,
        is_sold=False,  # Retail = available, not sold
        transaction_date=datetime.utcnow(),
    )
    session.add(price_record)
    return price_record


async def scrape_whisky_barrel(max_pages: int = 20) -> int:
    """Scrape The Whisky Barrel."""
    logger.info("=== Scraping The Whisky Barrel ===")

    products = await fetch_shopify_products("https://www.thewhiskybarrel.com", max_pages)
    logger.info(f"Total products fetched: {len(products)}")

    count = 0
    async with async_session() as session:
        for product in products:
            if not is_whisky_product(product):
                continue

            title = product.get("title", "")
            variants = product.get("variants", [])
            if not variants:
                continue

            variant = variants[0]
            price = float(variant.get("price", 0))
            if price <= 0:
                continue

            handle = product.get("handle", "")
            source_url = f"https://www.thewhiskybarrel.com/products/{handle}"

            try:
                bottle = await find_or_create_bottle(session, title)
                await save_retail_price(
                    session, bottle, price, "GBP",
                    "The Whisky Barrel", source_url
                )
                count += 1

                if count % 50 == 0:
                    await session.commit()
                    logger.info(f"  Saved {count} prices...")

            except Exception as e:
                logger.error(f"Error saving {title}: {e}")
                await session.rollback()
                continue

        try:
            await session.commit()
        except Exception as e:
            logger.error(f"Final commit error: {e}")
            await session.rollback()

    logger.info(f"Whisky Barrel: Saved {count} prices")
    return count


async def scrape_dekanta(max_pages: int = 20) -> int:
    """Scrape Dekanta."""
    logger.info("=== Scraping Dekanta ===")

    products = await fetch_shopify_products("https://www.dekanta.com", max_pages)
    logger.info(f"Total products fetched: {len(products)}")

    count = 0
    async with async_session() as session:
        for product in products:
            if not is_whisky_product(product):
                continue

            title = product.get("title", "")
            variants = product.get("variants", [])
            if not variants:
                continue

            variant = variants[0]
            price = float(variant.get("price", 0))
            if price <= 0:
                continue

            handle = product.get("handle", "")
            source_url = f"https://www.dekanta.com/store/{handle}"

            try:
                bottle = await find_or_create_bottle(session, title)
                await save_retail_price(
                    session, bottle, price, "USD",
                    "Dekanta", source_url
                )
                count += 1

                if count % 50 == 0:
                    await session.commit()
                    logger.info(f"  Saved {count} prices...")

            except Exception as e:
                logger.error(f"Error saving {title}: {e}")
                await session.rollback()
                continue

        try:
            await session.commit()
        except Exception as e:
            logger.error(f"Final commit error: {e}")
            await session.rollback()

    logger.info(f"Dekanta: Saved {count} prices")
    return count


async def main():
    parser = argparse.ArgumentParser(description="Scrape retail whisky prices")
    parser.add_argument("spider", choices=["whisky_barrel", "dekanta", "all"],
                       help="Spider to run")
    parser.add_argument("--max-pages", type=int, default=20,
                       help="Maximum pages to scrape")
    args = parser.parse_args()

    total = 0

    if args.spider in ["whisky_barrel", "all"]:
        total += await scrape_whisky_barrel(args.max_pages)

    if args.spider in ["dekanta", "all"]:
        total += await scrape_dekanta(args.max_pages)

    logger.info(f"\n=== TOTAL: {total} prices saved ===")


if __name__ == "__main__":
    asyncio.run(main())
