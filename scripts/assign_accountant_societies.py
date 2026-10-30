#!/usr/bin/env python3
"""Asigna al contador las sociedades confirmadas y completa su ficha fiscal.

El script es idempotente. Por defecto solo muestra el alcance; ``--apply``
persiste los clientes faltantes, las fichas conocidas y las asignaciones.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import sys

from sqlalchemy import create_engine, text
import toml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from am_hub_accounting import CUENTA_COLUMNAS, plan_cuentas_inicial


USERNAME = "contador.am"
UPDATED_BY = "Codex / Alan Moreno"
PILOT_CLIENTS = ["DEMO — Contabilidad"]


def database_url() -> str:
    secrets = toml.loads((ROOT / ".streamlit" / "secrets.toml").read_text())
    url = str(secrets["DATABASE_URL"])
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


SOCIETIES = [
    {
        "cliente": "Cooperativa de Trabajo Villa Adelina",
        "razon_social": "COOPERATIVA 3C3T",
        "cuit": "30-71811233-4",
        "condicion_iva": "Responsable inscripto",
        "iibb_regimen": "Convenio Multilateral",
        "iibb_jurisdiccion": "",
        "email_destinatarios": "",
        "observaciones": "En facturación se identifica como Cooperativa 3C3T.",
    },
    {
        "cliente": "COOPERATIVA INSTITUTO BUENOS AIRES",
        "razon_social": "COOPERATIVA DE SERVICIOS PARA DOCENTES INSTITUTO BUENOS AIRES",
        "cuit": "33-58243684-9",
        "condicion_iva": "Responsable inscripto",
        "iibb_regimen": "",
        "iibb_jurisdiccion": "",
        "email_destinatarios": "",
        "observaciones": (
            "En facturación se identifica como Instituto Buenos Aires. "
            "Régimen y jurisdicción de IIBB pendientes de validar con constancia."
        ),
    },
    {
        "cliente": "EXPRESO RDA SAS",
        "razon_social": "EXPRESO RDA SAS",
        "cuit": "30-71961601-8",
        "condicion_iva": "Responsable inscripto",
        "iibb_regimen": "Convenio Multilateral",
        "iibb_jurisdiccion": "",
        "email_destinatarios": "Ileanaaraujo0@gmail.com",
        "observaciones": "Alta impositiva confirmada desde octubre de 2026.",
    },
    {
        "cliente": "GSG LOGISTIC SAS",
        "razon_social": "GSG LOGISTIC SAS",
        "cuit": "",
        "condicion_iva": "Responsable inscripto",
        "iibb_regimen": "Local",
        "iibb_jurisdiccion": "AGIP - CABA",
        "email_destinatarios": "escobedogus64gust64@gmail.com",
        "observaciones": "CUIT y constancias fiscales pendientes de carga.",
    },
    {
        "cliente": "HYDROTEK SRL",
        "razon_social": "HYDROTEK SRL",
        "cuit": "30-71896489-6",
        "condicion_iva": "Responsable inscripto",
        "iibb_regimen": "Convenio Multilateral",
        "iibb_jurisdiccion": "",
        "email_destinatarios": "littlejonathan51@gmail.com",
        "observaciones": "",
    },
    {
        "cliente": "PP&L GROUP SAS",
        "razon_social": "PP&L GROUP SAS",
        "cuit": "30-71962593-9",
        "condicion_iva": "Responsable inscripto",
        "iibb_regimen": "",
        "iibb_jurisdiccion": "",
        "email_destinatarios": "Marcelalettini@gmail.com",
        "observaciones": "Régimen de IIBB pendiente de validar con constancia.",
    },
    {
        "cliente": "RED MANOS UNIDAS 77 SAS",
        "razon_social": "RED MANOS UNIDAS 77 SAS",
        "cuit": "33-71960169-9",
        "condicion_iva": "Responsable inscripto",
        "iibb_regimen": "Convenio Multilateral",
        "iibb_jurisdiccion": "",
        "email_destinatarios": "22garcia22adrian@gmail.com",
        "observaciones": "",
    },
    {
        "cliente": "SMPA SAS",
        "razon_social": "SMPA SAS",
        "cuit": "",
        "condicion_iva": "Exento",
        "iibb_regimen": "Convenio Multilateral",
        "iibb_jurisdiccion": "",
        "email_destinatarios": "sabrina.aristegui.1980@gmail.com; mperadotto@gmail.com",
        "observaciones": (
            "CUIT pendiente de validar. El 30-71524512-0 informado previamente "
            "fue marcado como inconsistente y no debe utilizarse sin constancia."
        ),
    },
    {
        "cliente": "KM146 SAS",
        "razon_social": "KM146 SAS",
        "cuit": "30-71958879-0",
        "condicion_iva": "Responsable inscripto",
        "iibb_regimen": "Convenio Multilateral",
        "iibb_jurisdiccion": "",
        "email_destinatarios": "",
        "observaciones": "Adjuntar constancias fiscal y de IIBB utilizadas en la liquidación.",
    },
    {
        "cliente": "CASA DESER SRL",
        "razon_social": "CASA DESER S.R.L.",
        "cuit": "30-71893522-5",
        "condicion_iva": "Responsable inscripto",
        "iibb_regimen": "Local",
        "iibb_jurisdiccion": "AGIP - CABA",
        "email_destinatarios": "casadesersrl@gmail.com",
        "observaciones": "",
    },
    {
        "cliente": "SOLUCIONES GEM SAS",
        "razon_social": "SOLUCIONES GEM SAS",
        "cuit": "33-71960172-9",
        "condicion_iva": "Responsable inscripto",
        "iibb_regimen": "Local",
        "iibb_jurisdiccion": "AGIP - CABA",
        "email_destinatarios": "exerivas15@gmail.com",
        "observaciones": "",
    },
    {
        "cliente": "GRUPO CEDE SAS",
        "razon_social": "GRUPO CEDE SAS",
        "cuit": "",
        "condicion_iva": "Responsable inscripto",
        "iibb_regimen": "Local",
        "iibb_jurisdiccion": "AGIP - CABA",
        "email_destinatarios": "",
        "observaciones": "CUIT y constancias fiscales pendientes de carga.",
    },
    {
        "cliente": "AVBC COMERCIALIZADORA AGRÍCOLA SAS",
        "razon_social": "AVBC COMERCIALIZADORA AGRÍCOLA SAS",
        "cuit": "",
        "condicion_iva": "Responsable inscripto",
        "iibb_regimen": "Local",
        "iibb_jurisdiccion": "AGIP - CABA",
        "email_destinatarios": "",
        "observaciones": "CUIT y constancias fiscales pendientes de carga.",
    },
    {
        "cliente": "COLEGIO SAN ANTONIO EDUCA SRL",
        "razon_social": "COLEGIO SAN ANTONIO EDUCA SRL",
        "cuit": "33-54009213-9",
        "condicion_iva": "Responsable inscripto",
        "iibb_regimen": "Local",
        "iibb_jurisdiccion": "ARBA - Buenos Aires",
        "email_destinatarios": "",
        "observaciones": "En facturación se identifica como Colegio San Antonio.",
    },
]


def ensure_client(conn, row: dict[str, str]) -> None:
    existing = conn.execute(
        text('SELECT 1 FROM "clientes" WHERE lower("cliente")=lower(:cliente)'),
        row,
    ).first()
    if existing:
        conn.execute(
            text(
                'UPDATE "clientes" SET "estado"=\'Activo\', '
                '"servicio_contabilidad"=\'Sí\' '
                'WHERE lower("cliente")=lower(:cliente)'
            ),
            row,
        )
        return

    conn.execute(
        text(
            'INSERT INTO "clientes" ('
            '"cliente", "rubro", "estado", "plan", "responsable_am", '
            '"fecha_inicio", "servicio_digital", "servicio_consultoria", '
            '"servicio_contabilidad", "notas"'
            ') VALUES ('
            ':cliente, \'Sociedad\', \'Activo\', \'Impuestos y contabilidad\', '
            '\'AM Consultora\', \'2026-10-01\', \'No\', \'No\', \'Sí\', '
            '\'Ficha creada para gestión contable y fiscal.\''
            ')'
        ),
        row,
    )


def upsert_fiscal_profile(conn, row: dict[str, str]) -> None:
    existing = conn.execute(
        text(
            'SELECT "id" FROM "fiscal_clientes" '
            'WHERE lower("cliente")=lower(:cliente) LIMIT 1'
        ),
        row,
    ).mappings().first()
    values = {
        **row,
        "id": stable_id("FCLI", row["cliente"]),
        "fecha_actualizacion": datetime.now().astimezone().isoformat(),
        "actualizado_por": UPDATED_BY,
    }
    if not existing:
        conn.execute(
            text(
                'INSERT INTO "fiscal_clientes" ('
                '"id", "cliente", "cuit", "razon_social", "condicion_iva", '
                '"iibb_regimen", "iibb_jurisdiccion", "iibb_inscripcion", '
                '"actividad_principal", "actividades", "alicuota_iibb", '
                '"email_destinatarios", "observaciones", "fecha_actualizacion", '
                '"actualizado_por", "mes_cierre_ejercicio"'
                ') VALUES ('
                ':id, :cliente, :cuit, :razon_social, :condicion_iva, '
                ':iibb_regimen, :iibb_jurisdiccion, \'\', \'\', \'\', \'\', '
                ':email_destinatarios, :observaciones, :fecha_actualizacion, '
                ':actualizado_por, \'12\''
                ')'
            ),
            values,
        )
        return

    # Completa datos conocidos sin borrar campos más precisos cargados antes.
    values["existing_id"] = existing["id"]
    conn.execute(
        text(
            'UPDATE "fiscal_clientes" SET '
            '"cuit"=COALESCE(NULLIF("cuit", \'\'), :cuit), '
            '"razon_social"=COALESCE(NULLIF("razon_social", \'\'), :razon_social), '
            '"condicion_iva"=COALESCE(NULLIF("condicion_iva", \'\'), :condicion_iva), '
            '"iibb_regimen"=COALESCE(NULLIF("iibb_regimen", \'\'), :iibb_regimen), '
            '"iibb_jurisdiccion"=COALESCE(NULLIF("iibb_jurisdiccion", \'\'), :iibb_jurisdiccion), '
            '"email_destinatarios"=COALESCE(NULLIF("email_destinatarios", \'\'), :email_destinatarios), '
            '"observaciones"=CASE WHEN COALESCE("observaciones", \'\')=\'\' '
            'THEN :observaciones ELSE "observaciones" END, '
            '"mes_cierre_ejercicio"=COALESCE(NULLIF("mes_cierre_ejercicio", \'\'), \'12\'), '
            '"fecha_actualizacion"=:fecha_actualizacion, '
            '"actualizado_por"=:actualizado_por '
            'WHERE "id"=:existing_id'
        ),
        values,
    )


def replace_assignments(conn) -> None:
    conn.execute(
        text(
            'UPDATE "asignaciones_equipo" SET "activo"=\'No\' '
            'WHERE lower("username")=lower(:username)'
        ),
        {"username": USERNAME},
    )
    assigned_clients = [row["cliente"] for row in SOCIETIES] + PILOT_CLIENTS
    for client in assigned_clients:
        values = {
            "id": stable_id("ASG", f"{USERNAME}:{client}"),
            "username": USERNAME,
            "cliente": client,
        }
        existing = conn.execute(
            text(
                'SELECT "id" FROM "asignaciones_equipo" '
                'WHERE lower("username")=lower(:username) '
                'AND lower("cliente")=lower(:cliente) LIMIT 1'
            ),
            values,
        ).mappings().first()
        if existing:
            conn.execute(
                text(
                    'UPDATE "asignaciones_equipo" SET "activo"=\'Sí\' '
                    'WHERE "id"=:existing_id'
                ),
                {"existing_id": existing["id"]},
            )
        else:
            conn.execute(
                text(
                    'INSERT INTO "asignaciones_equipo" '
                    '("id", "username", "cliente", "activo") '
                    'VALUES (:id, :username, :cliente, \'Sí\')'
                ),
                values,
            )


def split_smpa_km146_tasks(conn) -> None:
    """Separa las obligaciones fiscales sin tocar el módulo de flota compartido."""
    conn.execute(
        text(
            'UPDATE "tareas" SET "cliente"=\'KM146 SAS\' '
            'WHERE lower("cliente")=\'smpa / km146\' '
            'AND lower("tarea") LIKE \'%km146%\''
        )
    )
    conn.execute(
        text(
            'UPDATE "tareas" SET "cliente"=\'SMPA SAS\' '
            'WHERE lower("cliente")=\'smpa / km146\' '
            'AND (lower("tarea") LIKE \'%smpa%\' '
            'OR lower("tarea") LIKE \'%marcos%\')'
        )
    )


def ensure_base_chart_of_accounts(conn, client: str) -> None:
    exists = conn.execute(
        text(
            'SELECT 1 FROM "contable_cuentas" '
            'WHERE lower("cliente")=lower(:cliente) LIMIT 1'
        ),
        {"cliente": client},
    ).first()
    if exists:
        return
    rows = plan_cuentas_inicial(client, USERNAME).to_dict("records")
    conn.execute(
        text(
            'INSERT INTO "contable_cuentas" ('
            + ", ".join(f'"{column}"' for column in CUENTA_COLUMNAS)
            + ") VALUES ("
            + ", ".join(f":{column}" for column in CUENTA_COLUMNAS)
            + ")"
        ),
        rows,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    print(f"Usuario: {USERNAME}")
    print(f"Sociedades: {len(SOCIETIES)}")
    for row in SOCIETIES:
        print(f"- {row['cliente']} | CUIT {row['cuit'] or 'pendiente'}")
    for client in PILOT_CLIENTS:
        print(f"- {client} | entorno de prueba")
    if not args.apply:
        print("Vista previa: ejecute con --apply para persistir.")
        return

    engine = create_engine(
        database_url(),
        pool_pre_ping=True,
        connect_args={"prepare_threshold": None},
    )
    with engine.begin() as conn:
        user = conn.execute(
            text(
                'SELECT 1 FROM "usuarios" WHERE lower("username")=lower(:username) '
                'AND lower("role")=\'contador\' AND lower("activo") IN '
                '(\'sí\', \'si\', \'true\', \'1\', \'activo\')'
            ),
            {"username": USERNAME},
        ).first()
        if not user:
            raise RuntimeError(f"No existe un contador activo: {USERNAME}")
        for row in SOCIETIES:
            ensure_client(conn, row)
            upsert_fiscal_profile(conn, row)
            ensure_base_chart_of_accounts(conn, row["cliente"])
        replace_assignments(conn)
        split_smpa_km146_tasks(conn)
    print("Sincronización completada.")


if __name__ == "__main__":
    main()
