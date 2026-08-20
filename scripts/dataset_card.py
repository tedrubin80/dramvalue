"""Shared dataset README and Kaggle metadata for DramValue exports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HF_REPO = "datamatters24/dramvalue-whisky-prices"
DEFAULT_KAGGLE_DATASET = "theodorerubin/dramvalue-whisky-prices"


def export_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def markdown_body(
    counts: dict[str, int],
    exported: str,
    hf_repo: str,
    kaggle_dataset: str,
) -> str:
    kaggle_url = f"https://www.kaggle.com/datasets/{kaggle_dataset}"
    hf_url = f"https://huggingface.co/datasets/{hf_repo}"

    return f"""# DramValue Whisky Price Intelligence

Whisky bottle catalog, price history, and auction market statistics exported from [dramvalue.com](https://dramvalue.com).

**Last export:** {exported}

| | |
|---|---|
| Bottles | {counts['bottles']:,} |
| Price records | {counts['prices']:,} |
| Market stat rows | {counts['market_stats']:,} |

## Files

| File | Rows | Description |
|------|------|-------------|
| `dramvalue_bottles.csv` | {counts['bottles']:,} | Bottle catalog with cached price stats |
| `dramvalue_prices.csv` | {counts['prices']:,} | Individual price records (auction, retail, import) |
| `dramvalue_market_stats.csv` | {counts['market_stats']:,} | Monthly auction house aggregates |

### `dramvalue_bottles.csv`

Key columns: `id`, `name`, `distillery`, `brand`, `category`, `age_statement`, `proof`, `size_ml`, `price_count`, `avg_price`, `min_price`, `max_price`, `last_price`, `last_price_date`.

### `dramvalue_prices.csv`

Key columns: `price_id`, `bottle_id`, `bottle_name`, `price`, `currency`, `price_usd`, `source`, `source_name`, `auction_house`, `source_url`, `transaction_date`.

### `dramvalue_market_stats.csv`

Key columns: `auction_name`, `auction_slug`, `period_date`, `winning_bid_mean`, `trading_volume`, `lots_count`.

## Download

**Hugging Face:** [{hf_repo}]({hf_url})

```bash
pip install huggingface_hub
huggingface-cli download {hf_repo} --repo-type dataset --local-dir ./data/huggingface
```

**Kaggle:** [{kaggle_dataset}]({kaggle_url})

```bash
pip install kaggle
kaggle datasets download -d {kaggle_dataset} -p ./data/kaggle --unzip
```

One-liner (Hugging Face):

```bash
curl -fsSL https://raw.githubusercontent.com/tedrubin80/dramvalue/main/scripts/install_huggingface_dataset.sh | bash
```

## License

CC0 1.0 Universal (public domain dedication).
"""


def write_huggingface_readme(
    data_dir: Path,
    counts: dict[str, int],
    hf_repo: str = DEFAULT_HF_REPO,
    kaggle_dataset: str = DEFAULT_KAGGLE_DATASET,
) -> Path:
    exported = export_timestamp()
    body = markdown_body(counts, exported, hf_repo, kaggle_dataset)
    content = f"""---
license: cc0-1.0
task_categories:
- tabular-classification
language:
- en
tags:
- whisky
- whiskey
- auction
- prices
- spirits
size_categories:
- 1M<n<10M
---

{body}"""
    path = data_dir / "README.md"
    path.write_text(content, encoding="utf-8")
    return path


def write_kaggle_readme(
    data_dir: Path,
    counts: dict[str, int],
    hf_repo: str = DEFAULT_HF_REPO,
    kaggle_dataset: str = DEFAULT_KAGGLE_DATASET,
) -> Path:
    exported = export_timestamp()
    path = data_dir / "README.md"
    path.write_text(
        markdown_body(counts, exported, hf_repo, kaggle_dataset),
        encoding="utf-8",
    )
    return path


def write_kaggle_metadata(
    data_dir: Path,
    counts: dict[str, int],
    dataset_id: str = DEFAULT_KAGGLE_DATASET,
) -> Path:
    metadata = {
        "title": "DramValue Whisky Price Intelligence",
        "id": dataset_id,
        "subtitle": "Whisky auction and retail prices from dramvalue.com",
        "description": (
            "Bottle catalog, price history, and auction market statistics from dramvalue.com. "
            f"Contains {counts['bottles']:,} bottles and {counts['prices']:,} price records. "
            f"Also mirrored on Hugging Face at {DEFAULT_HF_REPO}."
        ),
        "isPrivate": False,
        "licenses": [{"name": "CC0-1.0"}],
    }
    path = data_dir / "dataset-metadata.json"
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return path
