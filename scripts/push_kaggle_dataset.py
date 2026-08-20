#!/usr/bin/env python3
"""
Export DramValue data and publish a new Kaggle dataset version.

Usage:
    python scripts/push_kaggle_dataset.py
    python scripts/push_kaggle_dataset.py --export-only
    python scripts/push_kaggle_dataset.py --dataset tedrubin80/dramvalue-whisky-prices

Requires Kaggle authentication via one of:
    export KAGGLE_API_TOKEN=KGAT_...
    ~/.kaggle/access_token
    kaggle auth login
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_DATASET_ID = os.getenv("KAGGLE_DATASET_ID", "tedrubin80/dramvalue-whisky-prices")
OUTPUT_DIR = ROOT / "data" / "kaggle"


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        from src.scrapers.settings import DATABASE_URL

        url = DATABASE_URL
    return url.replace("postgresql+asyncpg", "postgresql+psycopg2").replace(
        "+asyncpg", "+psycopg2"
    )


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        raise FileNotFoundError(f"Missing export file: {path}")
    return sum(1 for _ in path.open(encoding="utf-8")) - 1


def get_counts(data_dir: Path) -> dict[str, int]:
    return {
        "bottles": count_csv_rows(data_dir / "dramvalue_bottles.csv"),
        "prices": count_csv_rows(data_dir / "dramvalue_prices.csv"),
        "market_stats": count_csv_rows(data_dir / "dramvalue_market_stats.csv"),
    }


def run_export(output_dir: Path) -> None:
    script = ROOT / "scripts" / "export_dataset.sh"
    subprocess.run(["bash", str(script), str(output_dir)], check=True)


def export_dataset(output_dir: Path) -> dict[str, int]:
    """Export bottles, prices, and market stats to CSV files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(get_database_url())
    counts: dict[str, int] = {}

    print("Exporting bottles...")
    bottles_query = """
        SELECT
            id, name, normalized_name, distillery, brand, category::text AS category,
            age_statement, proof, size_ml, release_year,
            is_limited_release, is_allocated, msrp,
            price_count, avg_price, min_price, max_price,
            last_price, last_price_date, price_trend,
            created_at, updated_at, stats_updated_at
        FROM bottles
        WHERE is_active = true
        ORDER BY id
    """
    bottles_df = pd.read_sql(text(bottles_query), engine)
    bottles_path = output_dir / "dramvalue_bottles.csv"
    bottles_df.to_csv(bottles_path, index=False)
    counts["bottles"] = len(bottles_df)
    print(f"  -> {counts['bottles']:,} rows -> {bottles_path.name}")

    print("Exporting prices...")
    prices_query = """
        SELECT
            p.id AS price_id,
            p.bottle_id,
            b.name AS bottle_name,
            b.distillery,
            b.brand,
            b.category::text AS category,
            p.price,
            p.currency,
            p.price_usd,
            p.source::text AS source,
            p.source_name,
            p.auction_house::text AS auction_house,
            p.source_url,
            p.source_id,
            p.transaction_date,
            p.is_sold,
            p.is_excluded,
            p.created_at
        FROM prices p
        JOIN bottles b ON b.id = p.bottle_id
        WHERE p.is_excluded = false
        ORDER BY p.transaction_date DESC, p.id DESC
    """
    prices_df = pd.read_sql(text(prices_query), engine)
    prices_path = output_dir / "dramvalue_prices.csv"
    prices_df.to_csv(prices_path, index=False)
    counts["prices"] = len(prices_df)
    print(f"  -> {counts['prices']:,} rows -> {prices_path.name}")

    print("Exporting market stats...")
    market_query = """
        SELECT
            id, auction_name, auction_slug, period_date,
            winning_bid_max, winning_bid_min, winning_bid_mean,
            trading_volume, lots_count, all_auctions_lots_count, created_at
        FROM market_stats
        ORDER BY period_date DESC, auction_slug
    """
    market_df = pd.read_sql(text(market_query), engine)
    market_path = output_dir / "dramvalue_market_stats.csv"
    market_df.to_csv(market_path, index=False)
    counts["market_stats"] = len(market_df)
    print(f"  -> {counts['market_stats']:,} rows -> {market_path.name}")

    readme = output_dir / "README.md"
    readme.write_text(
        "# DramValue Whisky Price Intelligence Dataset\n\n"
        f"Exported from dramvalue.com on {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}.\n\n"
        f"- dramvalue_bottles.csv: {counts['bottles']:,} bottles\n"
        f"- dramvalue_prices.csv: {counts['prices']:,} prices\n"
        f"- dramvalue_market_stats.csv: {counts['market_stats']:,} market stats\n",
        encoding="utf-8",
    )

    engine.dispose()
    return counts


def write_dataset_metadata(output_dir: Path, dataset_id: str, counts: dict[str, int]) -> None:
    metadata = {
        "title": "DramValue Whisky Price Intelligence",
        "id": dataset_id,
        "subtitle": "Whisky auction and retail prices from dramvalue.com",
        "description": (
            "Bottle catalog, price history, and auction market statistics from dramvalue.com. "
            f"Contains {counts['bottles']:,} bottles and {counts['prices']:,} price records."
        ),
        "isPrivate": False,
        "licenses": [{"name": "CC0-1.0"}],
        "keywords": ["whisky", "whiskey", "auction", "prices", "spirits"],
    }
    (output_dir / "dataset-metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )


def _load_kaggle_token() -> None:
    if os.getenv("KAGGLE_API_TOKEN"):
        return
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("KAGGLE_API_TOKEN="):
                os.environ["KAGGLE_API_TOKEN"] = line.split("=", 1)[1].strip()
                return
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if kaggle_json.exists():
        data = json.loads(kaggle_json.read_text(encoding="utf-8"))
        token = data.get("token")
        if token:
            os.environ["KAGGLE_API_TOKEN"] = token
            access_token = Path.home() / ".kaggle" / "access_token"
            access_token.parent.mkdir(parents=True, exist_ok=True)
            access_token.write_text(token, encoding="utf-8")
            access_token.chmod(0o600)


def push_to_kaggle(output_dir: Path, dataset_id: str, message: str) -> None:
    _load_kaggle_token()
    if not os.getenv("KAGGLE_API_TOKEN") and not (Path.home() / ".kaggle" / "access_token").exists():
        raise RuntimeError(
            "Kaggle authentication not configured. Set KAGGLE_API_TOKEN in .env or run: kaggle auth login"
        )
    print(f"Uploading to Kaggle dataset {dataset_id}...")
    version_cmd = [
        sys.executable, "-m", "kaggle", "datasets", "version",
        "-p", str(output_dir), "-m", message, "--dir-mode", "zip",
    ]
    result = subprocess.run(version_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(result.stdout.strip() or "Dataset version uploaded successfully.")
        return
    combined = result.stderr + result.stdout
    if "404" in combined or "does not exist" in combined.lower():
        print("Dataset not found — creating new dataset...")
        create_cmd = [
            sys.executable, "-m", "kaggle", "datasets", "create",
            "-p", str(output_dir), "--dir-mode", "zip",
        ]
        create_result = subprocess.run(create_cmd, capture_output=True, text=True)
        if create_result.returncode != 0:
            raise RuntimeError(create_result.stderr or create_result.stdout)
        print(create_result.stdout.strip() or f"Created dataset {dataset_id}")
        return
    raise RuntimeError(combined)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export and push DramValue data to Kaggle")
    parser.add_argument("--dataset", default=DEFAULT_DATASET_ID)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--from-dir", type=Path, help="Use existing CSV export directory (skip DB export)")
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--message", default="")
    args = parser.parse_args()

    data_dir = args.from_dir or args.output_dir

    if args.from_dir is None and not args.export_only:
        print("Exporting from database...")
        run_export(data_dir)
    elif args.from_dir is None:
        run_export(data_dir)

    counts = get_counts(data_dir)
    write_dataset_metadata(data_dir, args.dataset, counts)
    print(f"Ready: {counts['bottles']:,} bottles, {counts['prices']:,} prices, {counts['market_stats']:,} market stats")

    if args.export_only:
        print(f"\nExport complete in {data_dir}")
        return 0

    message = args.message or f"DramValue export {datetime.now(timezone.utc):%Y-%m-%d} — {counts['prices']:,} prices"
    push_to_kaggle(data_dir, args.dataset, message)
    print(f"\nDone. Dataset: https://www.kaggle.com/datasets/{args.dataset}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
