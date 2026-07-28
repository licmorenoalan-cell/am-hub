#!/bin/bash
set -e

cd "$(dirname "$0")/.."
source .venv/bin/activate

MSG="${1:-Actualizar app}"

echo "Chequeando código y pruebas..."
python -m py_compile app.py pocket_app.py am_hub_core.py scripts/*.py
python -m unittest discover -s tests -v
python -m pip check

echo "Estado actual:"
git status --short

echo "Agregando archivos de código..."
git add app.py pocket_app.py am_hub_core.py tests README.md requirements.txt .streamlit/config.toml 2>/dev/null || true

if git diff --cached --quiet; then
  echo "No hay cambios de código para commitear."
else
  git commit -m "$MSG"
  git push
fi

echo "Deploy enviado a GitHub."
