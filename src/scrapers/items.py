"""
Scrapy item definitions for auction data.

Items define the structure of scraped data as it flows through pipelines.
"""

import scrapy
from datetime import datetime
from typing import Optional


class AuctionLotItem(scrapy.Item):
    """
    Represents a single auction lot (bottle sale).

    This item flows through the pipeline:
    1. Spider extracts raw data
    2. ValidationPipeline validates required fields
    3. NormalizationPipeline matches/creates bottle
    4. DeduplicationPipeline checks for existing records
    5. DatabasePipeline persists to database
    """

    # === Source Identification ===
    source_id = scrapy.Field()           # Unique ID from source (lot number)
    source_url = scrapy.Field()          # Direct URL to lot page
    auction_house = scrapy.Field()       # Enum value: WHISKY_AUCTIONEER, SCOTCH_WHISKY_AUCTIONS
    auction_name = scrapy.Field()        # Name of specific auction (e.g., "December 2024 Auction")

    # === Raw Content (as scraped) ===
    raw_title = scrapy.Field()           # Original lot title from page
    raw_description = scrapy.Field()     # Full lot description

    # === Extracted Bottle Information ===
    bottle_name = scrapy.Field()         # Cleaned bottle name
    distillery = scrapy.Field()          # Extracted distillery name
    category = scrapy.Field()            # Spirit category (bourbon, scotch, etc.)
    age_statement = scrapy.Field()       # Age in years (None if NAS)
    size_ml = scrapy.Field()             # Bottle size in ml
    abv = scrapy.Field()                 # Alcohol by volume (percentage)
    proof = scrapy.Field()               # Proof (ABV * 2 for US)
    vintage = scrapy.Field()             # Vintage year if applicable
    bottled_year = scrapy.Field()        # Year bottled
    cask_number = scrapy.Field()         # Cask number if single cask
    bottle_count = scrapy.Field()        # Number of bottles in lot (usually 1)

    # === Price Information ===
    hammer_price = scrapy.Field()        # Winning bid (before premium)
    buyers_premium_pct = scrapy.Field()  # Buyer's premium percentage
    total_price = scrapy.Field()         # Hammer + premium (final price)
    currency = scrapy.Field()            # Original currency (GBP, USD, EUR)
    price_usd = scrapy.Field()           # Converted to USD
    estimate_low = scrapy.Field()        # Low estimate (if available)
    estimate_high = scrapy.Field()       # High estimate (if available)

    # === Transaction Details ===
    auction_date = scrapy.Field()        # Date auction closed (ISO format string)
    sold = scrapy.Field()                # Boolean: did it sell?
    num_bids = scrapy.Field()            # Number of bids received

    # === Media ===
    image_url = scrapy.Field()           # Primary bottle image
    image_urls = scrapy.Field()          # All images (list)

    # === Metadata ===
    scraped_at = scrapy.Field()          # When this was scraped (ISO format)
    spider_name = scrapy.Field()         # Name of spider that scraped this

    # === Processing State (set by pipelines) ===
    normalization_confidence = scrapy.Field()  # 0-1 confidence in bottle match
    matched_bottle_id = scrapy.Field()         # FK to bottles table if matched
    requires_review = scrapy.Field()           # Flag for manual review queue
    validation_errors = scrapy.Field()         # List of validation issues
    is_duplicate = scrapy.Field()              # Set by deduplication pipeline
    _dedup_key = scrapy.Field()                # Internal: deduplication key

    def __repr__(self) -> str:
        return f"<AuctionLotItem {self.get('source_id', 'unknown')}: {self.get('raw_title', '')[:50]}>"


class AuctionListingItem(scrapy.Item):
    """
    Represents an auction listing page (contains multiple lots).

    Used to track which auctions have been scraped.
    """

    auction_house = scrapy.Field()
    auction_id = scrapy.Field()          # Unique auction identifier
    auction_name = scrapy.Field()        # Display name
    auction_url = scrapy.Field()         # URL to auction page
    start_date = scrapy.Field()          # Auction start date
    end_date = scrapy.Field()            # Auction end date
    total_lots = scrapy.Field()          # Total number of lots
    scraped_at = scrapy.Field()


class RetailPriceItem(scrapy.Item):
    """
    Represents a retail price listing from an online shop.

    Used for tracking retail/secondary market prices.
    """

    # === Source Identification ===
    source_id = scrapy.Field()           # Unique product ID from source
    source_url = scrapy.Field()          # Direct URL to product page
    source_name = scrapy.Field()         # Retailer name (Fine Drams, Dekanta, etc.)
    source_type = scrapy.Field()         # "retail" or "secondary"

    # === Raw Content ===
    raw_title = scrapy.Field()           # Original product title
    raw_description = scrapy.Field()     # Product description

    # === Extracted Bottle Information ===
    bottle_name = scrapy.Field()         # Cleaned bottle name
    distillery = scrapy.Field()          # Extracted distillery name
    category = scrapy.Field()            # Spirit category
    age_statement = scrapy.Field()       # Age in years
    size_ml = scrapy.Field()             # Bottle size in ml
    abv = scrapy.Field()                 # Alcohol by volume
    vintage = scrapy.Field()             # Vintage year
    bottled_year = scrapy.Field()        # Year bottled
    cask_number = scrapy.Field()         # Cask number if single cask
    bottler = scrapy.Field()             # Independent bottler name
    country = scrapy.Field()             # Country of origin
    region = scrapy.Field()              # Region (Speyside, Islay, Kentucky, etc.)

    # === Price Information ===
    price = scrapy.Field()               # Current price
    original_price = scrapy.Field()      # Original price (if on sale)
    currency = scrapy.Field()            # Currency (EUR, GBP, USD)
    price_usd = scrapy.Field()           # Converted to USD

    # === Availability ===
    in_stock = scrapy.Field()            # Boolean: is it available?
    stock_quantity = scrapy.Field()      # Number in stock (if available)

    # === Media ===
    image_url = scrapy.Field()           # Primary product image

    # === Metadata ===
    scraped_at = scrapy.Field()          # When this was scraped
    spider_name = scrapy.Field()         # Spider that scraped this

    # === Processing State ===
    matched_bottle_id = scrapy.Field()   # FK to bottles table if matched
    normalization_confidence = scrapy.Field()
    requires_review = scrapy.Field()
    is_duplicate = scrapy.Field()
    validation_errors = scrapy.Field()   # List of validation issues
    _dedup_key = scrapy.Field()          # Internal: deduplication key

    def __repr__(self) -> str:
        return f"<RetailPriceItem {self.get('source_name', '')}: {self.get('raw_title', '')[:50]}>"
