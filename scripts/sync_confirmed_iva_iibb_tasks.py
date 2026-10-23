#!/usr/bin/env python3
"""Sincroniza las recurrencias confirmadas de IVA e IIBB sin duplicarlas."""

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
    return json.dumps(
        [{"texto": item, "hecho": False} for item in items],
        ensure_ascii=False,
    )


def task_values(client: str, category: str, due: str, description: str) -> dict:
    key = f"{category.casefold()}:{client.casefold()}"
    return {
        "id": stable_code("TAR-FISC", key),
        "cliente": client,
        "tarea": f"{category} — {client}",
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
        "checklist": checklist(
            "Cargar y controlar la documentación del período",
            "Preparar y revisar el papel de trabajo",
            "Presentar la declaración jurada",
            "Registrar resultado, pago y comprobante",
        ),
        "avance": 0,
        "recurrente": "Sí",
        "frecuencia": "Mensual",
        "intervalo": 1,
        "serie_id": stable_code("SER-FISC", key),
        "ocurrencia": 1,
        "proyecto": "Obligaciones fiscales",
        "origen": "Confirmación fiscal AM HUB 22/10/2026",
        "id_externo": "",
        "categoria": category,
        "unidad": "AM Consultora",
        "orden_manual": "",
        "archivos_habilitados": "No",
        "posicion_manual": "",
    }


def build_rows() -> list[dict]:
    return [
        task_values(
            "Alejandro Vera",
            "IVA",
            "2026-10-21",
            "Régimen fiscal: IVA. CUIT: 20-16336071-4. Período: septiembre 2026.",
        ),
        task_values(
            "Alejandro Vera",
            "Ingresos Brutos",
            "2026-10-15",
            "Régimen fiscal: IIBB AGIP Local. CUIT: 20-16336071-4. Período: septiembre 2026.",
        ),
        task_values(
            "EXPRESO RDA SAS",
            "Ingresos Brutos",
            "2026-11-20",
            "Régimen fiscal: IIBB Convenio Multilateral. CUIT: 30-71961601-8. Primer período: octubre 2026.",
        ),
        task_values(
            "Matías Ojeda",
            "Ingresos Brutos",
            "2026-10-28",
            "Régimen fiscal: IIBB ARBA Local. CUIT: 20-35656955-6. Período: septiembre 2026.",
        ),
        task_values(
            "Verónica Martínez",
            "Ingresos Brutos",
            "2026-10-29",
            "Régimen fiscal: IIBB ARBA Local. CUIT: 27-36806250-8. Período: septiembre 2026.",
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", default=str(ROOT / "backups_locales"))
    args = parser.parse_args()
    rows = build_rows()
    if not args.apply:
        for row in rows:
            print(row["fecha_limite"], row["tarea"])
        return

    engine = create_engine(database_url(), connect_args={"prepare_threshold": None})
    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with engine.connect() as conn:
        current = pd.read_sql(text('SELECT * FROM "tareas"'), conn)
    backup = backup_dir / f"tareas_antes_iva_iibb_confirmados_{timestamp}.csv"
    current.to_csv(backup, index=False)

    inserted, updated = [], []
    with engine.begin() as conn:
        for row in rows:
            existing = conn.execute(
                text(
                    'SELECT "id" FROM "tareas" WHERE lower("cliente") = lower(:cliente) '
                    'AND lower("categoria") = lower(:categoria) '
                    'AND "estado" <> \'Finalizada\' ORDER BY "fecha_limite" DESC LIMIT 1'
                ),
                row,
            ).mappings().first()
            if existing:
                conn.execute(
                    text(
                        'UPDATE "tareas" SET "tarea"=:tarea, "fecha_limite"=:fecha_limite, '
                        '"descripcion"=:descripcion, "checklist"=:checklist, "recurrente"=\'Sí\', '
                        '"frecuencia"=\'Mensual\', "intervalo"=1, "serie_id"=:serie_id, '
                        '"categoria"=:categoria, "proyecto"=:proyecto, '
                        '"fecha_actualizacion"=:fecha_actualizacion, "actualizado_por"=:actualizado_por '
                        'WHERE "id"=:existing_id'
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

        # IVA ya existente: corregir la próxima ocurrencia al calendario oficial.
        ajustes_iva = (
            ("Matías Ojeda", "2026-11-24", "20-35656955-6"),
            ("Verónica Martínez", "2026-11-25", "27-36806250-8"),
            ("EXPRESO RDA SAS", "2026-11-25", "30-71961601-8"),
        )
        for client, due, cuit in ajustes_iva:
            conn.execute(
                text(
                    'UPDATE "tareas" SET "fecha_limite"=:due, '
                    '"descripcion"=:description, "fecha_actualizacion"=:today, '
                    '"actualizado_por"=\'Alan Moreno\' '
                    'WHERE lower("cliente")=lower(:client) AND "categoria"=\'IVA\' '
                    'AND "estado"<>\'Finalizada\''
                ),
                {
                    "client": client,
                    "due": due,
                    "today": TODAY,
                    "description": f"Régimen fiscal: IVA. CUIT: {cuit}. Período: octubre 2026.",
                },
            )

    print(f"Backup: {backup}")
    print(f"Insertadas: {len(inserted)}")
    print(f"Actualizadas: {len(updated)}")


if __name__ == "__main__":
    main()
