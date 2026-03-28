"""
Import whisky auction market data from Kaggle dataset.

Dataset: shivd24coder/wiskey-price-dataset
Contains monthly aggregate auction statistics from 27 auction houses (2005-2023).

Usage:
    python scripts/import_kaggle_market.py
    python scripts/import_kaggle_market.py --dry-run
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.session import get_async_session_maker
from src.models.market_stat import MarketStat


async def import_market_data(csv_path: str, dry_run: bool = False):
    """Import auction market aggregate data into the database."""
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} market stat records")
    print(f"  Auction houses: {df['auction_name'].nunique()}")
    print(f"  Date range: {df['dt'].min()} to {df['dt'].max()}")

    session_maker = get_async_session_maker()
    async with session_maker() as session:
        new_stats = 0
        skipped = 0

        for _, row in df.iterrows():
            period_date = datetime.strptime(row["dt"], "%Y-%m-%d")

            # Check for duplicate
            existing = await session.execute(
                select(MarketStat).where(
                    MarketStat.auction_slug == row["auction_slug"],
                    MarketStat.period_date == period_date,
                )
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            stat = MarketStat(
                auction_name=row["auction_name"],
                auction_slug=row["auction_slug"],
                period_date=period_date,
                winning_bid_max=float(row["winning_bid_max"]),
                winning_bid_min=float(row["winning_bid_min"]),
                winning_bid_mean=float(row["winning_bid_mean"]),
                trading_volume=float(row["auction_trading_volume"]),
                lots_count=int(row["auction_lots_count"]),
                all_auctions_lots_count=int(row["all_auctions_lots_count"]),
            )
            session.add(stat)
            new_stats += 1

        if dry_run:
            print(f"\n[DRY RUN] Would create {new_stats} market stat records ({skipped} skipped)")
            await session.rollback()
        else:
            await session.commit()
            print(f"\nImport complete: {new_stats} records added ({skipped} skipped)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import Kaggle market stats")
    parser.add_argument(
        "--csv",
        default="/home/southerns/.cache/kagglehub/datasets/shivd24coder/wiskey-price-dataset/versions/1/auction_data.csv",
        help="Path to auction_data.csv",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    asyncio.run(import_market_data(args.csv, dry_run=args.dry_run))
