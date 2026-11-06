#!/usr/bin/env python3
"""Ordena las obligaciones de noviembre 2026 de sociedades confirmadas.

La ejecución es idempotente: reutiliza la tarjeta activa del impuesto y convierte
los controles preliminares en recurrencias fiscales, sin crear duplicados.
También retira el alta errónea de Cooperativa de Trabajo Villa Adelina, con un
backup completo y conservando COOPERATIVA INSTITUTO BUENOS AIRES.
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
COOPERATIVA_A_RETIRAR = "Cooperativa de Trabajo Villa Adelina"


SOCIEDADES = {
    "HYDROTEK SRL": {
        "cuit": "30-71896489-6",
        "iibb_regimen": "Convenio Multilateral",
        "iibb_jurisdiccion": "",
        "iva_due": "2026-11-24",
        "iibb_due": "2026-11-19",
        "iibb_obligacion": "CM03",
        "iibb_jurisdiccion_meta": "COMARB",
    },
    "GSG LOGISTIC SAS": {
        "cuit": "30-71963386-9",
        "iibb_regimen": "Convenio Multilateral",
        "iibb_jurisdiccion": "",
        "iva_due": "2026-11-25",
        "iibb_due": "2026-11-20",
        "iibb_obligacion": "CM03",
        "iibb_jurisdiccion_meta": "COMARB",
    },
    "PP&L GROUP SAS": {
        "cuit": "30-71962593-9",
        "iibb_regimen": "Local",
        "iibb_jurisdiccion": "AGIP - CABA",
        "iva_due": "2026-11-25",
        "iibb_due": "2026-11-17",
        "iibb_obligacion": "MENSUAL",
        "iibb_jurisdiccion_meta": "CABA",
    },
    "RED MANOS UNIDAS 77 SAS": {
        "cuit": "33-71960169-9",
        "iibb_regimen": "Convenio Multilateral",
        "iibb_jurisdiccion": "",
        "iva_due": "2026-11-25",
        "iibb_due": "2026-11-20",
        "iibb_obligacion": "CM03",
        "iibb_jurisdiccion_meta": "COMARB",
    },
    "SOLUCIONES GEM SAS": {
        "cuit": "33-71960172-9",
        "iibb_regimen": "Convenio Multilateral",
        "iibb_jurisdiccion": "",
        "iva_due": "2026-11-25",
        "iibb_due": "2026-11-20",
        "iibb_obligacion": "CM03",
        "iibb_jurisdiccion_meta": "COMARB",
    },
}


def database_url() -> str:
    secrets = toml.loads((ROOT / ".streamlit" / "secrets.toml").read_text())
    url = str(secrets["DATABASE_URL"])
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def stable_code(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def checklist(category: str) -> str:
    items = (
        [
            "Cargar compras, ventas, retenciones y percepciones",
            "Preparar y revisar papel de trabajo",
            "Contrastar con Portal IVA y presentar",
            "Registrar resultado, pago y comprobante",
        ]
        if category == "IVA"
        else [
            "Cargar retenciones, percepciones y base imponible",
            "Preparar y revisar papel de trabajo",
            "Contrastar con el organismo y presentar",
            "Registrar resultado, pago y comprobante",
        ]
    )
    return json.dumps(
        [{"texto": item, "hecho": False} for item in items],
        ensure_ascii=False,
    )


def metadata(
    *, category: str, config: dict, due: str, client: str
) -> str:
    if category == "IVA":
        source = "https://seti.afip.gob.ar/av/viewVencimientosSintetica.do"
        jurisdiction = "NACIONAL"
        obligation = "MENSUAL"
    elif config["iibb_obligacion"] == "CM03":
        source = "https://www.ca.gob.ar/descargas/sifere/vencimientos/2026-11.pdf"
        jurisdiction = "COMARB"
        obligation = "CM03"
    else:
        source = (
            "https://documentosboletinoficial.buenosaires.gob.ar/publico/"
            "PE-RES-MHFGC-AGIP-557-25-ANX.pdf"
        )
        jurisdiction = "CABA"
        obligation = "MENSUAL"

    payload = {
        "estado": "verificado",
        "fuente": source,
        "impuesto": "IVA" if category == "IVA" else "IIBB",
        "jurisdiccion": jurisdiction,
        "motivo": "",
        "obligacion": obligation,
        "periodo": "2026-10",
        "periodo_fuente": (
            "Obligación y régimen confirmados expresamente por Alan el "
            f"05/11/2026 para {client}; vencimiento de noviembre tomado del "
            "calendario fiscal incorporado a AM HUB."
        ),
        "terminacion": int(config["cuit"].replace("-", "")[-1]),
        "verificado_el": TODAY,
        "vencimiento": due,
    }
    return "fiscal:v1:" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def description(client: str, category: str, config: dict) -> str:
    cuit = config["cuit"]
    if category == "IVA":
        extra = ""
        if client == "GSG LOGISTIC SAS":
            extra = (
                " La ficha conserva una constancia anterior con IVA Exento desde "
                "10/2026; la tarjeta se incorpora por indicación expresa de Alan y "
                "debe contrastarse con la situación registral vigente al liquidar."
            )
        return (
            f"Liquidación mensual de IVA. CUIT: {cuit}. Período fiscal: "
            f"octubre 2026.{extra}"
        )
    return (
        "Liquidación mensual de Ingresos Brutos. "
        f"CUIT: {cuit}. Régimen: {config['iibb_regimen']}. "
        "Período fiscal: octubre 2026."
    )


def task_values(client: str, category: str, config: dict) -> dict:
    due = config["iva_due"] if category == "IVA" else config["iibb_due"]
    key = f"{category}:{client}"
    return {
        "id": stable_code("TAR-NOV26", key),
        "cliente": client,
        "tarea": f"{category} — {client}",
        "responsable_am": "AM Consultora",
        "prioridad": "Alta",
        "estado": "Pendiente",
        "fecha_limite": due,
        "descripcion": description(client, category, config),
        "comentarios": "",
        "fecha_carga": TODAY,
        "creado_por": "Alan Moreno",
        "fecha_actualizacion": TODAY,
        "actualizado_por": "Alan Moreno",
        "checklist": checklist(category),
        "avance": 0,
        "recurrente": "Sí",
        "frecuencia": "Mensual",
        "intervalo": 1,
        "serie_id": stable_code("SER-NOV26", key),
        "ocurrencia": 1,
        "proyecto": "Obligaciones fiscales",
        "origen": "Confirmación fiscal AM HUB 05/11/2026",
        "id_externo": metadata(
            category=category,
            config=config,
            due=due,
            client=client,
        ),
        "categoria": category,
        "unidad": "AM Consultora",
        "orden_manual": "",
        "archivos_habilitados": "No",
        "posicion_manual": "",
    }


def active_task(conn, client: str, category: str):
    return conn.execute(
        text(
            'SELECT * FROM "tareas" WHERE lower("cliente")=lower(:client) '
            'AND lower(coalesce("estado", \'\')) <> \'finalizada\' AND ('
            'lower(coalesce("categoria", \'\'))=lower(:category) OR '
            'lower(coalesce("tarea", \'\')) LIKE lower(:title_pattern)) '
            'ORDER BY CASE WHEN lower(coalesce("categoria", \'\'))=lower(:category) '
            'THEN 0 ELSE 1 END, "fecha_limite" DESC LIMIT 1'
        ),
        {
            "client": client,
            "category": category,
            "title_pattern": f"{category}%",
        },
    ).mappings().first()


def upsert_task(conn, row: dict) -> tuple[str, str]:
    current = active_task(conn, row["cliente"], row["categoria"])
    if current:
        task_id = current["id"]
        series_id = str(current.get("serie_id", "") or row["serie_id"])
        conn.execute(
            text(
                'UPDATE "tareas" SET "tarea"=:tarea, "responsable_am"=:responsable_am, '
                '"prioridad"=:prioridad, "estado"=:estado, "fecha_limite"=:fecha_limite, '
                '"descripcion"=:descripcion, "checklist"=:checklist, "avance"=0, '
                '"recurrente"=\'Sí\', "frecuencia"=\'Mensual\', "intervalo"=1, '
                '"serie_id"=:series_id, "ocurrencia"=:ocurrencia, '
                '"proyecto"=:proyecto, "origen"=:origen, "id_externo"=:id_externo, '
                '"categoria"=:categoria, "unidad"=:unidad, '
                '"fecha_actualizacion"=:fecha_actualizacion, '
                '"actualizado_por"=:actualizado_por WHERE "id"=:task_id'
            ),
            {**row, "series_id": series_id, "task_id": task_id},
        )
        return "actualizada", task_id

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
    return "insertada", row["id"]


def append_note(existing: str, note: str) -> str:
    existing = str(existing or "").strip()
    if note in existing:
        return existing
    return (existing + "\n" + note).strip()


def backup_and_delete_cooperativa(engine, backup_dir: Path) -> dict:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = backup_dir / f"cooperativa_villa_adelina_{timestamp}"
    destination.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    client_tables = [
        "asignaciones_equipo",
        "clientes",
        "contable_cuentas",
        "fiscal_clientes",
        "objetivos",
        "tareas",
        "usuarios",
    ]
    with engine.connect() as conn:
        task_ids = conn.execute(
            text('SELECT "id" FROM "tareas" WHERE "cliente"=:client'),
            {"client": COOPERATIVA_A_RETIRAR},
        ).scalars().all()
        objective_ids = conn.execute(
            text('SELECT "id" FROM "objetivos" WHERE "cliente"=:client'),
            {"client": COOPERATIVA_A_RETIRAR},
        ).scalars().all()
        linked_ids = task_ids + objective_ids
        for table in client_tables:
            frame = pd.read_sql(
                text(f'SELECT * FROM "{table}" WHERE "cliente"=:client'),
                conn,
                params={"client": COOPERATIVA_A_RETIRAR},
            )
            counts[table] = len(frame)
            if not frame.empty:
                frame.to_csv(destination / f"{table}.csv", index=False)
        attachments = pd.DataFrame()
        if linked_ids:
            attachments = pd.read_sql(
                text('SELECT * FROM "tarea_archivos" WHERE "tarea_id"=ANY(:ids)'),
                conn,
                params={"ids": linked_ids},
            )
        counts["tarea_archivos"] = len(attachments)
        if not attachments.empty:
            attachments.to_csv(destination / "tarea_archivos.csv", index=False)

    with engine.begin() as conn:
        if linked_ids:
            conn.execute(
                text('DELETE FROM "tarea_archivos" WHERE "tarea_id"=ANY(:ids)'),
                {"ids": linked_ids},
            )
        for table in client_tables:
            conn.execute(
                text(f'DELETE FROM "{table}" WHERE "cliente"=:client'),
                {"client": COOPERATIVA_A_RETIRAR},
            )
    counts["backup"] = str(destination)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--backup-dir",
        default=str(ROOT / "backups_locales"),
    )
    args = parser.parse_args()

    rows = [
        task_values(client, category, config)
        for client, config in SOCIEDADES.items()
        for category in ("IVA", "Ingresos Brutos")
    ]
    for row in rows:
        print(row["fecha_limite"], row["tarea"])
    print("Retirar:", COOPERATIVA_A_RETIRAR)
    if not args.apply:
        return

    engine = create_engine(
        database_url(),
        connect_args={"prepare_threshold": None},
    )
    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with engine.connect() as conn:
        pd.read_sql(text('SELECT * FROM "tareas"'), conn).to_csv(
            backup_dir / f"tareas_antes_sociedades_noviembre_{timestamp}.csv",
            index=False,
        )
        pd.read_sql(text('SELECT * FROM "fiscal_clientes"'), conn).to_csv(
            backup_dir / f"fiscal_clientes_antes_sociedades_noviembre_{timestamp}.csv",
            index=False,
        )

    results = []
    with engine.begin() as conn:
        for client, config in SOCIEDADES.items():
            profile = conn.execute(
                text(
                    'SELECT "observaciones" FROM "fiscal_clientes" '
                    'WHERE lower("cliente")=lower(:client) LIMIT 1'
                ),
                {"client": client},
            ).mappings().first()
            if not profile:
                raise RuntimeError(f"No existe ficha fiscal para {client}")
            note = (
                "Confirmación operativa de Alan 05/11/2026: "
                f"IIBB {config['iibb_regimen']}; se activa la recurrencia del "
                "período octubre con vencimiento en noviembre."
            )
            conn.execute(
                text(
                    'UPDATE "fiscal_clientes" SET "cuit"=:cuit, '
                    '"iibb_regimen"=:regime, "iibb_jurisdiccion"=:jurisdiction, '
                    '"observaciones"=:notes, "fecha_actualizacion"=:today, '
                    '"actualizado_por"=\'Alan Moreno\' '
                    'WHERE lower("cliente")=lower(:client)'
                ),
                {
                    "client": client,
                    "cuit": config["cuit"],
                    "regime": config["iibb_regimen"],
                    "jurisdiction": config["iibb_jurisdiccion"],
                    "notes": append_note(profile["observaciones"], note),
                    "today": TODAY,
                },
            )
        for row in rows:
            action, task_id = upsert_task(conn, row)
            results.append((action, row["tarea"], row["fecha_limite"], task_id))

    deletion = backup_and_delete_cooperativa(engine, backup_dir)
    for result in results:
        print(*result)
    print("Eliminación Cooperativa:", json.dumps(deletion, ensure_ascii=False))


if __name__ == "__main__":
    main()
