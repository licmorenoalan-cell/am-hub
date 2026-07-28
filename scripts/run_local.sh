#!/bin/bash
set -e

cd "$(dirname "$0")/.."
source .venv/bin/activate

python -m py_compile app.py pocket_app.py am_hub_core.py scripts/*.py
python -m unittest discover -s tests -v
python -m streamlit run app.py --server.headless=false --server.port=8501
