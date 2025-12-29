"""
Normalization pipeline for WTracker scrapers.

Second pipeline stage: normalizes bottle names and matches to database.
"""

import logging
import re
from typing import Optional, Tuple

from src.scrapers.items import AuctionLotItem
from src.scrapers.utils.text import clean_title, extract_distillery

logger = logging.getLogger(__name__)


class NormalizationPipeline:
    """
    Normalizes bottle names and prepares for database matching.

    This pipeline performs lightweight normalization during scraping.
    Full database matching happens in the DatabasePipeline using
    the BottleNormalizationService.

    Normalization steps:
    1. Clean title (remove lot numbers, prices, special chars)
    2. Extract distillery if not already set
    3. Determine spirit category
    4. Set initial confidence score
    """

    # Category detection patterns
    CATEGORY_PATTERNS = {
        "BOURBON": [
            r"\bbourbon\b",
            r"\bkentucky\s+straight\b",
            r"\bbuffalo\s+trace\b",
            r"\beagle\s+rare\b",
            r"\bblantons?\b",
            r"\bwild\s+turkey\b",
            r"\bmakers?\s+mark\b",
            r"\bwoodford\b",
            r"\bknob\s+creek\b",
            r"\bbookers?\b",
            r"\bfour\s+roses\b",
            r"\bjim\s+beam\b",
            r"\bevan\s+williams\b",
            r"\belijah\s+craig\b",
            r"\bpappy\b",
            r"\bvan\s+winkle\b",
            r"\bweller\b",
            r"\bstagg\b",
        ],
        "RYE": [
            r"\brye\s+whiskey?\b",
            r"\bstraight\s+rye\b",
            r"\bsazerac\s+rye\b",
            r"\bwhistlepig\b",
            r"\bhigh\s+west\b",
        ],
        "SCOTCH_SINGLE_MALT": [
            r"\bsingle\s+malt\b",
            r"\bspeyside\b",
            r"\bhighland\b",
            r"\bislay\b",
            r"\blowland\b",
            r"\bcampbeltown\b",
            r"\bmacallan\b",
            r"\bglenfiddich\b",
            r"\bglenlivet\b",
            r"\blagavulin\b",
            r"\blaphroaig\b",
            r"\bardbeg\b",
            r"\bbowmore\b",
            r"\btalisker\b",
            r"\bhighland\s+park\b",
        ],
        "SCOTCH_BLENDED": [
            r"\bblended\s+scotch\b",
            r"\bjohnnie\s+walker\b",
            r"\bchivas\s+regal\b",
            r"\bballantines?\b",
            r"\bdewar'?s\b",
        ],
        "IRISH": [
            r"\birish\s+whiskey?\b",
            r"\bjameson\b",
            r"\bredbreast\b",
            r"\bgreen\s+spot\b",
            r"\byellow\s+spot\b",
            r"\bpowers\b",
            r"\bbushmills\b",
            r"\bmidleton\b",
            r"\bteeling\b",
        ],
        "JAPANESE": [
            r"\bjapanese\s+whisky?\b",
            r"\byamazaki\b",
            r"\bhakushu\b",
            r"\bhibiki\b",
            r"\bnikka\b",
            r"\byoichi\b",
            r"\bmiyagikyo\b",
            r"\bchichibu\b",
            r"\bkaruizawa\b",
        ],
        "AMERICAN_SINGLE_MALT": [
            r"\bamerican\s+single\s+malt\b",
            r"\bwestland\b",
            r"\bbalcones\b",
            r"\bstranahan'?s\b",
        ],
    }

    def __init__(self):
        """Initialize the pipeline."""
        self._stats = {
            "processed": 0,
            "normalized": 0,
            "category_detected": 0,
        }

    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline from crawler."""
        return cls()

    def open_spider(self, spider):
        """Reset stats when spider opens."""
        self._stats = {"processed": 0, "normalized": 0, "category_detected": 0}
        logger.info(f"NormalizationPipeline initialized for {spider.name}")

    def close_spider(self, spider):
        """Log stats when spider closes."""
        logger.info(f"Normalization stats: {self._stats}")

    def process_item(self, item: AuctionLotItem, spider) -> AuctionLotItem:
        """
        Normalize item data.

        Args:
            item: The scraped item
            spider: The spider instance

        Returns:
            The normalized item
        """
        self._stats["processed"] += 1

        # Get raw title and description
        raw_title = item.get("raw_title", "")
        raw_description = item.get("raw_description", "")
        full_text = f"{raw_title} {raw_description}"

        # Clean the bottle name if not already done
        if not item.get("bottle_name"):
            item["bottle_name"] = clean_title(raw_title)
            self._stats["normalized"] += 1

        # Extract distillery if not set
        if not item.get("distillery"):
            distillery, _ = extract_distillery(full_text)
            if distillery:
                item["distillery"] = distillery

        # Detect category if not set
        if not item.get("category"):
            category = self._detect_category(full_text)
            if category:
                item["category"] = category
                self._stats["category_detected"] += 1

        # Set initial confidence (will be updated by database pipeline)
        # Higher confidence if we detected category and distillery
        confidence = 0.5
        if item.get("distillery"):
            confidence += 0.2
        if item.get("category"):
            confidence += 0.2
        if item.get("age_statement"):
            confidence += 0.1

        item["normalization_confidence"] = min(confidence, 1.0)

        logger.debug(
            f"Normalized: {item.get('source_id')} -> "
            f"'{item.get('bottle_name')}' "
            f"(category={item.get('category')}, confidence={confidence:.2f})"
        )

        return item

    def _detect_category(self, text: str) -> Optional[str]:
        """
        Detect spirit category from text.

        Returns category enum value or None.
        """
        text_lower = text.lower()

        for category, patterns in self.CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return category

        return None
