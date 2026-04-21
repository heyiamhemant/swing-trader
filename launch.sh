#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

export FRED_API_KEY="db81286cac821c59591a01557838f502"

if [ ! -d ".venv" ]; then
    echo "Setting up for the first time..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -q -r requirements.txt
else
    source .venv/bin/activate
fi

mkdir -p data

PORT="${1:-5050}"

# Kill any existing server on this port
lsof -ti:"$PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 0.3

echo "Swing Trader: http://localhost:$PORT"
python server.py "$PORT"
