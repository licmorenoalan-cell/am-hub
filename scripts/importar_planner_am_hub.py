#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


REQUIRED_INPUT_COLUMNS = {
    "id",
    "proyecto",
    "cliente",
    "tarea",
    "descripcion",
    "responsable_am",
    "prioridad",
    "estado",
    "fecha_limite",
    "checklist",
    "avance",
    "recurrente",
    "frecuencia",
    "intervalo",
    "serie_id",
    "ocurrencia",
    "comentarios",
    "origen",
    "id_externo",
    "categoria",
}


def read_database_url(project_dir: Path) -> str:
    secrets_path = project_dir / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        raise FileNotFoundError(
            f"No existe {secrets_path}. Ejecutá el script desde la carpeta am-hub."
        )

    content = secrets_path.read_text(encoding="utf-8")
    match = re.search(r'DATABASE_URL\s*=\s*"([^"]+)"', content)
    if not match:
        raise RuntimeError("No encontré DATABASE_URL en .streamlit/secrets.toml.")

    url = match.group(1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_int(value, default: int) -> int:
    try:
        if pd.isna(value) or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def ensure_columns(conn) -> None:
    additions = {
        "proyecto": "text",
        "origen": "text",
        "id_externo": "text",
        "categoria": "text",
        "checklist": "text",
        "avance": "integer",
        "recurrente": "text",
        "frecuencia": "text",
        "intervalo": "integer",
        "serie_id": "text",
        "ocurrencia": "integer",
        "descripcion": "text",
        "comentarios": "text",
        "fecha_carga": "text",
        "creado_por": "text",
        "fecha_actualizacion": "text",
        "actualizado_por": "text",
    }

    for column, sql_type in additions.items():
        conn.execute(
            text(
                f'ALTER TABLE "tareas" '
                f'ADD COLUMN IF NOT EXISTS "{column}" {sql_type}'
            )
        )

    conn.execute(
        text(
            'CREATE INDEX IF NOT EXISTS "idx_tareas_id_externo" '
            'ON "tareas" ("id_externo")'
        )
    )
    conn.execute(
        text(
            'CREATE INDEX IF NOT EXISTS "idx_tareas_proyecto" '
            'ON "tareas" ("proyecto")'
        )
    )


def load_input(excel_path: Path) -> pd.DataFrame:
    if not excel_path.exists():
        raise FileNotFoundError(f"No existe el archivo: {excel_path}")

    df = pd.read_excel(excel_path, sheet_name="Importar_AM_Hub", dtype=object)
    df.columns = [str(c).strip() for c in df.columns]

    missing = REQUIRED_INPUT_COLUMNS.difference(df.columns)
    if missing:
        raise RuntimeError(
            "Faltan columnas obligatorias en Importar_AM_Hub: "
            + ", ".join(sorted(missing))
        )

    df = df.dropna(how="all").copy()
    if df.empty:
        raise RuntimeError("La hoja Importar_AM_Hub no contiene tareas.")

    return df


def prepare_record(row: pd.Series, today: str) -> dict:
    record = {
        "id": normalize_text(row.get("id")),
        "proyecto": normalize_text(row.get("proyecto")) or "Sin proyecto",
        "cliente": normalize_text(row.get("cliente")),
        "tarea": normalize_text(row.get("tarea")),
        "descripcion": normalize_text(row.get("descripcion")),
        "responsable_am": normalize_text(row.get("responsable_am")) or "Sin asignar",
        "prioridad": normalize_text(row.get("prioridad")) or "Media",
        "estado": normalize_text(row.get("estado")) or "Pendiente",
        "fecha_limite": normalize_text(row.get("fecha_limite")),
        "checklist": normalize_text(row.get("checklist")) or "[]",
        "avance": normalize_int(row.get("avance"), 0),
        "recurrente": normalize_text(row.get("recurrente")) or "No",
        "frecuencia": normalize_text(row.get("frecuencia")),
        "intervalo": normalize_int(row.get("intervalo"), 1),
        "serie_id": normalize_text(row.get("serie_id")),
        "ocurrencia": normalize_int(row.get("ocurrencia"), 1),
        "comentarios": normalize_text(row.get("comentarios")),
        "origen": normalize_text(row.get("origen")) or "Microsoft Planner / Teams",
        "id_externo": normalize_text(row.get("id_externo")),
        "categoria": normalize_text(row.get("categoria")),
        "fecha_carga": today,
        "creado_por": "Migración Microsoft Planner",
        "fecha_actualizacion": today,
        "actualizado_por": "Migración Microsoft Planner",
    }

    if not record["id"]:
        record["id"] = f"MIG-{record['id_externo']}"
    if not record["tarea"]:
        raise ValueError("Hay una fila sin nombre de tarea.")
    if not record["id_externo"]:
        raise ValueError(f"La tarea '{record['tarea']}' no tiene id_externo.")

    return record


def import_tasks(project_dir: Path, excel_path: Path, dry_run: bool) -> None:
    from datetime import date

    df = load_input(excel_path)
    url = read_database_url(project_dir)
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )

    today = date.today().strftime("%Y-%m-%d")
    records = [prepare_record(row, today) for _, row in df.iterrows()]

    inserted = 0
    skipped_external = 0
    skipped_id = 0

    with engine.begin() as conn:
        ensure_columns(conn)

        existing_external = {
            str(value)
            for value in conn.execute(
                text(
                    'SELECT "id_externo" FROM "tareas" '
                    'WHERE "id_externo" IS NOT NULL AND "id_externo" <> \'\''
                )
            ).scalars()
        }
        existing_ids = {
            str(value)
            for value in conn.execute(text('SELECT "id" FROM "tareas"')).scalars()
        }

        insert_sql = text(
            '''
            INSERT INTO "tareas" (
                "id", "proyecto", "cliente", "tarea", "descripcion",
                "responsable_am", "prioridad", "estado", "fecha_limite",
                "checklist", "avance", "recurrente", "frecuencia",
                "intervalo", "serie_id", "ocurrencia", "comentarios",
                "origen", "id_externo", "categoria", "fecha_carga",
                "creado_por", "fecha_actualizacion", "actualizado_por"
            )
            VALUES (
                :id, :proyecto, :cliente, :tarea, :descripcion,
                :responsable_am, :prioridad, :estado, :fecha_limite,
                :checklist, :avance, :recurrente, :frecuencia,
                :intervalo, :serie_id, :ocurrencia, :comentarios,
                :origen, :id_externo, :categoria, :fecha_carga,
                :creado_por, :fecha_actualizacion, :actualizado_por
            )
            '''
        )

        for record in records:
            if record["id_externo"] in existing_external:
                skipped_external += 1
                continue
            if record["id"] in existing_ids:
                skipped_id += 1
                continue

            if not dry_run:
                conn.execute(insert_sql, record)
            inserted += 1
            existing_external.add(record["id_externo"])
            existing_ids.add(record["id"])

        if dry_run:
            conn.rollback()

    print("=" * 64)
    print("MIGRACIÓN PLANNER → AM HUB")
    print("=" * 64)
    print(f"Archivo: {excel_path}")
    print(f"Filas analizadas: {len(records)}")
    print(f"{'A insertar' if dry_run else 'Insertadas'}: {inserted}")
    print(f"Omitidas por id_externo duplicado: {skipped_external}")
    print(f"Omitidas por id duplicado: {skipped_id}")
    if dry_run:
        print("Modo simulación: no se guardaron cambios.")
    else:
        print("Migración finalizada correctamente.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importa tareas activas de Microsoft Planner a AM Hub."
    )
    parser.add_argument(
        "excel",
        type=Path,
        help="Ruta al archivo Planner_Activas_Normalizadas_AM_Hub.xlsx",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Carpeta raíz de am-hub. Por defecto, la carpeta actual.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida y muestra el resultado sin insertar registros.",
    )
    args = parser.parse_args()

    try:
        import_tasks(
            project_dir=args.project_dir.resolve(),
            excel_path=args.excel.expanduser().resolve(),
            dry_run=args.dry_run,
        )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
