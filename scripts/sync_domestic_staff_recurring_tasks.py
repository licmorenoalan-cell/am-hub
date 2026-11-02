#!/usr/bin/env python3
"""Crea las recurrencias mensuales de liquidación de casas particulares."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
import toml


ROOT = Path(__file__).resolve().parents[1]
TODAY = date.today().isoformat()
FIRST_DUE = "2026-11-01"

TITLES = (
    "AGUS CABALEIRO",
    "DANI CABALEIRO",
    "LEY DJANIKIAN",
)


def database_url() -> str:
    secrets = toml.loads((ROOT / ".streamlit" / "secrets.toml").read_text())
    url = str(secrets["DATABASE_URL"])
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def stable_code(prefix: str, key: str) -> str:
    return f"{prefix}-{hashlib.sha256(key.encode()).hexdigest()[:20]}"


def checklist() -> str:
    return json.dumps(
        [
            {"texto": "Relevar novedades del período", "hecho": False},
            {"texto": "Liquidar y emitir el recibo", "hecho": False},
            {"texto": "Preparar el pago correspondiente", "hecho": False},
            {"texto": "Guardar recibo y comprobante", "hecho": False},
        ],
        ensure_ascii=False,
    )


def task_values(title: str) -> dict:
    key = f"casas-particulares:{title.casefold()}"
    return {
        "id": stable_code("TAR-LAB", key),
        "cliente": title,
        "tarea": title,
        "responsable_am": "AM Consultora",
        "prioridad": "Alta",
        "estado": "Pendiente",
        "fecha_limite": FIRST_DUE,
        "descripcion": (
            "Liquidación mensual de empleada doméstica / casas particulares. "
            "Vencimiento operativo interno: día 1 de cada mes."
        ),
        "comentarios": "",
        "fecha_carga": TODAY,
        "creado_por": "Alan Moreno",
        "fecha_actualizacion": TODAY,
        "actualizado_por": "Alan Moreno",
        "checklist": checklist(),
        "avance": 0,
        "recurrente": "Sí",
        "frecuencia": "Mensual",
        "intervalo": 1,
        "serie_id": stable_code("SER-LAB", key),
        "ocurrencia": 1,
        "proyecto": "Liquidación empleada doméstica",
        "origen": "Solicitud Alan 01/11/2026",
        "id_externo": "",
        "categoria": "Casas Particulares",
        "unidad": "AM Consultora",
        "orden_manual": "",
        "archivos_habilitados": "No",
        "posicion_manual": "",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", default=str(ROOT / "backups_locales"))
    args = parser.parse_args()
    rows = [task_values(title) for title in TITLES]

    if not args.apply:
        for row in rows:
            print(row["fecha_limite"], row["frecuencia"], row["tarea"])
        return

    engine = create_engine(database_url(), connect_args={"prepare_threshold": None})
    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with engine.connect() as conn:
        current = pd.read_sql(text('SELECT * FROM "tareas"'), conn)
    backup = backup_dir / f"tareas_antes_casas_particulares_{timestamp}.csv"
    current.to_csv(backup, index=False)

    inserted, updated = [], []
    with engine.begin() as conn:
        for row in rows:
            existing = conn.execute(
                text(
                    'SELECT "id" FROM "tareas" WHERE "estado" <> \'Finalizada\' AND ('
                    '"serie_id"=:serie_id OR ('
                    'lower("tarea")=lower(:tarea) AND '
                    'lower(coalesce("categoria",\'\'))=lower(:categoria))) LIMIT 1'
                ),
                row,
            ).mappings().first()
            if existing:
                conn.execute(
                    text(
                        'UPDATE "tareas" SET "cliente"=:cliente, "tarea"=:tarea, '
                        '"descripcion"=:descripcion, "checklist"=:checklist, '
                        '"fecha_limite"=:fecha_limite, "recurrente"=\'Sí\', '
                        '"frecuencia"=\'Mensual\', "intervalo"=1, '
                        '"serie_id"=:serie_id, "categoria"=:categoria, '
                        '"proyecto"=:proyecto, "fecha_actualizacion"=:fecha_actualizacion, '
                        '"actualizado_por"=:actualizado_por WHERE "id"=:existing_id'
                    ),
                    {**row, "existing_id": existing["id"]},
                )
                updated.append(row["tarea"])
            else:
                columns = list(row)
                conn.execute(
                    text(
                        'INSERT INTO "tareas" ('
                        + ", ".join(f'"{column}"' for column in columns)
                        + ") VALUES ("
                        + ", ".join(f":{column}" for column in columns)
                        + ")"
                    ),
                    row,
                )
                inserted.append(row["tarea"])

    print(f"Backup: {backup}")
    print(f"Insertadas: {len(inserted)}")
    print(f"Actualizadas: {len(updated)}")


if __name__ == "__main__":
    main()
