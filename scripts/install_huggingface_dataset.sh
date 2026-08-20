#!/usr/bin/env bash
# Download the DramValue dataset from Hugging Face Hub.
#
# Usage:
#   ./scripts/install_huggingface_dataset.sh
#   ./scripts/install_huggingface_dataset.sh /path/to/output
#   HF_DATASET_REPO=myuser/my-dataset ./scripts/install_huggingface_dataset.sh
#
# Optional: import into running DramValue database after download:
#   ./scripts/install_huggingface_dataset.sh && IMPORT_TO_DB=1 ./scripts/install_huggingface_dataset.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$REPO_DIR/data/huggingface}"
HF_REPO="${HF_DATASET_REPO:-datamatters24/dramvalue-whisky-prices}"
LOG_DIR="$REPO_DIR/logs"
LOG_FILE="$LOG_DIR/hf_install.log"

mkdir -p "$OUT_DIR" "$LOG_DIR"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "DramValue Hugging Face dataset install"
log "  Repo:   $HF_REPO"
log "  Output: $OUT_DIR"

if ! python3 -c "import huggingface_hub" 2>/dev/null; then
  log "Installing huggingface_hub..."
  pip3 install --quiet huggingface_hub
fi

if [[ -f "$REPO_DIR/.env" ]]; then
  # shellcheck disable=SC1091
  set +u
  source <(grep -E '^HF_TOKEN=|^HUGGING_FACE_HUB_TOKEN=' "$REPO_DIR/.env" | sed 's/^/export /')
  set -u
fi

log "Downloading dataset..."
python3 - << PY
from huggingface_hub import snapshot_download
import os

repo = os.environ.get("HF_DATASET_REPO", "$HF_REPO")
out = "$OUT_DIR"
token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")

path = snapshot_download(
    repo_id=repo,
    repo_type="dataset",
    local_dir=out,
    token=token,
)
print(f"Downloaded to {path}")
PY

log "Files:"
ls -lh "$OUT_DIR" | tee -a "$LOG_FILE"

if [[ "${IMPORT_TO_DB:-0}" == "1" ]]; then
  log "Importing into database via Docker..."
  CONTAINER="wtracker-api"
  REMOTE_DIR="/tmp/hf_dataset"
  docker cp "$OUT_DIR/." "$CONTAINER:$REMOTE_DIR/"
  docker compose -f "$REPO_DIR/docker-compose.yml" exec -T api \
    python scripts/reimport_csv_data.py --csv-dir "$REMOTE_DIR"
  log "Database import complete."
fi

log "Install complete."
log "  Bottles:  $OUT_DIR/dramvalue_bottles.csv"
log "  Prices:   $OUT_DIR/dramvalue_prices.csv"
log "  Market:   $OUT_DIR/dramvalue_market_stats.csv"
