"""
Import whisky cask auction data from Kaggle dataset.

Dataset: joaopaivaa/whisky-casks-auction-database
Contains 562 cask auction records with inflation-adjusted hammer prices.

Usage:
    python scripts/import_kaggle_casks.py
"""

import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.session import get_async_session_maker
from src.models.bottle import Bottle, SpiritCategory
from src.models.price import AuctionHouse, Price, PriceSource


# Map regions to spirit categories
REGION_CATEGORY_MAP = {
    "Islay": SpiritCategory.SCOTCH_SINGLE_MALT,
    "Speyside": SpiritCategory.SCOTCH_SINGLE_MALT,
    "Highland": SpiritCategory.SCOTCH_SINGLE_MALT,
    "Highlands": SpiritCategory.SCOTCH_SINGLE_MALT,
    "Lowlands": SpiritCategory.SCOTCH_SINGLE_MALT,
    "Lowland": SpiritCategory.SCOTCH_SINGLE_MALT,
    "Islands": SpiritCategory.SCOTCH_SINGLE_MALT,
    "Campbeltown": SpiritCategory.SCOTCH_SINGLE_MALT,
    "England": SpiritCategory.OTHER,
    "Ireland": SpiritCategory.IRISH,
    "USA": SpiritCategory.BOURBON,
}

SOURCE_NAME = "Kaggle Cask Auctions"


def normalize_name(name: str) -> str:
    """Create a normalized name for matching."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def build_bottle_name(row: pd.Series) -> str:
    """Build a descriptive bottle name from cask data."""
    parts = [row["distillery"]]

    age = row.get("age")
    if pd.notna(age) and age > 0:
        parts.append(f"{int(age)} Year Old")

    cask_type = row.get("cask_type")
    if pd.notna(cask_type):
        parts.append(f"({cask_type})")

    parts.append("Cask")

    return " ".join(parts)


def get_category(row: pd.Series) -> SpiritCategory:
    """Determine spirit category from region/country."""
    region = row.get("region", "")
    country = row.get("country", "")

    if pd.notna(region) and region in REGION_CATEGORY_MAP:
        return REGION_CATEGORY_MAP[region]

    if pd.notna(country):
        if country == "Scotland":
            return SpiritCategory.SCOTCH_SINGLE_MALT
        elif country == "Ireland":
            return SpiritCategory.IRISH
        elif country in ("USA", "America"):
            return SpiritCategory.BOURBON
        elif country == "Japan":
            return SpiritCategory.JAPANESE

    return SpiritCategory.OTHER


async def import_cask_data(csv_path: str, dry_run: bool = False):
    """Import cask auction data into the database."""
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} cask auction records")

    # Filter out rows without prices
    df = df.dropna(subset=["inf_adj_hammer_price"])
    df = df[df["inf_adj_hammer_price"] > 0]
    print(f"Valid records with prices: {len(df)}")

    session_maker = get_async_session_maker()
    async with session_maker() as session:
        new_bottles = 0
        new_prices = 0
        skipped = 0

        for _, row in df.iterrows():
            bottle_name = build_bottle_name(row)
            norm_name = normalize_name(bottle_name)

            # Check if bottle already exists
            result = await session.execute(
                select(Bottle).where(Bottle.normalized_name == norm_name)
            )
            bottle = result.scalar_one_or_none()

            if not bottle:
                # Create new bottle
                category = get_category(row)
                age = int(row["age"]) if pd.notna(row.get("age")) and row["age"] > 0 else None
                abv = row.get("strength")
                proof = float(abv) * 2 if pd.notna(abv) else None

                bottle = Bottle(
                    name=bottle_name,
                    normalized_name=norm_name,
                    distillery=row["distillery"] if pd.notna(row.get("distillery")) else None,
                    category=category,
                    age_statement=age,
                    proof=proof,
                    description=f"Cask auction: {row.get('cask_type', 'N/A')} cask, "
                                f"{row.get('cask_filling', 'N/A')} fill, "
                                f"previously held {row.get('previous_spirit', 'N/A')}. "
                                f"Region: {row.get('region', 'N/A')}, "
                                f"Status: {row.get('distillery_status', 'N/A')}.",
                )
                session.add(bottle)
                await session.flush()
                new_bottles += 1

            # Check for duplicate price
            auction_date = None
            if pd.notna(row.get("auction_date")):
                try:
                    auction_date = datetime.strptime(row["auction_date"], "%Y-%m-%d")
                except (ValueError, TypeError):
                    auction_date = datetime.utcnow()
            else:
                auction_date = datetime.utcnow()

            existing_price = await session.execute(
                select(Price).where(
                    Price.bottle_id == bottle.id,
                    Price.source_name == SOURCE_NAME,
                    Price.transaction_date == auction_date,
                    Price.price_usd == round(float(row["inf_adj_hammer_price"]), 2),
                )
            )
            if existing_price.scalar_one_or_none():
                skipped += 1
                continue

            # Create price record
            price = Price(
                bottle_id=bottle.id,
                price=round(float(row["inf_adj_hammer_price"]), 2),
                currency="GBP",
                price_usd=round(float(row["inf_adj_hammer_price"]), 2),  # Already adjusted
                source=PriceSource.IMPORT,
                source_name=SOURCE_NAME,
                auction_house=AuctionHouse.OTHER,
                transaction_date=auction_date,
                is_sold=True,
                includes_fees=True,
                confidence_weight=0.8,
                is_verified=True,
                notes=f"Cask auction import. "
                      f"Bulk litres: {row.get('bulk_litres', 'N/A')}, "
                      f"RLA: {row.get('rla', 'N/A')}, "
                      f"Bottles at cask strength: {row.get('bottles_at_cask_strength', 'N/A')}",
            )
            session.add(price)
            new_prices += 1

        if dry_run:
            print(f"\n[DRY RUN] Would create:")
            print(f"  {new_bottles} new bottles")
            print(f"  {new_prices} new prices")
            print(f"  {skipped} skipped (duplicates)")
            await session.rollback()
        else:
            await session.commit()
            print(f"\nImport complete:")
            print(f"  {new_bottles} new bottles created")
            print(f"  {new_prices} new prices added")
            print(f"  {skipped} skipped (duplicates)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import Kaggle cask auction data")
    parser.add_argument(
        "--csv",
        default="/home/southerns/.cache/kagglehub/datasets/joaopaivaa/whisky-casks-auction-database/versions/4/casks_database.csv",
        help="Path to casks_database.csv",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    args = parser.parse_args()

    asyncio.run(import_cask_data(args.csv, dry_run=args.dry_run))
