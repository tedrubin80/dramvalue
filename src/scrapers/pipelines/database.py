"""
Database pipeline for WTracker scrapers.

Final pipeline stage: persists validated, normalized data to PostgreSQL.
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from scrapy.exceptions import DropItem

from src.scrapers.items import AuctionLotItem, RetailPriceItem
from src.scrapers.utils.currency import convert_to_usd

logger = logging.getLogger(__name__)


class DatabasePipeline:
    """
    Persists scraped auction data to PostgreSQL.

    Handles:
    1. Database connection management
    2. Duplicate checking (database level)
    3. Bottle matching/creation
    4. Price insertion
    5. Audit logging

    Uses synchronous database operations for Scrapy compatibility.
    """

    def __init__(self):
        """Initialize the pipeline."""
        self.engine = None
        self.Session = None
        self._stats = {
            "processed": 0,
            "new_prices": 0,
            "new_bottles": 0,
            "duplicates": 0,
            "errors": 0,
        }

    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline from crawler."""
        return cls()

    def open_spider(self, spider):
        """
        Initialize database connection when spider opens.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        # Get database URL from settings
        from src.scrapers.settings import DATABASE_URL

        # Convert async URL to sync URL for Scrapy
        db_url = DATABASE_URL
        if "asyncpg" in db_url:
            db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
        if "+asyncpg" in db_url:
            db_url = db_url.replace("+asyncpg", "+psycopg2")

        self.engine = create_engine(db_url, pool_size=5, max_overflow=10)
        self.Session = sessionmaker(bind=self.engine)

        self._stats = {
            "processed": 0,
            "new_prices": 0,
            "new_bottles": 0,
            "duplicates": 0,
            "errors": 0,
        }

        logger.info(f"DatabasePipeline connected for {spider.name}")

    def close_spider(self, spider):
        """
        Close database connection and log stats.
        """
        if self.engine:
            self.engine.dispose()

        logger.info(f"Database pipeline stats: {self._stats}")

    def process_item(self, item, spider):
        """
        Persist item to database.

        Args:
            item: The validated, normalized item
            spider: The spider instance

        Returns:
            The item (for potential further processing)

        Raises:
            DropItem: If item cannot be saved
        """
        self._stats["processed"] += 1

        session = self.Session()
        try:
            # Check for existing price in database
            if self._price_exists(session, item):
                self._stats["duplicates"] += 1
                raise DropItem(f"Already in database: {item.get('source_id')}")

            # Get or create bottle
            bottle_id = self._get_or_create_bottle(session, item)

            if not bottle_id:
                # Failed to match or create bottle
                self._stats["errors"] += 1
                logger.warning(f"Could not match/create bottle for: {item.get('source_id')}")
                raise DropItem(f"Could not match bottle: {item.get('raw_title')}")

            # Create price record
            price_id = self._create_price(session, item, bottle_id)

            # Create audit log
            self._create_audit_log(session, item, price_id, bottle_id)

            session.commit()

            self._stats["new_prices"] += 1
            logger.info(f"Saved price {price_id} for bottle {bottle_id}: {item.get('source_id')}")

            return item

        except DropItem:
            session.rollback()
            raise

        except Exception as e:
            session.rollback()
            self._stats["errors"] += 1
            logger.error(f"Database error for {item.get('source_id')}: {e}")
            raise DropItem(f"Database error: {e}")

        finally:
            session.close()

    def _price_exists(self, session, item) -> bool:
        """Check if price already exists in database."""
        from sqlalchemy import select
        from src.models.price import Price

        source_id = str(item.get("source_id", ""))
        source_name = item.get("source_name") or item.get("auction_house")

        # Query for existing price with same source ID and source name
        query = select(Price.id).where(
            Price.source_id == source_id,
        )

        # Filter by source name if available
        if source_name:
            query = query.where(Price.source_name == source_name)

        result = session.execute(query)
        return result.scalar_one_or_none() is not None

    def _get_or_create_bottle(self, session, item) -> Optional[int]:
        """
        Get existing bottle or create new one.

        Returns bottle ID or None if unable to create.
        """
        from sqlalchemy import select, func
        from src.models.bottle import Bottle, SpiritCategory, BottleSize

        bottle_name = item.get("bottle_name", "").strip()
        if not bottle_name:
            return None

        # Create normalized name for matching
        normalized = bottle_name.lower().strip()

        # Try to find existing bottle
        query = select(Bottle).where(
            func.lower(Bottle.normalized_name) == normalized
        )
        result = session.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            item["matched_bottle_id"] = existing.id
            item["normalization_confidence"] = 1.0
            return existing.id

        # Create new bottle
        # Determine category
        category_str = item.get("category", "OTHER")
        try:
            category = SpiritCategory(category_str)
        except ValueError:
            category = SpiritCategory.OTHER

        # Determine size
        size_ml = item.get("size_ml", 700)
        if size_ml == 750:
            size = BottleSize.ML_750
        elif size_ml == 1000:
            size = BottleSize.ML_1000
        elif size_ml == 1750:
            size = BottleSize.ML_1750
        elif size_ml == 375:
            size = BottleSize.ML_375
        elif size_ml == 200:
            size = BottleSize.ML_200
        elif size_ml == 50:
            size = BottleSize.ML_50
        else:
            size = BottleSize.ML_700

        bottle = Bottle(
            name=bottle_name[:255],
            normalized_name=normalized[:255],
            distillery=item.get("distillery", "")[:100] if item.get("distillery") else None,
            category=category,
            age_statement=item.get("age_statement"),
            proof=item.get("proof"),
            size=size,
            size_ml=size_ml,
            is_active=True,
        )

        session.add(bottle)
        session.flush()  # Get the ID

        self._stats["new_bottles"] += 1
        item["matched_bottle_id"] = bottle.id
        item["normalization_confidence"] = 0.8  # Lower confidence for new bottles

        logger.info(f"Created new bottle: {bottle.name} (ID: {bottle.id})")
        return bottle.id

    def _create_price(self, session, item, bottle_id: int) -> int:
        """Create price record in database."""
        from src.models.price import Price, PriceSource, AuctionHouse

        is_retail = isinstance(item, RetailPriceItem)

        # Get price values - different fields for retail vs auction
        if is_retail:
            price_value = item.get("price")
            total_price = price_value
            currency = item.get("currency", "USD")
            source = PriceSource.RETAIL
            source_name = item.get("source_name", "Unknown Retailer")
            auction_house = None
        else:
            hammer_price = item.get("hammer_price") or item.get("total_price")
            total_price = item.get("total_price") or hammer_price
            price_value = hammer_price
            currency = item.get("currency", "GBP")
            source = PriceSource.AUCTION
            # Determine auction house enum
            auction_house_str = item.get("auction_house", "OTHER")
            try:
                auction_house = AuctionHouse(auction_house_str)
                source_name = auction_house.value.replace("_", " ").title()
            except ValueError:
                auction_house = AuctionHouse.OTHER
                source_name = "Other Auction"

        if not price_value:
            raise ValueError("No price available")

        # Convert to USD
        price_usd = convert_to_usd(total_price, currency)

        # Parse transaction date
        transaction_date = None
        date_field = item.get("auction_date") or item.get("scraped_at")
        if date_field:
            if isinstance(date_field, str):
                try:
                    transaction_date = datetime.fromisoformat(date_field.split("T")[0])
                except ValueError:
                    pass
            elif isinstance(date_field, datetime):
                transaction_date = date_field

        if not transaction_date:
            transaction_date = datetime.utcnow()

        price = Price(
            bottle_id=bottle_id,
            price=Decimal(str(total_price)),
            currency=currency,
            price_usd=price_usd,
            source=source,
            source_name=source_name,
            auction_house=auction_house,
            source_url=item.get("source_url", "")[:500],
            source_id=str(item.get("source_id", ""))[:100],
            transaction_date=transaction_date,
            is_sold=item.get("sold", True) if not is_retail else item.get("in_stock", True),
            includes_fees=not is_retail,  # Auction prices include buyer's premium
            confidence_weight=item.get("normalization_confidence", 1.0),
            is_verified=not is_retail,  # Auction data is verified, retail is current listing
            is_outlier=False,
            notes=f"Scraped from {source_name}. Original: {item.get('raw_title', '')[:200]}",
        )

        session.add(price)
        session.flush()

        return price.id

    def _create_audit_log(
        self,
        session,
        item,
        price_id: int,
        bottle_id: int,
    ):
        """Create audit log entry for the import."""
        from src.models.audit import AuditLog, AuditAction

        is_retail = isinstance(item, RetailPriceItem)
        source = item.get("source_name") if is_retail else item.get("auction_house")

        log = AuditLog(
            user_id=None,  # System action
            action=AuditAction.SYSTEM_PRICE_IMPORT,
            target_type="price",
            target_id=price_id,
            description=f"Imported price from {source}",
            details=json.dumps({
                "source_url": item.get("source_url"),
                "source_id": str(item.get("source_id", "")),
                "source": source,
                "source_type": "retail" if is_retail else "auction",
                "bottle_id": bottle_id,
                "price_usd": float(item.get("price_usd") or item.get("price") or 0),
                "raw_title": item.get("raw_title", "")[:200],
            }),
        )

        session.add(log)
