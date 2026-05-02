#!/usr/bin/env sh
set -eu
XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
HOSTY_DATA_DIR="${HOSTY_DATA_DIR:-$XDG_DATA_HOME/hosty}"
export HOSTY_DATA_DIR
# Create the data dir if it does not exist
mkdir -p "$HOSTY_DATA_DIR"

cd /app/share
exec python3 /app/share/hosty.py "$@"
