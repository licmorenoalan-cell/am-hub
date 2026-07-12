#!/bin/bash
set -e

cd "$(dirname "$0")/.."
source .venv/bin/activate

python -m py_compile app.py

git commit --allow-empty -m "Forzar redeploy publico"
git push

echo "Redeploy público solicitado vía GitHub."
