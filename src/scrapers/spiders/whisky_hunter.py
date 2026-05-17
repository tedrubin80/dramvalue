"""
Spider for Whisky Hunter API (whiskyhunter.net/api/).

Uses the official Whisky Hunter API to fetch auction data.
All values are in GBP.

API Endpoints:
- /api/auctions_info - List all online auctions
- /api/auctions_data/ - Aggregated data across all auctions
- /api/auction_data/{slug}/ - Data for specific auction (e.g., catawiki)
- /api/distilleries_info/ - Details about all distilleries
- /api/distillery_data/{slug}/ - Data for specific distillery (e.g., ardbeg)
"""

import logging
from datetime import datetime
from typing import Generator, Any

import scrapy
from scrapy.http import Response, JsonRequest

from src.scrapers.spiders.base import BaseAuctionSpider
from src.scrapers.items import AuctionLotItem

logger = logging.getLogger(__name__)


class WhiskyHunterSpider(BaseAuctionSpider):
    """
    Spider for fetching data from Whisky Hunter API.

    Aggregates auction results from multiple online whisky auctions including:
    - Catawiki
    - Whisky Auctioneer
    - Scotch Whisky Auctions
    - And others

    All prices are in GBP.
    """

    name = "whisky_hunter"
    auction_house = "WHISKY_HUNTER"
    allowed_domains = ["whiskyhunter.net"]

    # API base URL
    API_BASE = "https://whiskyhunter.net/api"

    custom_settings = {
        "DOWNLOAD_DELAY": 2.0,
        "CONCURRENT_REQUESTS": 1,
        "ROBOTSTXT_OBEY": False,  # Using API
    }

    def start_requests(self):
        """Start by fetching auctions info and distilleries."""
        # Get list of all auctions
        yield JsonRequest(
            url=f"{self.API_BASE}/auctions_info",
            callback=self.parse_auctions_info,
            errback=self.handle_error,
        )

        # Get list of all distilleries
        yield JsonRequest(
            url=f"{self.API_BASE}/distilleries_info/",
            callback=self.parse_distilleries_info,
            errback=self.handle_error,
        )

    def parse_auctions_info(self, response: Response) -> Generator[Any, None, None]:
        """Parse list of auctions and fetch data for each."""
        logger.info(f"Parsing auctions info: {response.url}")

        try:
            auctions = response.json()
        except Exception as e:
            logger.error(f"Failed to parse auctions info JSON: {e}")
            return

        if not isinstance(auctions, list):
            logger.warning(f"Expected list, got {type(auctions)}")
            return

        logger.info(f"Found {len(auctions)} auction sources")

        for auction in auctions:
            slug = auction.get("slug")
            if slug:
                yield JsonRequest(
                    url=f"{self.API_BASE}/auction_data/{slug}/",
                    callback=self.parse_auction_data,
                    meta={"auction_info": auction},
                    errback=self.handle_error,
                )

    def parse_distilleries_info(self, response: Response) -> Generator[Any, None, None]:
        """Parse list of distilleries and fetch data for each."""
        logger.info(f"Parsing distilleries info: {response.url}")

        try:
            distilleries = response.json()
        except Exception as e:
            logger.error(f"Failed to parse distilleries info JSON: {e}")
            return

        if not isinstance(distilleries, list):
            logger.warning(f"Expected list, got {type(distilleries)}")
            return

        logger.info(f"Found {len(distilleries)} distilleries")

        for distillery in distilleries:
            slug = distillery.get("slug")
            if slug:
                yield JsonRequest(
                    url=f"{self.API_BASE}/distillery_data/{slug}/",
                    callback=self.parse_distillery_data,
                    meta={"distillery_info": distillery},
                    errback=self.handle_error,
                )

    def parse_auction_data(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """Parse auction data containing aggregated results."""
        auction_info = response.meta.get("auction_info", {})
        auction_name = auction_info.get("name", "Unknown Auction")

        logger.info(f"Parsing auction data for: {auction_name}")

        try:
            data = response.json()
        except Exception as e:
            logger.error(f"Failed to parse auction data JSON: {e}")
            return

        if not isinstance(data, list):
            # Single object response
            data = [data] if data else []

        for entry in data:
            item = self._create_item_from_auction_entry(entry, auction_info)
            if item:
                self.items_scraped += 1
                yield item

    def parse_distillery_data(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """Parse distillery data containing bottle auction history."""
        distillery_info = response.meta.get("distillery_info", {})
        distillery_name = distillery_info.get("name", "Unknown Distillery")

        logger.info(f"Parsing distillery data for: {distillery_name}")

        try:
            data = response.json()
        except Exception as e:
            logger.error(f"Failed to parse distillery data JSON: {e}")
            return

        if not isinstance(data, list):
            data = [data] if data else []

        for entry in data:
            item = self._create_item_from_distillery_entry(entry, distillery_info)
            if item:
                self.items_scraped += 1
                yield item

    def parse(self, response: Response) -> Generator[Any, None, None]:
        """Default parse - not used for API spider."""
        pass

    def parse_lot(self, response: Response) -> Generator[AuctionLotItem, None, None]:
        """Not used for API spider."""
        pass

    def _create_item_from_auction_entry(
        self,
        entry: dict,
        auction_info: dict,
    ) -> AuctionLotItem | None:
        """Create an AuctionLotItem from auction data entry."""
        if not entry:
            return None

        # Extract date from entry
        dt_str = entry.get("dt")
        auction_date = None
        if dt_str:
            try:
                # Handle YYYY-MM-DD or YYYY-MM format
                if len(dt_str) == 7:  # YYYY-MM
                    auction_date = f"{dt_str}-01"
                else:
                    auction_date = dt_str[:10]
            except Exception:
                pass

        # Generate source ID
        auction_slug = auction_info.get("slug", "unknown")
        source_id = f"wh-{auction_slug}-{dt_str or 'na'}"

        # Get trading data (API v2 field names)
        lots_traded = entry.get("auction_lots_count", 0)
        trading_volume = entry.get("auction_trading_volume", 0)
        winning_bid_avg = entry.get("winning_bid_mean", 0)

        if not lots_traded or not trading_volume:
            return None

        item = AuctionLotItem()

        # Source identification
        item["source_id"] = source_id
        item["source_url"] = f"https://whiskyhunter.net/auctions/{auction_slug}/"
        item["auction_house"] = self.auction_house
        item["spider_name"] = self.name
        item["scraped_at"] = datetime.utcnow().isoformat()

        # Auction info
        item["auction_name"] = auction_info.get("name", auction_slug)
        item["raw_title"] = f"{auction_info.get('name', auction_slug)} - {dt_str}"
        item["raw_description"] = f"Aggregated data: {lots_traded} lots traded, £{trading_volume:,.0f} volume"

        # Price data (average winning bid)
        item["hammer_price"] = float(winning_bid_avg) if winning_bid_avg else None
        item["total_price"] = float(winning_bid_avg) if winning_bid_avg else None
        item["currency"] = "GBP"
        item["estimate_low"] = None
        item["estimate_high"] = None

        # Date
        item["auction_date"] = auction_date
        item["sold"] = True

        # Metadata
        item["bottle_count"] = lots_traded
        item["bottle_name"] = f"{auction_info.get('name', 'Whisky Hunter')} Aggregate"

        # Processing flags
        item["normalization_confidence"] = 0.0
        item["matched_bottle_id"] = None
        item["requires_review"] = True  # Aggregated data
        item["validation_errors"] = []
        item["is_duplicate"] = False

        return item

    def _create_item_from_distillery_entry(
        self,
        entry: dict,
        distillery_info: dict,
    ) -> AuctionLotItem | None:
        """Create an AuctionLotItem from distillery data entry."""
        if not entry:
            return None

        # Extract date
        dt_str = entry.get("dt")
        auction_date = None
        if dt_str:
            try:
                if len(dt_str) == 7:
                    auction_date = f"{dt_str}-01"
                else:
                    auction_date = dt_str[:10]
            except Exception:
                pass

        # Generate source ID
        distillery_slug = distillery_info.get("slug", "unknown")
        source_id = f"wh-dist-{distillery_slug}-{dt_str or 'na'}"

        # Get trading data (distillery endpoint uses lots_count, winning_bid_mean)
        lots_traded = entry.get("lots_count", 0)
        trading_volume = entry.get("trading_volume", 0)
        winning_bid_avg = entry.get("winning_bid_mean", 0)

        if not lots_traded or not winning_bid_avg:
            return None

        item = AuctionLotItem()

        # Source identification
        item["source_id"] = source_id
        item["source_url"] = f"https://whiskyhunter.net/distilleries/{distillery_slug}/"
        item["auction_house"] = self.auction_house
        item["spider_name"] = self.name
        item["scraped_at"] = datetime.utcnow().isoformat()

        # Distillery info
        item["distillery"] = distillery_info.get("name", distillery_slug)
        item["auction_name"] = "Whisky Hunter"
        item["raw_title"] = f"{distillery_info.get('name', distillery_slug)} - {dt_str}"
        item["raw_description"] = f"Aggregated distillery data: {lots_traded} lots, £{trading_volume:,.0f} volume"

        # Name for matching
        item["bottle_name"] = f"{distillery_info.get('name', distillery_slug)} (Aggregate)"

        # Price data
        item["hammer_price"] = float(winning_bid_avg) if winning_bid_avg else None
        item["total_price"] = float(winning_bid_avg) if winning_bid_avg else None
        item["currency"] = "GBP"

        # Date
        item["auction_date"] = auction_date
        item["sold"] = True

        # Metadata
        item["bottle_count"] = lots_traded

        # Processing flags
        item["normalization_confidence"] = 0.0
        item["matched_bottle_id"] = None
        item["requires_review"] = True
        item["validation_errors"] = []
        item["is_duplicate"] = False

        return item
