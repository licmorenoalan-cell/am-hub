#!/bin/bash
set -e

cd "$(dirname "$0")/.."
source .venv/bin/activate

MSG="${1:-Actualizar app}"

echo "Chequeando app.py..."
python -m py_compile app.py

echo "Estado actual:"
git status --short

echo "Agregando archivos de código..."
git add app.py requirements.txt .streamlit/config.toml 2>/dev/null || true

if git diff --cached --quiet; then
  echo "No hay cambios de código para commitear."
else
  git commit -m "$MSG"
  git push
fi

echo "Deploy enviado a GitHub."
