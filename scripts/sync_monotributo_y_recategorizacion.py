#!/usr/bin/env python3
"""Sincroniza pagos y recategorizaciones individuales de Monotributo."""

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

PERSONAS = (
    ("Abril Larreta", "Abril Larreta", "27-44998850-2"),
    ("Adriana Dominguez", "Adriana Dominguez", "23-14271037-4"),
    ("Joaquín Mengide", "Joaquín Mengide", "23-34037156-9"),
    ("Juan Mallo", "Juan Mallo", "20-41824832-8"),
    ("Leslie Vera", "Leslie Vera", "27-38157761-4"),
    ("Martina Peirano", "Martina Peirano", "27-38992790-8"),
    ("Mica Verta", "Mica Verta", "27-38657949-6"),
    ("Micaela Alegre", "Micaela Alegre", "27-42315458-1"),
    ("Nancy", "Nancy", "27-22497248-8"),
    ("Natalia Gena", "Natalia Gena", ""),
    ("Santiago Rios", "Santiago Rios", "20-40676310-3"),
    ("Leyla Djanikian", "Leyla Djanikian", "27-34555265-6"),
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


def checklist(*items: str) -> str:
    return json.dumps([{"texto": item, "hecho": False} for item in items], ensure_ascii=False)


def row_for(
    *, client: str, taxpayer: str, cuit: str, kind: str, due: str, frequency: str
) -> dict:
    key = f"{kind}:{taxpayer.casefold()}"
    cuit_note = f" CUIT: {cuit}." if cuit else " CUIT pendiente en ficha fiscal."
    if kind == "monotributo":
        title = f"Monotributo — {taxpayer}"
        description = "Control mensual del pago de Monotributo." + cuit_note
        items = (
            "Verificar deuda y credencial vigente",
            "Preparar o confirmar el pago",
            "Registrar comprobante y observaciones",
        )
    else:
        title = f"Recategorización Monotributo — {taxpayer}"
        description = (
            "Control semestral de recategorización de Monotributo. "
            "Vencimientos generales: 5 de febrero y 5 de agosto." + cuit_note
        )
        items = (
            "Revisar facturación e ingresos de los últimos 12 meses",
            "Controlar alquileres y restantes parámetros aplicables",
            "Determinar si mantiene o modifica la categoría",
            "Realizar o documentar el control y guardar la constancia",
        )
    return {
        "id": stable_code("TAR-FISC", key),
        "cliente": client,
        "tarea": title,
        "responsable_am": "AM Consultora",
        "prioridad": "Alta",
        "estado": "Pendiente",
        "fecha_limite": due,
        "descripcion": description,
        "comentarios": "",
        "fecha_carga": TODAY,
        "creado_por": "Alan Moreno",
        "fecha_actualizacion": TODAY,
        "actualizado_por": "Alan Moreno",
        "checklist": checklist(*items),
        "avance": 0,
        "recurrente": "Sí",
        "frecuencia": frequency,
        "intervalo": 1,
        "serie_id": stable_code("SER-FISC", key),
        "ocurrencia": 1,
        "proyecto": "Obligaciones fiscales",
        "origen": "Sincronización Monotributo 23/10/2026",
        "id_externo": "",
        "categoria": "Monotributo",
        "unidad": "AM Consultora",
        "orden_manual": "",
        "archivos_habilitados": "No",
        "posicion_manual": "",
    }


def build_rows() -> list[dict]:
    rows = []
    for client, taxpayer, cuit in PERSONAS:
        rows.append(
            row_for(
                client=client,
                taxpayer=taxpayer,
                cuit=cuit,
                kind="monotributo",
                due="2026-10-20",
                frequency="Mensual",
            )
        )
        rows.append(
            row_for(
                client=client,
                taxpayer=taxpayer,
                cuit=cuit,
                kind="recategorizacion-monotributo",
                due="2027-02-05",
                frequency="Semestral",
            )
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", default=str(ROOT / "backups_locales"))
    args = parser.parse_args()
    rows = build_rows()
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
    backup = backup_dir / f"tareas_antes_monotributo_{timestamp}.csv"
    current.to_csv(backup, index=False)

    inserted, updated = [], []
    with engine.begin() as conn:
        # Renombrar la ficha sin alterar usuario, asignaciones ni historial asociado.
        for table in ("clientes", "usuarios", "asignaciones_equipo", "tareas"):
            conn.execute(
                text(
                    f'UPDATE "{table}" SET "cliente"=\'Nancy\' '
                    'WHERE lower(coalesce("cliente",\'\'))=lower(\'Naomi Kraus Studio\')'
                )
            )

        # Retirar las series pedidas y la vieja recategorización genérica.
        conn.execute(
            text(
                'DELETE FROM "tareas" WHERE "categoria"=\'Monotributo\' AND ('
                'lower("cliente") IN (lower(\'Jose Jaure\'), lower(\'Marlitt Elisa Ordoñez Arteaga\')) '
                'OR (lower("cliente")=lower(\'Atlantis Cars\') '
                'AND (lower("tarea") LIKE \'%franco%\' OR lower("tarea") LIKE \'%martín%\' '
                'OR lower("tarea") LIKE \'%martin%\'))'
                ')'
            )
        )
        conn.execute(
            text(
                'DELETE FROM "tareas" WHERE "estado"<>\'Finalizada\' '
                'AND lower("tarea") LIKE \'recategorizaci%n monotributo - control semestral%\''
            )
        )

        for row in rows:
            existing = conn.execute(
                text(
                    'SELECT "id" FROM "tareas" WHERE "estado"<>\'Finalizada\' AND ('
                    '"serie_id"=:serie_id OR '
                    '(lower("cliente")=lower(:cliente) AND lower("tarea")=lower(:tarea))'
                    ') LIMIT 1'
                ),
                row,
            ).mappings().first()
            if existing:
                conn.execute(
                    text(
                        'UPDATE "tareas" SET "cliente"=:cliente, "tarea"=:tarea, '
                        '"descripcion"=:descripcion, "checklist"=:checklist, '
                        '"fecha_limite"=:fecha_limite, "recurrente"=\'Sí\', '
                        '"frecuencia"=:frecuencia, "intervalo"=1, "serie_id"=:serie_id, '
                        '"fecha_actualizacion"=:fecha_actualizacion, '
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
