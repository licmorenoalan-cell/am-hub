from pathlib import Path
import re

from sqlalchemy import create_engine, text


BASE_DIR = Path(__file__).resolve().parent.parent
SECRETS_PATH = BASE_DIR / ".streamlit" / "secrets.toml"


def read_database_url() -> str:
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
    engine = create_engine(read_database_url(), pool_pre_ping=True)

    statements = [
        'CREATE INDEX IF NOT EXISTS idx_clientes_cliente ON "clientes" ("cliente")',
        'CREATE INDEX IF NOT EXISTS idx_contenidos_cliente ON "contenidos" ("cliente")',
        'CREATE INDEX IF NOT EXISTS idx_contenidos_cliente_fecha ON "contenidos" ("cliente", "fecha")',
        'CREATE INDEX IF NOT EXISTS idx_contenidos_cliente_estado ON "contenidos" ("cliente", "estado")',
        'CREATE INDEX IF NOT EXISTS idx_materiales_cliente ON "materiales" ("cliente")',
        'CREATE INDEX IF NOT EXISTS idx_campanias_cliente ON "campanias" ("cliente")',
        'CREATE INDEX IF NOT EXISTS idx_reportes_cliente ON "reportes" ("cliente")',
        'CREATE INDEX IF NOT EXISTS idx_tareas_cliente ON "tareas" ("cliente")',
        'CREATE INDEX IF NOT EXISTS idx_objetivos_cliente ON "objetivos" ("cliente")',
        'CREATE INDEX IF NOT EXISTS idx_objetivos_cliente_mes ON "objetivos" ("cliente", "mes")',
        'CREATE INDEX IF NOT EXISTS idx_movimientos_cliente ON "indicadores_movimientos" ("cliente")',
        'CREATE INDEX IF NOT EXISTS idx_movimientos_cliente_mes ON "indicadores_movimientos" ("cliente", "mes")',
        'CREATE INDEX IF NOT EXISTS idx_movimientos_cliente_tipo ON "indicadores_movimientos" ("cliente", "tipo")',
    ]

    with engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
                print("OK", stmt)
            except Exception as e:
                print("SKIP/ERROR", stmt, e)

    print("Índices aplicados.")


if __name__ == "__main__":
    main()
