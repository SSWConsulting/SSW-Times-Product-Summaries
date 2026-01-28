#!/usr/bin/env bash

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing dependencies..."
pip install -q -r requirements.txt

echo "Running script..."
python ./sprint_transcripts.py

echo ""
echo "Done. Press any key to close."
read -n 1 -s -r
