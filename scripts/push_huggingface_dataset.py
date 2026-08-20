#!/usr/bin/env python3
"""
Export DramValue CSVs and upload to Hugging Face Hub.

Usage:
    python scripts/push_huggingface_dataset.py
    python scripts/push_huggingface_dataset.py --from-dir data/huggingface
    python scripts/push_huggingface_dataset.py --export-only
    python scripts/push_huggingface_dataset.py --repo datamatters24/dramvalue-whisky-prices

Requires HF_TOKEN in .env or environment (https://huggingface.co/settings/tokens).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.dataset_card import write_huggingface_readme

DEFAULT_REPO = "datamatters24/dramvalue-whisky-prices"
OUTPUT_DIR = ROOT / "data" / "huggingface"


def load_env_value(*keys: str) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value

    env_path = ROOT / ".env"
    if not env_path.exists():
        return None

    prefixes = tuple(f"{key}=" for key in keys)
    for line in env_path.read_text(encoding="utf-8").splitlines():
        for prefix in prefixes:
            if line.startswith(prefix):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def load_hf_token() -> str:
    token = load_env_value("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")
    if not token:
        raise RuntimeError(
            "Hugging Face token not found. Add HF_TOKEN=hf_... to .env or export HF_TOKEN."
        )
    return token


def load_hf_repo() -> str:
    return load_env_value("HF_DATASET_REPO") or DEFAULT_REPO


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


def write_dataset_card(data_dir: Path, repo_id: str, counts: dict[str, int]) -> None:
    write_huggingface_readme(data_dir, counts, hf_repo=repo_id)


def run_export(output_dir: Path) -> None:
    script = ROOT / "scripts" / "export_dataset.sh"
    subprocess.run(["bash", str(script), str(output_dir)], check=True)


def push_to_huggingface(data_dir: Path, repo_id: str, message: str) -> str:
    token = load_hf_token()
    os.environ["HF_TOKEN"] = token

    try:
        from huggingface_hub import HfApi, create_repo
    except ImportError as exc:
        raise RuntimeError("Install huggingface_hub: pip install huggingface_hub") from exc

    api = HfApi(token=token)
    create_repo(repo_id, repo_type="dataset", exist_ok=True, token=token)

    print(f"Uploading {data_dir} -> hf.co/datasets/{repo_id} ...")
    api.upload_folder(
        folder_path=str(data_dir),
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=message,
        token=token,
    )
    return f"https://huggingface.co/datasets/{repo_id}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export and push DramValue data to Hugging Face")
    parser.add_argument("--repo", default=load_hf_repo(), help=f"HF dataset repo (default: from HF_DATASET_REPO or {DEFAULT_REPO})")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--from-dir", type=Path, help="Use existing CSV export directory (skip DB export)")
    parser.add_argument("--export-only", action="store_true", help="Export CSVs only, do not upload")
    parser.add_argument("--message", default="", help="Commit message for HF upload")
    args = parser.parse_args()

    data_dir = args.from_dir or args.output_dir

    if args.from_dir is None and not args.export_only:
        print("Exporting from database...")
        run_export(data_dir)
    elif args.from_dir is None:
        run_export(data_dir)

    counts = get_counts(data_dir)
    write_dataset_card(data_dir, args.repo, counts)
    print(f"Ready: {counts['bottles']:,} bottles, {counts['prices']:,} prices, {counts['market_stats']:,} market stats")

    if args.export_only:
        print(f"Export complete: {data_dir}")
        return 0

    message = args.message or (
        f"DramValue export {datetime.now(timezone.utc):%Y-%m-%d} — "
        f"{counts['prices']:,} prices, {counts['bottles']:,} bottles"
    )
    url = push_to_huggingface(data_dir, args.repo, message)
    print(f"Done: {url}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
