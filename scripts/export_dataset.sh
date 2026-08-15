#!/usr/bin/env bash
# Export DramValue database tables to CSV via PostgreSQL COPY (memory-safe for large tables).
#
# Usage:
#   ./scripts/export_dataset.sh
#   ./scripts/export_dataset.sh /path/to/output

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$REPO_DIR/data/huggingface}"
COMPOSE="docker compose -f $REPO_DIR/docker-compose.yml"

mkdir -p "$OUT_DIR"
echo "Exporting to $OUT_DIR ..."

export_bottles() {
  $COMPOSE exec -T db psql -U wtracker -d wtracker -c \
    "\COPY (
      SELECT id, name, normalized_name, distillery, brand, category::text AS category,
             age_statement, proof, size_ml, release_year,
             is_limited_release, is_allocated, msrp,
             price_count, avg_price, min_price, max_price,
             last_price, last_price_date, price_trend,
             created_at, updated_at, stats_updated_at
      FROM bottles WHERE is_active = true ORDER BY id
    ) TO STDOUT WITH CSV HEADER" > "$OUT_DIR/dramvalue_bottles.csv"
}

export_prices() {
  $COMPOSE exec -T db psql -U wtracker -d wtracker -c \
    "\COPY (
      SELECT p.id AS price_id, p.bottle_id, b.name AS bottle_name,
             b.distillery, b.brand, b.category::text AS category,
             p.price, p.currency, p.price_usd, p.source::text AS source,
             p.source_name, p.auction_house::text AS auction_house,
             p.source_url, p.source_id, p.transaction_date,
             p.is_sold, p.is_excluded, p.created_at
      FROM prices p
      JOIN bottles b ON b.id = p.bottle_id
      WHERE p.is_excluded = false
      ORDER BY p.transaction_date DESC, p.id DESC
    ) TO STDOUT WITH CSV HEADER" > "$OUT_DIR/dramvalue_prices.csv"
}

export_market() {
  $COMPOSE exec -T db psql -U wtracker -d wtracker -c \
    "\COPY (
      SELECT id, auction_name, auction_slug, period_date,
             winning_bid_max, winning_bid_min, winning_bid_mean,
             trading_volume, lots_count, all_auctions_lots_count, created_at
      FROM market_stats
      ORDER BY period_date DESC, auction_slug
    ) TO STDOUT WITH CSV HEADER" > "$OUT_DIR/dramvalue_market_stats.csv"
}

echo "[1/3] bottles..."
export_bottles
echo "  $(($(wc -l < "$OUT_DIR/dramvalue_bottles.csv") - 1)) rows"

echo "[2/3] prices (this may take several minutes)..."
export_prices
echo "  $(($(wc -l < "$OUT_DIR/dramvalue_prices.csv") - 1)) rows"

echo "[3/3] market stats..."
export_market
echo "  $(($(wc -l < "$OUT_DIR/dramvalue_market_stats.csv") - 1)) rows"

python3 << PY
from datetime import datetime, timezone
from pathlib import Path

out = Path("$OUT_DIR")
counts = {
    "bottles": sum(1 for _ in open(out / "dramvalue_bottles.csv")) - 1,
    "prices": sum(1 for _ in open(out / "dramvalue_prices.csv")) - 1,
    "market_stats": sum(1 for _ in open(out / "dramvalue_market_stats.csv")) - 1,
}
(out / "README.md").write_text(
    "# DramValue Whisky Price Intelligence Dataset\\n\\n"
    f"Exported from dramvalue.com on {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}.\\n\\n"
    f"- dramvalue_bottles.csv: {counts['bottles']:,} bottles\\n"
    f"- dramvalue_prices.csv: {counts['prices']:,} prices\\n"
    f"- dramvalue_market_stats.csv: {counts['market_stats']:,} market stats\\n",
    encoding="utf-8",
)
print("Export complete:", counts)
PY

ls -lh "$OUT_DIR"
