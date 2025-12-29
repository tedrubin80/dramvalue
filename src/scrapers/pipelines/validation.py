"""
Validation pipeline for WTracker scrapers.

First pipeline stage: validates scraped data before processing.
"""

import logging
from datetime import datetime, date
from typing import List

from scrapy.exceptions import DropItem

from src.scrapers.items import AuctionLotItem

logger = logging.getLogger(__name__)


class ValidationPipeline:
    """
    Validates scraped auction lot data.

    Validation rules:
    1. Required fields must be present and non-empty
    2. Price must be positive (if sold)
    3. Date must be valid and not in the future
    4. Currency must be recognized
    5. Size and ABV must be in valid ranges

    Items failing validation are dropped and logged.
    """

    # Required fields that must be present
    REQUIRED_FIELDS = [
        "source_id",
        "source_url",
        "auction_house",
        "raw_title",
    ]

    # Supported currencies
    VALID_CURRENCIES = {"GBP", "USD", "EUR", "CHF", "JPY", "AUD", "CAD", "HKD"}

    # Valid ranges
    MIN_PRICE = 1  # Minimum price in any currency
    MAX_PRICE = 10_000_000  # Maximum reasonable price
    MIN_SIZE_ML = 20  # Miniature bottles
    MAX_SIZE_ML = 4500  # Large bottles
    MIN_ABV = 35.0  # Minimum ABV
    MAX_ABV = 75.0  # Maximum ABV (cask strength)
    MIN_AGE = 0  # NAS or very young
    MAX_AGE = 100  # Very old whisky

    def process_item(self, item: AuctionLotItem, spider) -> AuctionLotItem:
        """
        Validate item data.

        Args:
            item: The scraped item to validate
            spider: The spider that scraped the item

        Returns:
            The validated item

        Raises:
            DropItem: If validation fails
        """
        errors: List[str] = []

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            value = item.get(field)
            if not value or (isinstance(value, str) and not value.strip()):
                errors.append(f"Missing required field: {field}")

        # Validate price
        if item.get("sold") and item.get("hammer_price"):
            price = item["hammer_price"]
            if not isinstance(price, (int, float)):
                errors.append(f"Invalid price type: {type(price)}")
            elif price < self.MIN_PRICE:
                errors.append(f"Price too low: {price}")
            elif price > self.MAX_PRICE:
                errors.append(f"Price suspiciously high: {price}")
                item["requires_review"] = True  # Flag but don't drop

        # Validate total price consistency
        if item.get("total_price") and item.get("hammer_price"):
            if item["total_price"] < item["hammer_price"]:
                errors.append("Total price less than hammer price")

        # Validate currency
        currency = item.get("currency", "GBP")
        if currency and currency not in self.VALID_CURRENCIES:
            errors.append(f"Unknown currency: {currency}")

        # Validate date
        auction_date = item.get("auction_date")
        if auction_date:
            try:
                if isinstance(auction_date, str):
                    parsed_date = datetime.fromisoformat(auction_date.split("T")[0])
                elif isinstance(auction_date, date):
                    parsed_date = datetime.combine(auction_date, datetime.min.time())
                else:
                    parsed_date = auction_date

                # Date should not be in the future
                if parsed_date.date() > date.today():
                    errors.append(f"Auction date in future: {auction_date}")

                # Date should not be too old (before 2015)
                if parsed_date.year < 2015:
                    logger.info(f"Old auction from {parsed_date.year}, flagging for review")
                    item["requires_review"] = True

            except (ValueError, TypeError) as e:
                errors.append(f"Invalid date format: {auction_date} ({e})")

        # Validate bottle specifications
        if item.get("size_ml"):
            size = item["size_ml"]
            if not (self.MIN_SIZE_ML <= size <= self.MAX_SIZE_ML):
                errors.append(f"Invalid size: {size}ml")

        if item.get("abv"):
            abv = item["abv"]
            if not (self.MIN_ABV <= abv <= self.MAX_ABV):
                errors.append(f"Invalid ABV: {abv}%")

        if item.get("age_statement"):
            age = item["age_statement"]
            if not (self.MIN_AGE <= age <= self.MAX_AGE):
                errors.append(f"Invalid age: {age}")

        # Validate title length
        raw_title = item.get("raw_title", "")
        if len(raw_title) < 5:
            errors.append(f"Title too short: '{raw_title}'")
        elif len(raw_title) > 500:
            item["raw_title"] = raw_title[:500]
            logger.debug("Truncated long title")

        # Store validation errors
        item["validation_errors"] = errors

        # Drop if critical errors
        critical_errors = [e for e in errors if "Missing required" in e]
        if critical_errors:
            spider.items_errored += 1
            logger.warning(f"Validation failed for {item.get('source_id')}: {critical_errors}")
            raise DropItem(f"Validation failed: {critical_errors}")

        # Log non-critical errors but continue
        if errors:
            logger.debug(f"Validation warnings for {item.get('source_id')}: {errors}")

        logger.debug(f"Validated: {item.get('source_id')}")
        return item
