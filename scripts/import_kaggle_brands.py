"""
Import world whisky distilleries and brands from Kaggle dataset.

Dataset: koki25ando/world-whisky-distilleries-brands-dataset
Contains 1,157 distilleries and 4,880 brands from Whiskybase.

Usage:
    python scripts/import_kaggle_brands.py
    python scripts/import_kaggle_brands.py --dry-run
"""

import asyncio
import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.session import get_async_session_maker
from src.models.bottle import Bottle, SpiritCategory


# Country to category mapping
COUNTRY_CATEGORY_MAP = {
    "Scotland": SpiritCategory.SCOTCH_SINGLE_MALT,
    "Japan": SpiritCategory.JAPANESE,
    "Ireland": SpiritCategory.IRISH,
    "United States": SpiritCategory.BOURBON,
    "USA": SpiritCategory.BOURBON,
}


def normalize_name(name: str) -> str:
    """Create a normalized name for matching."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def get_category(country: str) -> SpiritCategory:
    """Determine spirit category from country."""
    if pd.notna(country) and country in COUNTRY_CATEGORY_MAP:
        return COUNTRY_CATEGORY_MAP[country]
    return SpiritCategory.OTHER


async def import_brands(base_path: str, dry_run: bool = False):
    """Import distillery and brand data."""
    distilleries_df = pd.read_csv(f"{base_path}/Distillery.csv")
    brands_df = pd.read_csv(f"{base_path}/Whisky_Brand.csv")
    print(f"Loaded {len(distilleries_df)} distilleries and {len(brands_df)} brands")

    session_maker = get_async_session_maker()
    async with session_maker() as session:
        new_bottles = 0
        updated = 0
        skipped = 0

        # Import brands as bottles (brands = product lines)
        for _, row in brands_df.iterrows():
            brand = row.get("Brand")
            if not isinstance(brand, str) or not brand.strip():
                skipped += 1
                continue

            brand = brand.strip()
            norm = normalize_name(brand)
            if not norm:
                skipped += 1
                continue

            # Check if already exists
            result = await session.execute(
                select(Bottle).where(Bottle.normalized_name == norm)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update category if it's currently OTHER
                country = row.get("Country", "")
                cat = get_category(country)
                if existing.category == SpiritCategory.OTHER and cat != SpiritCategory.OTHER:
                    existing.category = cat
                    updated += 1
                else:
                    skipped += 1
                continue

            country = row.get("Country", "")
            category = get_category(country)

            try:
                bottle = Bottle(
                    name=brand,
                    normalized_name=norm,
                    distillery=brand,
                    brand=brand,
                    category=category,
                )
                session.add(bottle)
                await session.flush()
                new_bottles += 1
            except Exception:
                await session.rollback()
                skipped += 1
                continue

        if dry_run:
            print(f"\n[DRY RUN] Would create {new_bottles} bottles, update {updated}, skip {skipped}")
            await session.rollback()
        else:
            await session.commit()
            print(f"\nImport complete: {new_bottles} bottles created, {updated} updated, {skipped} skipped")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import Kaggle brands data")
    parser.add_argument(
        "--path",
        default="/home/southerns/.cache/kagglehub/datasets/koki25ando/world-whisky-distilleries-brands-dataset/versions/1",
        help="Path to dataset directory",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    asyncio.run(import_brands(args.path, dry_run=args.dry_run))
