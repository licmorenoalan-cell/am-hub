#!/bin/bash
set -e

cd "$(dirname "$0")/.."
source .venv/bin/activate

python -m py_compile app.py
python -m streamlit run app.py --server.headless=false --server.port=8501
