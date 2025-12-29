"""
Text extraction and cleaning utilities for WTracker scrapers.

Provides helpers for extracting structured data from auction listings.
"""

import re
import logging
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


# Compiled regex patterns for common extractions
PATTERNS = {
    # Age statement: "12 Year Old", "12yo", "12 years"
    "age": re.compile(
        r"(\d{1,2})\s*(?:year|yr|yo)s?\s*(?:old)?",
        re.IGNORECASE
    ),

    # Size: "700ml", "70cl", "75cl", "1L", "1 Litre"
    "size_ml": re.compile(
        r"(\d+)\s*(ml|cl|l|litre|liter)\b",
        re.IGNORECASE
    ),

    # ABV: "46%", "46.5% ABV", "Cask Strength 57.1%"
    "abv": re.compile(
        r"(\d+(?:\.\d+)?)\s*%\s*(?:abv|vol|alc)?",
        re.IGNORECASE
    ),

    # Vintage year: "1990 Vintage", "Distilled 1990"
    "vintage": re.compile(
        r"(?:vintage|distilled)\s*(\d{4})",
        re.IGNORECASE
    ),

    # Bottled year: "Bottled 2020"
    "bottled": re.compile(
        r"bottled\s*(\d{4})",
        re.IGNORECASE
    ),

    # Cask number: "Cask #123", "Cask No. 456"
    "cask": re.compile(
        r"cask\s*(?:#|no\.?|number)?\s*(\d+)",
        re.IGNORECASE
    ),

    # Lot number: "Lot 123", "Lot #456"
    "lot": re.compile(
        r"lot\s*(?:#|no\.?)?\s*(\d+)",
        re.IGNORECASE
    ),

    # Price: "£100", "$150.00", "GBP 100"
    "price": re.compile(
        r"(?:£|\$|€|GBP|USD|EUR)\s*([\d,]+(?:\.\d{2})?)",
        re.IGNORECASE
    ),
}

# Distillery name patterns (common distilleries)
DISTILLERY_PATTERNS = [
    # Scotch - Speyside
    (r"\b(macallan|glenfiddich|glenlivet|balvenie|aberlour|glenfarclas)\b", "Speyside"),
    (r"\b(glen\s*moray|benriach|benromach|craigellachie|mortlach|strathisla)\b", "Speyside"),

    # Scotch - Islay
    (r"\b(lagavulin|laphroaig|ardbeg|bowmore|bruichladdich|bunnahabhain)\b", "Islay"),
    (r"\b(caol\s*ila|kilchoman|port\s*ellen|port\s*charlotte)\b", "Islay"),

    # Scotch - Highland
    (r"\b(highland\s*park|glenmorangie|dalmore|oban|talisker|clynelish)\b", "Highland"),
    (r"\b(ben\s*nevis|dalwhinnie|glengoyne|tomatin|old\s*pulteney)\b", "Highland"),

    # Scotch - Lowland
    (r"\b(auchentoshan|glenkinchie|bladnoch|rosebank)\b", "Lowland"),

    # Scotch - Campbeltown
    (r"\b(springbank|glengyle|glen\s*scotia|kilkerran)\b", "Campbeltown"),

    # Bourbon
    (r"\b(buffalo\s*trace|eagle\s*rare|blantons?|stagg|e\.?h\.?\s*taylor)\b", "Bourbon"),
    (r"\b(wild\s*turkey|makers?\s*mark|woodford|knob\s*creek|bookers?)\b", "Bourbon"),
    (r"\b(four\s*roses|jim\s*beam|evan\s*williams|elijah\s*craig|heaven\s*hill)\b", "Bourbon"),
    (r"\b(pappy|van\s*winkle|old\s*fitzgerald|weller|old\s*forester)\b", "Bourbon"),

    # Japanese
    (r"\b(yamazaki|hakushu|hibiki|nikka|yoichi|miyagikyo|chichibu)\b", "Japanese"),
    (r"\b(karuizawa|hanyu|ichiros?\s*malt)\b", "Japanese"),

    # Irish
    (r"\b(jameson|redbreast|green\s*spot|yellow\s*spot|powers|bushmills)\b", "Irish"),
    (r"\b(midleton|teeling|tullamore)\b", "Irish"),
]


def extract_age(text: str) -> Optional[int]:
    """Extract age statement from text."""
    match = PATTERNS["age"].search(text)
    if match:
        age = int(match.group(1))
        # Sanity check: whisky ages are typically 3-70 years
        if 3 <= age <= 70:
            return age
    return None


def extract_size_ml(text: str) -> Optional[int]:
    """Extract bottle size in ml."""
    match = PATTERNS["size_ml"].search(text)
    if match:
        value = int(match.group(1))
        unit = match.group(2).lower()

        if unit == "cl":
            value *= 10
        elif unit in ("l", "litre", "liter"):
            value *= 1000

        # Sanity check: common sizes are 50ml to 4500ml
        if 50 <= value <= 4500:
            return value

    # Default size for standard bottles
    return None


def extract_abv(text: str) -> Optional[float]:
    """Extract ABV percentage from text."""
    match = PATTERNS["abv"].search(text)
    if match:
        abv = float(match.group(1))
        # Sanity check: ABV is typically 40-70%
        if 35 <= abv <= 75:
            return abv
    return None


def extract_vintage(text: str) -> Optional[int]:
    """Extract vintage year from text."""
    match = PATTERNS["vintage"].search(text)
    if match:
        year = int(match.group(1))
        # Sanity check: vintage between 1900 and current year
        if 1900 <= year <= datetime.now().year:
            return year
    return None


def extract_bottled_year(text: str) -> Optional[int]:
    """Extract bottled year from text."""
    match = PATTERNS["bottled"].search(text)
    if match:
        year = int(match.group(1))
        if 1950 <= year <= datetime.now().year + 1:
            return year
    return None


def extract_cask_number(text: str) -> Optional[str]:
    """Extract cask number from text."""
    match = PATTERNS["cask"].search(text)
    if match:
        return match.group(1)
    return None


def extract_lot_number(text: str) -> Optional[str]:
    """Extract lot number from text."""
    match = PATTERNS["lot"].search(text)
    if match:
        return match.group(1)
    return None


def extract_distillery(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract distillery name and region from text.

    Returns:
        Tuple of (distillery_name, region) or (None, None)
    """
    text_lower = text.lower()

    for pattern, region in DISTILLERY_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            # Title case the matched distillery name
            distillery = match.group(1).title()
            # Clean up spacing
            distillery = re.sub(r"\s+", " ", distillery)
            return distillery, region

    return None, None


def clean_title(title: str) -> str:
    """
    Clean auction lot title for normalization.

    Removes:
    - Lot numbers
    - Prices
    - Extra whitespace
    - Special characters
    """
    # Remove lot numbers
    cleaned = PATTERNS["lot"].sub("", title)

    # Remove prices
    cleaned = PATTERNS["price"].sub("", cleaned)

    # Remove common auction suffixes
    cleaned = re.sub(r"\s*-\s*(?:sold|unsold|withdrawn).*$", "", cleaned, flags=re.IGNORECASE)

    # Normalize quotes and apostrophes
    cleaned = cleaned.replace("'", "'").replace(""", '"').replace(""", '"')

    # Remove excessive punctuation
    cleaned = re.sub(r"[^\w\s\-\'\.%]", " ", cleaned)

    # Normalize whitespace
    cleaned = " ".join(cleaned.split())

    return cleaned.strip()


def parse_price(price_text: str) -> Optional[float]:
    """Parse price string to float."""
    if not price_text:
        return None

    # Remove currency symbols and whitespace
    cleaned = re.sub(r"[£$€\s,]", "", price_text)

    # Handle "GBP 100" format
    cleaned = re.sub(r"^(GBP|USD|EUR|CHF)\s*", "", cleaned, flags=re.IGNORECASE)

    try:
        return float(cleaned)
    except ValueError:
        return None
