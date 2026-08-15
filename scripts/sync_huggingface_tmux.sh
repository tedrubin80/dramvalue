#!/usr/bin/env bash
# Run DramValue -> Hugging Face sync inside a tmux session (survives disconnects).
#
# Usage:
#   ./scripts/sync_huggingface_tmux.sh              # export from DB + upload
#   ./scripts/sync_huggingface_tmux.sh --from-export # upload existing CSVs only
#   ./scripts/sync_huggingface_tmux.sh --attach       # attach to running session
#
# Requires HF_TOKEN in .env

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="${HF_SYNC_TMUX_SESSION:-dramvalue-hf-sync}"
LOG_DIR="$REPO_DIR/logs"
LOG_FILE="$LOG_DIR/hf_sync.log"
FROM_EXPORT=0
ATTACH_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --from-export) FROM_EXPORT=1 ;;
    --attach) ATTACH_ONLY=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

mkdir -p "$LOG_DIR"

if [[ "$ATTACH_ONLY" == "1" ]]; then
  exec tmux attach -t "$SESSION"
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session '$SESSION' is already running."
  echo "  Attach:  tmux attach -t $SESSION"
  echo "  Log:     tail -f $LOG_FILE"
  exit 0
fi

# Ensure huggingface_hub is available before starting long upload
if ! python3 -c "import huggingface_hub" 2>/dev/null; then
  echo "Installing huggingface_hub..."
  pip3 install --quiet huggingface_hub
fi

if [[ "$FROM_EXPORT" == "1" ]]; then
  CMD="cd '$REPO_DIR' && python3 scripts/push_huggingface_dataset.py --from-dir data/huggingface 2>&1 | tee -a '$LOG_FILE'"
else
  CMD="cd '$REPO_DIR' && python3 scripts/push_huggingface_dataset.py 2>&1 | tee -a '$LOG_FILE'"
fi

echo "Starting Hugging Face sync in tmux session: $SESSION"
echo "  Log: $LOG_FILE"
tmux new-session -d -s "$SESSION" "$CMD"

sleep 1
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Sync running in background."
  echo "  Attach:  tmux attach -t $SESSION"
  echo "  Detach:  Ctrl-b then d"
  echo "  Log:     tail -f $LOG_FILE"
else
  echo "ERROR: tmux session failed to start." >&2
  exit 1
fi
