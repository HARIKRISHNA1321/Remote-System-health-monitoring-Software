#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [[ ! -x "$PROJECT_DIR/.venv/bin/osken-manager" ]]; then
    echo "ERROR: OS-Ken is not installed in the project virtual environment."
    echo "Run: pip install -r requirements.txt"
    exit 1
fi

source "$PROJECT_DIR/.venv/bin/activate"

echo "Starting Project 11 SDN Controller..."
exec osken-manager --verbose --ofp-tcp-listen-port 6653 controller.py
