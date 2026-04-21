#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

export FRED_API_KEY="db81286cac821c59591a01557838f502"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

mkdir -p data

PORT="${1:-5050}"
echo "Starting Swing Trader at http://localhost:$PORT"
python server.py "$PORT"
