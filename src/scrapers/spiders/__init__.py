"""
WTracker auction spiders.

Available spiders:
- whisky_auctioneer: Scrapes whiskyauctioneer.com
- scotch_whisky_auctions: Scrapes scotchwhiskyauctions.com
"""

from src.scrapers.spiders.base import BaseAuctionSpider
from src.scrapers.spiders.whisky_auctioneer import WhiskyAuctioneerSpider
from src.scrapers.spiders.scotch_whisky_auctions import ScotchWhiskyAuctionsSpider

# Spider registry for Celery tasks
SPIDERS = {
    "whisky_auctioneer": WhiskyAuctioneerSpider,
    "scotch_whisky_auctions": ScotchWhiskyAuctionsSpider,
}

__all__ = [
    "BaseAuctionSpider",
    "WhiskyAuctioneerSpider",
    "ScotchWhiskyAuctionsSpider",
    "SPIDERS",
]
