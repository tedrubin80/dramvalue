#!/usr/bin/env python3
"""
Reimport whisky data from CSV exports back into the database.

This script loads the exported CSV files (bottles, prices, market stats)
and inserts them into a fresh or existing database, skipping duplicates.

Usage:
    python scripts/reimport_csv_data.py
    python scripts/reimport_csv_data.py --dry-run
    python scripts/reimport_csv_data.py --bottles-only
    python scripts/reimport_csv_data.py --csv-dir /path/to/csvs
"""

import asyncio
import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.session import get_async_session_maker, Base, get_async_engine
from src.models.bottle import Bottle, SpiritCategory
from src.models.price import Price, PriceSource, AuctionHouse
from src.models.market_stat import MarketStat


# Map CSV category strings to enums
CATEGORY_MAP = {
    "SCOTCH_SINGLE_MALT": SpiritCategory.SCOTCH_SINGLE_MALT,
    "SCOTCH_BLENDED": SpiritCategory.SCOTCH_BLENDED,
    "BOURBON": SpiritCategory.BOURBON,
    "RYE": SpiritCategory.RYE,
    "IRISH": SpiritCategory.IRISH,
    "JAPANESE": SpiritCategory.JAPANESE,
    "AMERICAN_SINGLE_MALT": SpiritCategory.AMERICAN_SINGLE_MALT,
    "OTHER": SpiritCategory.OTHER,
}

SOURCE_MAP = {
    "AUCTION": PriceSource.AUCTION,
    "RETAIL": PriceSource.RETAIL,
    "CROWDSOURCED": PriceSource.CROWDSOURCED,
    "IMPORT": PriceSource.IMPORT,
}

AUCTION_HOUSE_MAP = {v.value: v for v in AuctionHouse}


def parse_datetime(val):
    """Parse datetime from CSV, handling various formats."""
    if pd.isna(val):
        return None
    try:
        return pd.to_datetime(val).to_pydatetime()
    except Exception:
        return None


async def create_tables():
    """Create all tables if they don't exist."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables ensured.")


async def import_bottles(csv_path: str, session, dry_run: bool = False) -> int:
    """Import bottles from CSV."""
    df = pd.read_csv(csv_path)
    print(f"\nLoading bottles from {csv_path}: {len(df)} rows")

    # Deduplicate by normalized_name within the CSV itself
    if "normalized_name" in df.columns:
        before = len(df)
        df = df.drop_duplicates(subset=["normalized_name"], keep="first")
        if len(df) < before:
            print(f"  Deduplicated CSV: {before} -> {len(df)} rows")

    created = 0
    skipped = 0
    seen_norms = set()

    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if not name:
            skipped += 1
            continue

        norm_name = str(row.get("normalized_name", "")).strip()
        if not norm_name:
            norm_name = name.lower().replace(" ", "_")

        # Skip in-batch duplicates
        if norm_name in seen_norms:
            skipped += 1
            continue
        seen_norms.add(norm_name)

        # Check for existing in DB
        result = await session.execute(
            select(Bottle).where(Bottle.normalized_name == norm_name)
        )
        if result.scalar_one_or_none():
            skipped += 1
            continue

        category = CATEGORY_MAP.get(
            str(row.get("category", "OTHER")), SpiritCategory.OTHER
        )

        try:
            bottle = Bottle(
                name=name,
                normalized_name=norm_name,
                distillery=str(row["distillery"]) if pd.notna(row.get("distillery")) else None,
                brand=str(row["brand"]) if pd.notna(row.get("brand")) else None,
                category=category,
                age_statement=int(row["age_statement"]) if pd.notna(row.get("age_statement")) else None,
                proof=float(row["proof"]) if pd.notna(row.get("proof")) else None,
                size_ml=int(row["size_ml"]) if pd.notna(row.get("size_ml")) else None,
                release_year=int(row["release_year"]) if pd.notna(row.get("release_year")) else None,
                is_limited_release=bool(row.get("is_limited_release", False)) if pd.notna(row.get("is_limited_release")) else False,
                is_allocated=bool(row.get("is_allocated", False)) if pd.notna(row.get("is_allocated")) else False,
                msrp=float(row["msrp"]) if pd.notna(row.get("msrp")) else None,
                avg_price=float(row["avg_price"]) if pd.notna(row.get("avg_price")) else None,
                min_price=float(row["min_price"]) if pd.notna(row.get("min_price")) else None,
                max_price=float(row["max_price"]) if pd.notna(row.get("max_price")) else None,
                last_price=float(row["last_price"]) if pd.notna(row.get("last_price")) else None,
                last_price_date=parse_datetime(row.get("last_price_date")),
                price_count=int(row["price_count"]) if pd.notna(row.get("price_count")) else 0,
                price_trend=float(row["price_trend"]) if pd.notna(row.get("price_trend")) else None,
            )
            session.add(bottle)
            await session.flush()
            created += 1

            if created % 500 == 0:
                print(f"  ... {created} bottles created so far")
        except Exception as e:
            await session.rollback()
            skipped += 1
            continue

    print(f"  Bottles: {created} created, {skipped} skipped")
    return created


async def import_prices(csv_path: str, session, dry_run: bool = False) -> int:
    """Import prices from CSV."""
    df = pd.read_csv(csv_path)
    print(f"\nLoading prices from {csv_path}: {len(df)} rows")

    created = 0
    skipped = 0
    no_bottle = 0

    for _, row in df.iterrows():
        bottle_name = str(row.get("bottle_name", "")).strip()
        if not bottle_name:
            skipped += 1
            continue

        # Find bottle by name
        norm = bottle_name.lower().replace(" ", "_")
        # Try normalized lookup first
        result = await session.execute(
            select(Bottle).where(Bottle.normalized_name == norm)
        )
        bottle = result.scalar_one_or_none()

        if not bottle:
            # Try exact name match
            result = await session.execute(
                select(Bottle).where(Bottle.name == bottle_name).limit(1)
            )
            bottle = result.scalar_one_or_none()

        if not bottle:
            no_bottle += 1
            continue

        price_usd = float(row["price_usd"]) if pd.notna(row.get("price_usd")) else None
        if not price_usd or price_usd <= 0:
            skipped += 1
            continue

        source = SOURCE_MAP.get(str(row.get("source", "")), PriceSource.IMPORT)
        source_name = str(row["source_name"]) if pd.notna(row.get("source_name")) else None

        auction_house = None
        ah_val = str(row.get("auction_house", "")) if pd.notna(row.get("auction_house")) else None
        if ah_val and ah_val in AUCTION_HOUSE_MAP:
            auction_house = AUCTION_HOUSE_MAP[ah_val]

        transaction_date = parse_datetime(row.get("transaction_date"))
        if not transaction_date:
            transaction_date = datetime.utcnow()

        price_val = float(row["price"]) if pd.notna(row.get("price")) else price_usd
        currency = str(row["currency"]) if pd.notna(row.get("currency")) else "USD"
        is_sold = str(row.get("is_sold", "t")).lower() in ("t", "true", "1", "yes")

        price_record = Price(
            bottle_id=bottle.id,
            price=price_val,
            currency=currency,
            price_usd=price_usd,
            source=source,
            source_name=source_name,
            auction_house=auction_house,
            source_url=str(row["source_url"]) if pd.notna(row.get("source_url")) else None,
            transaction_date=transaction_date,
            is_sold=is_sold,
            is_verified=True,
            confidence_weight=0.9,
        )
        session.add(price_record)
        created += 1

        if created % 1000 == 0:
            await session.flush()
            print(f"  ... {created} prices created so far")

    if not dry_run:
        await session.flush()

    print(f"  Prices: {created} created, {skipped} skipped, {no_bottle} missing bottles")
    return created


async def import_market_stats(csv_path: str, session, dry_run: bool = False) -> int:
    """Import market statistics from CSV."""
    df = pd.read_csv(csv_path)
    print(f"\nLoading market stats from {csv_path}: {len(df)} rows")

    created = 0
    skipped = 0

    for _, row in df.iterrows():
        auction_name = str(row.get("auction_name", "")).strip()
        auction_slug = str(row.get("auction_slug", "")).strip()
        period_date = parse_datetime(row.get("period_date"))

        if not auction_name or not period_date:
            skipped += 1
            continue

        # Check for duplicate
        result = await session.execute(
            select(MarketStat).where(
                MarketStat.auction_slug == auction_slug,
                MarketStat.period_date == period_date,
            )
        )
        if result.scalar_one_or_none():
            skipped += 1
            continue

        stat = MarketStat(
            auction_name=auction_name,
            auction_slug=auction_slug,
            period_date=period_date,
            winning_bid_max=float(row["winning_bid_max"]) if pd.notna(row.get("winning_bid_max")) else None,
            winning_bid_min=float(row["winning_bid_min"]) if pd.notna(row.get("winning_bid_min")) else None,
            winning_bid_mean=float(row["winning_bid_mean"]) if pd.notna(row.get("winning_bid_mean")) else None,
            trading_volume=float(row["trading_volume"]) if pd.notna(row.get("trading_volume")) else None,
            lots_count=int(row["lots_count"]) if pd.notna(row.get("lots_count")) else None,
            all_auctions_lots_count=int(row["all_auctions_lots_count"]) if pd.notna(row.get("all_auctions_lots_count")) else None,
        )
        session.add(stat)
        created += 1

        if created % 500 == 0:
            await session.flush()
            print(f"  ... {created} market stats created so far")

    if not dry_run:
        await session.flush()

    print(f"  Market stats: {created} created, {skipped} skipped")
    return created


async def main():
    parser = argparse.ArgumentParser(description="Reimport CSV data into database")
    parser.add_argument("--csv-dir", default="/var/www/wtracker", help="Directory containing CSV files")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--bottles-only", action="store_true", help="Only import bottles")
    parser.add_argument("--prices-only", action="store_true", help="Only import prices")
    parser.add_argument("--market-only", action="store_true", help="Only import market stats")
    parser.add_argument("--create-tables", action="store_true", help="Create DB tables first")
    args = parser.parse_args()

    csv_dir = Path(args.csv_dir)
    import_all = not (args.bottles_only or args.prices_only or args.market_only)

    if args.create_tables:
        await create_tables()

    session_maker = get_async_session_maker()
    async with session_maker() as session:
        total = 0

        # Import bottles first (prices depend on them)
        if import_all or args.bottles_only:
            # Import dramvalue_bottles.csv first (more fields)
            bottles_csv = csv_dir / "dramvalue_bottles.csv"
            if bottles_csv.exists():
                total += await import_bottles(str(bottles_csv), session, args.dry_run)
            # Also import whisky_bottles.csv (has additional bottles)
            whisky_bottles_csv = csv_dir / "whisky_bottles.csv"
            if whisky_bottles_csv.exists():
                total += await import_bottles(str(whisky_bottles_csv), session, args.dry_run)

        # Import prices
        if import_all or args.prices_only:
            # Try dramvalue_prices.csv first, fall back to whisky_prices.csv
            prices_csv = csv_dir / "dramvalue_prices.csv"
            if not prices_csv.exists():
                prices_csv = csv_dir / "whisky_prices.csv"
            if prices_csv.exists():
                total += await import_prices(str(prices_csv), session, args.dry_run)

            # Also import the other price CSV if both exist
            if (csv_dir / "whisky_prices.csv").exists() and (csv_dir / "dramvalue_prices.csv").exists():
                total += await import_prices(str(csv_dir / "whisky_prices.csv"), session, args.dry_run)

        # Import market stats
        if import_all or args.market_only:
            market_csv = csv_dir / "whisky_market_stats.csv"
            if market_csv.exists():
                total += await import_market_stats(str(market_csv), session, args.dry_run)

        if args.dry_run:
            print(f"\n[DRY RUN] Would have created {total} total records")
            await session.rollback()
        else:
            await session.commit()
            print(f"\nImport complete: {total} total records created")


if __name__ == "__main__":
    asyncio.run(main())
