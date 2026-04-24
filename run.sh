#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# COMP-5700 – Security Requirements Change Detector
# Runner script (Task-4 deliverable)
#
# Usage:
#   ./run.sh <doc1.pdf> <doc2.pdf> [scan_target_dir]
#
# Example:
#   ./run.sh cis-r1.pdf cis-r2.pdf ./project-yamls
#
# Notes:
#   * Must be run inside an activated Python virtual environment with
#     `pip install -r requirements.txt` already completed.
#   * The third argument (scan target) is optional — if omitted, Task-3
#     writes the controls-mapping file but skips the Kubescape scan.
# ─────────────────────────────────────────────────────────────────────────────

set -e

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "Usage: $0 <doc1.pdf> <doc2.pdf> [scan_target_dir]"
    exit 1
fi

PDF1="$1"
PDF2="$2"
SCAN_TARGET="${3:-}"

if [ ! -f "$PDF1" ]; then
    echo "Error: PDF not found: $PDF1"
    exit 1
fi
if [ ! -f "$PDF2" ]; then
    echo "Error: PDF not found: $PDF2"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -n "$SCAN_TARGET" ]; then
    python main.py "$PDF1" "$PDF2" --scan-target "$SCAN_TARGET"
else
    python main.py "$PDF1" "$PDF2"
fi
