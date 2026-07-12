"""
Deduplication pipeline for WTracker scrapers.

Third pipeline stage: checks for duplicate prices before database insertion.
"""

import logging
from typing import Set

from scrapy.exceptions import DropItem

from src.scrapers.items import AuctionLotItem, RetailPriceItem

logger = logging.getLogger(__name__)


class DeduplicationPipeline:
    """
    Checks for duplicate items within a scrape run.

    Deduplication strategy:
    1. In-memory tracking for current scrape run
    2. Database check happens in DatabasePipeline

    Deduplication key: (auction_house, source_id)
    """

    def __init__(self):
        """Initialize deduplication tracking."""
        self._seen_ids: Set[str] = set()

    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline from crawler."""
        return cls()

    def open_spider(self, spider):
        """Reset tracking when spider opens."""
        self._seen_ids.clear()
        logger.info(f"DeduplicationPipeline initialized for {spider.name}")

    def close_spider(self, spider):
        """Log statistics when spider closes."""
        logger.info(f"Deduplication checked {len(self._seen_ids)} unique items")

    def process_item(self, item: AuctionLotItem, spider) -> AuctionLotItem:
        """
        Check for duplicates.

        Args:
            item: The scraped item
            spider: The spider instance

        Returns:
            The item if not duplicate

        Raises:
            DropItem: If duplicate detected
        """
        # Create composite deduplication key
        source_id = item.get("source_id", "")

        if not source_id:
            logger.warning("Item missing source_id, cannot deduplicate")
            return item

        if isinstance(item, RetailPriceItem):
            source_key = item.get("source_name", spider.name)
        else:
            source_key = item.get("auction_house", "UNKNOWN")

        dedup_key = f"{source_key}:{source_id}"

        # Check in-memory cache (current scrape run)
        if dedup_key in self._seen_ids:
            spider.items_skipped += 1
            item["is_duplicate"] = True
            logger.debug(f"Duplicate in current run: {dedup_key}")
            raise DropItem(f"Duplicate item: {dedup_key}")

        # Add to seen set
        self._seen_ids.add(dedup_key)
        item["is_duplicate"] = False

        # Store the dedup key for database pipeline to use
        item["_dedup_key"] = dedup_key

        return item
