#!/usr/bin/env python3
"""Sincroniza el relevamiento urgente de IIBB de las nuevas sociedades.

No asigna un régimen fiscal por inferencia. Una constitución, el domicilio fiscal
o la constancia de CUIT no reemplazan la constancia de IIBB local/Convenio.
"""

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
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def checklist(*items: str, completed: bool = False) -> str:
    return json.dumps(
        [{"texto": item, "hecho": completed} for item in items],
        ensure_ascii=False,
    )


def task(
    *,
    key: str,
    client: str,
    title: str,
    due: str,
    description: str,
    checklist_value: str,
    status: str = "Pendiente",
) -> dict:
    return {
        "id": stable_code("TAR-IIBB-AUD", key),
        "cliente": client,
        "tarea": title,
        "responsable_am": "AM Consultora",
        "prioridad": "Alta",
        "estado": status,
        "fecha_limite": due,
        "descripcion": description,
        "comentarios": "",
        "fecha_carga": TODAY,
        "creado_por": "Alan Moreno",
        "fecha_actualizacion": TODAY,
        "actualizado_por": "Alan Moreno",
        "checklist": checklist_value,
        "avance": 100 if status == "Finalizada" else 0,
        "recurrente": "No",
        "frecuencia": "",
        "intervalo": 1,
        "serie_id": "",
        "ocurrencia": 1,
        "proyecto": "Obligaciones fiscales",
        "origen": "Auditoría fiscal 20/10/2026",
        "id_externo": "",
        "categoria": "Ingresos Brutos",
        "unidad": "AM Consultora",
        "orden_manual": "",
        "archivos_habilitados": "Sí",
        "posicion_manual": "",
    }


def pending_validation(
    client: str,
    cuit: str,
    evidence: str,
    recommendation: str,
) -> dict:
    cuit_text = cuit or "pendiente"
    return task(
        key=f"validar-regimen:{client.casefold()}",
        client=client,
        title=f"Ingresos Brutos — validar alta y régimen — {client}",
        due="2026-10-20",
        description=(
            f"Control urgente del anticipo 09/2026. CUIT: {cuit_text}. "
            f"Evidencia revisada: {evidence} "
            f"Criterio preliminar: {recommendation} "
            "No liquidar como Local ni Convenio hasta adjuntar la constancia "
            "de IIBB o confirmar el alta en Padrón Federal/AGIP. Si el alta ya "
            "estaba vigente en septiembre, presentar fuera de término y revisar "
            "intereses; si no estaba vigente, completar la inscripción desde la "
            "fecha real de inicio de actividad."
        ),
        checklist_value=checklist(
            "Descargar y adjuntar constancia de IIBB vigente",
            "Confirmar fecha de alta, jurisdicción sede y actividades",
            "Definir Local CABA o Convenio Multilateral",
            "Revisar anticipo 09/2026 y deuda/intereses si corresponde",
            "Convertir este control en recurrencia mensual con vencimiento correcto",
        ),
    )


def build_tasks() -> list[dict]:
    rows = [
        pending_validation(
            "SOLUCIONES GEM SAS",
            "33-71960172-9",
            "no figura en SIRCREB 09/2026 ni 10/2026; domicilio societario CABA y antecedentes operativos en Mendoza.",
            "evaluar Convenio si existe actividad efectiva en más de una jurisdicción; de lo contrario, Local CABA.",
        ),
        pending_validation(
            "EXPRESO RDA SAS",
            "30-71961601-8",
            "no figura en SIRCREB 09/2026 ni 10/2026; constitución publicada el 25/09/2026, sede CABA y operación vinculada con PBA.",
            "Convenio es probable por la actividad de transporte interjurisdiccional, pero requiere alta/constancia.",
        ),
        pending_validation(
            "PP&L GROUP SAS",
            "30-71962593-9",
            "no figura en SIRCREB 09/2026 ni 10/2026; sede societaria CABA.",
            "Local CABA si el establecimiento y las ventas operan solo en CABA; Convenio si hay sustento territorial en PBA u otra jurisdicción.",
        ),
        pending_validation(
            "RED MANOS UNIDAS 77 SAS",
            "33-71960169-9",
            "no figura en SIRCREB 09/2026 ni 10/2026; ARCA la informa activa, con domicilio fiscal CABA.",
            "Local CABA es el escenario preliminar si toda la actividad se desarrolla allí, sujeto a constancia.",
        ),
        pending_validation(
            "GSG LOGISTIC SAS",
            "",
            "constitución publicada en el Boletín Oficial el 07/10/2026; no se encontró CUIT societario publicado ni constancia fiscal.",
            "Convenio es probable por logística/transporte entre CABA y PBA, pero primero debe obtenerse CUIT y alta fiscal.",
        ),
        pending_validation(
            "GRUPO CEDE SAS",
            "",
            "existe instrumento constitutivo local, pero no se encontró publicación ni CUIT societario verificable al 20/10/2026.",
            "definir según jurisdicciones reales una vez inscripta y con CUIT.",
        ),
        pending_validation(
            "AVBC COMERCIALIZADORA AGRÍCOLA SAS",
            "",
            "existe instrumento constitutivo local, pero no se encontró publicación ni CUIT societario verificable al 20/10/2026.",
            "evaluar Convenio si comercializa u opera fuera de CABA; requiere inscripción y constancia.",
        ),
        task(
            key="cerrado:smpa:2026-09",
            client="SMPA / KM146",
            title="Ingresos Brutos — SMPA SAS — septiembre 2026",
            due="2026-10-20",
            status="Finalizada",
            description=(
                "Período marcado como liquidado por Alan. El CUIT 30-71524512-0 "
                "usado en la facturación debe revisarse antes de crear la próxima "
                "recurrencia: la consulta oficial SIRCREB lo devuelve asociado a "
                "otra razón social."
            ),
            checklist_value=checklist(
                "Liquidación informada como realizada",
                completed=True,
            ),
        ),
        task(
            key="cerrado:km146:2026-09",
            client="SMPA / KM146",
            title="Ingresos Brutos — KM146 SAS — septiembre 2026",
            due="2026-10-20",
            status="Finalizada",
            description=(
                "Período marcado como liquidado por Alan. CUIT 30-71958879-0. "
                "No figura en SIRCREB 09/2026 ni 10/2026; adjuntar la constancia "
                "utilizada en la liquidación antes de generar la recurrencia."
            ),
            checklist_value=checklist(
                "Liquidación informada como realizada",
                completed=True,
            ),
        ),
    ]
    return rows


def client_rows() -> list[dict]:
    names = [
        "SOLUCIONES GEM SAS",
        "EXPRESO RDA SAS",
        "GSG LOGISTIC SAS",
        "PP&L GROUP SAS",
        "RED MANOS UNIDAS 77 SAS",
        "GRUPO CEDE SAS",
        "AVBC COMERCIALIZADORA AGRÍCOLA SAS",
    ]
    return [
        {
            "cliente": name,
            "rubro": "Sociedad en alta fiscal",
            "estado": "Activo",
            "plan": "Impuestos y contabilidad",
            "responsable_am": "AM Consultora",
            "fecha_inicio": "2026-10-01",
            "servicio_digital": "No",
            "servicio_consultoria": "No",
            "servicio_contabilidad": "Sí",
            "notas": (
                "Alta preliminar para seguimiento fiscal. Completar onboarding, "
                "CUIT, constancia ARCA y constancia de IIBB."
            ),
        }
        for name in names
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", default=str(ROOT / "backups_locales"))
    args = parser.parse_args()

    rows = build_tasks()
    clients = client_rows()
    print(f"Tareas preparadas: {len(rows)}")
    for row in rows:
        print(row["fecha_limite"], row["estado"], row["tarea"])
    if not args.apply:
        return

    # Producción usa un pooler de PostgreSQL; desactivar prepared statements
    # evita colisiones de nombres cuando el pool reutiliza conexiones.
    engine = create_engine(
        database_url(),
        connect_args={"prepare_threshold": None},
    )
    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with engine.connect() as conn:
        current_tasks = pd.read_sql(text('SELECT * FROM "tareas"'), conn)
        current_clients = pd.read_sql(text('SELECT * FROM "clientes"'), conn)
    tasks_backup = backup_dir / f"tareas_antes_iibb_sas_{timestamp}.csv"
    clients_backup = backup_dir / f"clientes_antes_iibb_sas_{timestamp}.csv"
    current_tasks.to_csv(tasks_backup, index=False)
    current_clients.to_csv(clients_backup, index=False)

    inserted_tasks: list[str] = []
    skipped_tasks: list[str] = []
    inserted_clients: list[str] = []
    with engine.begin() as conn:
        for client in clients:
            exists = conn.execute(
                text('SELECT 1 FROM "clientes" WHERE lower("cliente") = lower(:cliente) LIMIT 1'),
                {"cliente": client["cliente"]},
            ).first()
            if exists:
                continue
            columns = list(client)
            conn.execute(
                text(
                    'INSERT INTO "clientes" ('
                    + ", ".join(f'"{column}"' for column in columns)
                    + ") VALUES ("
                    + ", ".join(f":{column}" for column in columns)
                    + ")"
                ),
                client,
            )
            inserted_clients.append(client["cliente"])

        for row in rows:
            exists = conn.execute(
                text('SELECT 1 FROM "tareas" WHERE "id" = :id LIMIT 1'),
                {"id": row["id"]},
            ).first()
            if exists:
                skipped_tasks.append(row["tarea"])
                continue
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
            inserted_tasks.append(row["tarea"])

        conn.execute(
            text(
                'UPDATE "tareas" SET "descripcion" = :descripcion, '
                '"fecha_actualizacion" = :fecha, "actualizado_por" = :usuario '
                'WHERE "id" = :id'
            ),
            {
                "id": "TAR-FISC-c9fd4931d4a3ddf15849",
                "descripcion": (
                    "Seguimiento reemplazado por tarjetas individuales de IIBB. "
                    "No cerrar hasta adjuntar las constancias y convertir cada "
                    "control validado en recurrencia mensual."
                ),
                "fecha": TODAY,
                "usuario": "Alan Moreno",
            },
        )

    print(f"Backups: {tasks_backup} | {clients_backup}")
    print(f"Clientes insertados: {len(inserted_clients)}")
    print(f"Tareas insertadas: {len(inserted_tasks)}")
    print(f"Tareas omitidas por existir: {len(skipped_tasks)}")


if __name__ == "__main__":
    main()
