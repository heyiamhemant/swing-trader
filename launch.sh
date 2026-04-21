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

CMD="${1:-scan}"

case "$CMD" in
    scan)
        echo "Running full market scan..."
        python main.py scan
        echo "Generating dashboard..."
        python main.py dashboard
        ;;
    dashboard)
        echo "Generating dashboard..."
        python main.py dashboard
        ;;
    *)
        echo "Running: python main.py $@"
        python main.py "$@"
        ;;
esac
