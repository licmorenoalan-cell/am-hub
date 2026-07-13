from pathlib import Path
import re

import pandas as pd
from sqlalchemy import create_engine, text


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SECRETS_PATH = BASE_DIR / ".streamlit" / "secrets.toml"

TABLE_MAP = {
    "clientes.csv": "clientes",
    "contenidos.csv": "contenidos",
    "materiales.csv": "materiales",
    "campanias.csv": "campanias",
    "reportes.csv": "reportes",
    "tareas.csv": "tareas",
    "usuarios.csv": "usuarios",
    "asignaciones_equipo.csv": "asignaciones_equipo",
    "objetivos.csv": "objetivos",
    "documentos.csv": "documentos",
    "indicadores.csv": "indicadores",
    "indicadores_movimientos.csv": "indicadores_movimientos",
}


def read_database_url() -> str:
    if not SECRETS_PATH.exists():
        raise SystemExit("No existe .streamlit/secrets.toml con DATABASE_URL.")

    text = SECRETS_PATH.read_text()
    match = re.search(r'DATABASE_URL\s*=\s*"([^"]+)"', text)

    if not match:
        raise SystemExit("No encontré DATABASE_URL en .streamlit/secrets.toml.")

    url = match.group(1).strip()

    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)

    return url


def main():
    url = read_database_url()
    engine = create_engine(url, pool_pre_ping=True)

    with engine.connect() as conn:
        now = conn.execute(text("SELECT now()")).scalar()
        print(f"Conexión OK: {now}")

    for filename, table_name in TABLE_MAP.items():
        path = DATA_DIR / filename

        if not path.exists():
            print(f"SKIP {filename}: no existe.")
            continue

        df = pd.read_csv(path, dtype=str).fillna("")

        df.to_sql(
            table_name,
            engine,
            if_exists="replace",
            index=False,
        )

        print(f"OK {filename} → {table_name}: {len(df)} filas")

    print("Migración terminada.")


if __name__ == "__main__":
    main()
