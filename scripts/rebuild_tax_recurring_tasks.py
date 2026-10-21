#!/usr/bin/env python3
"""Reconstruye series fiscales confirmadas sin duplicar tareas activas."""

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


def checklist(*items: str) -> str:
    return json.dumps(
        [{"texto": item, "hecho": False} for item in items],
        ensure_ascii=False,
    )


def task(
    *,
    key: str,
    client: str,
    title: str,
    category: str,
    due: str,
    description: str,
    checklist_value: str,
    recurring: bool = True,
    project: str = "Obligaciones fiscales",
) -> dict:
    series_id = stable_code("SER-FISC", key) if recurring else ""
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
        "checklist": checklist_value,
        "avance": 0,
        "recurrente": "Sí" if recurring else "No",
        "frecuencia": "Mensual" if recurring else "",
        "intervalo": 1,
        "serie_id": series_id,
        "ocurrencia": 1,
        "proyecto": project,
        "origen": "Reconstrucción fiscal AM HUB",
        "id_externo": "",
        "categoria": category,
        "unidad": "AM Consultora",
        "orden_manual": "",
        "archivos_habilitados": "No",
        "posicion_manual": "",
    }


def build_tasks() -> list[dict]:
    rows: list[dict] = []

    autonomos = [
        ("Luciano Arleo", "Luciano Arleo"),
        ("Ian Cittadini", "Ian Cittadini"),
        ("Vero Villalobo Mallo", "Vero Villalobo Mallo"),
        ("Online Mami", "Agustina Cabaleiro"),
        ("Barbie Villalobo Mallo", "Barbie Villalobo Mallo"),
        ("Gus Villalobo Mallo", "Gus Villalobo Mallo"),
        ("Nico SAS", "Nico SAS"),
        ("HYDROTEK SRL", "Jhony Hydrotek"),
        ("Matías Ojeda", "Matías Ojeda"),
        ("Verónica Martínez", "Verónica Martínez"),
        ("Socios SAS", "Socios SAS"),
        ("SMPA / KM146", "Marcos — SMPA SAS"),
    ]
    autonomos_cuits = {
        "Matías Ojeda": "20-35656955-6",
        "Verónica Martínez": "27-36806250-8",
    }
    for client, taxpayer in autonomos:
        cuit = autonomos_cuits.get(taxpayer, "")
        cuit_note = f" CUIT: {cuit}." if cuit else ""
        rows.append(
            task(
                key=f"autonomos:{taxpayer.lower()}",
                client=client,
                title=f"Autónomos — {taxpayer}",
                category="Autónomos",
                due="2026-10-05",
                description=(
                    "Control mensual del pago de Autónomos. La fecha reconstruye "
                    "el período octubre de la serie anterior. Completar el CUIT en "
                    "la ficha fiscal para ajustar automáticamente el día exacto."
                    + cuit_note
                ),
                checklist_value=checklist(
                    "Verificar deuda y vencimiento según terminación de CUIT",
                    "Preparar o confirmar el pago",
                    "Registrar comprobante y observaciones",
                ),
            )
        )

    monotributo = [
        ("Marlitt Elisa Ordoñez Arteaga", "Marlitt Elisa Ordoñez Arteaga", "27-96043123-0"),
        ("Joaquín Mengide", "Joaquín Mengide", "23-34037156-9"),
        ("Juan Mallo", "Juan Mallo", "20-41824832-8"),
        ("Naomi Kraus Studio", "Nancy", "27-22497248-8"),
        ("Natalia Gena", "Natalia Gena", ""),
        ("Atlantis Cars", "Martín — Atlantis Cars", "20-38201991-2"),
        ("Jose Jaure", "Jose Jaure", "27-42659064-1"),
        ("Atlantis Cars", "Franco — Atlantis Cars", "20-38996614-3"),
        ("Martina Peirano", "Martina Peirano", "27-38992790-8"),
        ("Abril Larreta", "Abril Larreta", "27-44998850-2"),
        ("Leslie Vera", "Leslie Vera", "27-38157776-1"),
        ("Adriana Dominguez", "Adriana Dominguez", "23-14271037-4"),
        ("Mica Verta", "Mica Verta", "27-38657949-6"),
        ("Micaela Alegre", "Micaela Alegre", "27-42315458-1"),
    ]
    for client, taxpayer, cuit in monotributo:
        cuit_note = f" CUIT: {cuit}." if cuit else " CUIT pendiente en ficha fiscal."
        rows.append(
            task(
                key=f"monotributo:{taxpayer.lower()}",
                client=client,
                title=f"Monotributo — {taxpayer}",
                category="Monotributo",
                due="2026-10-20",
                description="Control mensual del pago de Monotributo." + cuit_note,
                checklist_value=checklist(
                    "Verificar deuda y credencial vigente",
                    "Preparar o confirmar el pago",
                    "Registrar comprobante y observaciones",
                ),
            )
        )

    iva = [
        ("CASA DESER SRL", "30-71893522-5", "2026-10-21"),
        ("SOLUCIONES GEM SAS", "33-71960172-9", "2026-10-23"),
        ("EXPRESO RDA SAS", "30-71961601-8", "2026-11-25"),
        ("PP&L GROUP SAS", "30-71962593-9", "2026-10-23"),
        ("RED MANOS UNIDAS 77 SAS", "33-71960169-9", "2026-10-23"),
    ]
    for client, cuit, due in iva:
        if client == "EXPRESO RDA SAS":
            iva_description = (
                f"Liquidación mensual de IVA. CUIT: {cuit}. Primer período: "
                "octubre 2026. Vencimiento oficial para CUIT terminado en 8: "
                "25/11/2026. Septiembre 2026 no corresponde por fecha de alta."
            )
        else:
            iva_description = (
                f"Liquidación mensual de IVA. CUIT: {cuit}. Vencimiento de "
                "octubre 2026 calculado por terminación de CUIT."
            )
        rows.append(
            task(
                key=f"iva:{client.lower()}",
                client=client,
                title=f"IVA — {client}",
                category="IVA",
                due=due,
                description=iva_description,
                checklist_value=checklist(
                    "Cargar compras, ventas, retenciones y percepciones",
                    "Preparar y revisar papel de trabajo",
                    "Contrastar con Portal IVA",
                    "Presentar y registrar resultado",
                ),
            )
        )

    rows.append(
        task(
            key="iibb:casa-deser-srl",
            client="CASA DESER SRL",
            title="Ingresos Brutos — CASA DESER SRL",
            category="Ingresos Brutos",
            due="2026-10-15",
            description=(
                "Liquidación mensual de Ingresos Brutos local AGIP. CUIT: "
                "30-71893522-5. La ficha fiscal confirma régimen Local, CABA."
            ),
            checklist_value=checklist(
                "Cargar retenciones y percepciones",
                "Preparar y revisar papel de trabajo",
                "Contrastar con AGIP",
                "Presentar y registrar resultado",
            ),
        )
    )

    rows.append(
        task(
            key="recordatorio:nuevas-sas-obligaciones",
            client="AM Consultora",
            title="Completar Ganancias, IIBB y Autónomos de socios — nuevas SAS",
            category="Impuestos",
            due="2026-10-23",
            description=(
                "Completar la ficha fiscal de cada sociedad nueva antes de crear "
                "recurrencias que podrían tener régimen, jurisdicción o vencimiento "
                "incorrectos. SMPA figura como Responsable exento y no se le creó "
                "IVA mensual hasta validar el alcance de la exención."
            ),
            checklist_value=checklist(
                "SMPA SAS: validar exención, IIBB, Ganancias y socios",
                "Soluciones GEM SAS: completar IIBB, Ganancias y socios",
                "Expreso RDA SAS: completar IIBB, Ganancias y socios",
                "GSG Logistic SAS: completar CUIT, IVA, IIBB, Ganancias y socios",
                "PP&L Group SAS: completar IIBB, Ganancias y socios",
                "Red Manos Unidas 77 SAS: completar IIBB, Ganancias y socios",
                "Grupo CEDE SAS: completar todos los datos fiscales",
                "AVBC Comercializadora Agrícola SAS: completar CUIT y datos fiscales",
            ),
            recurring=False,
            project="Implementación fiscal",
        )
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", default=str(ROOT / "backups_locales"))
    args = parser.parse_args()

    engine = create_engine(database_url())
    rows = build_tasks()
    print(f"Tareas preparadas: {len(rows)}")
    if not args.apply:
        for row in rows:
            print(row["fecha_limite"], row["categoria"], row["tarea"])
        return

    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with engine.connect() as conn:
        current = pd.read_sql(text('SELECT * FROM "tareas"'), conn)
    backup = backup_dir / f"tareas_antes_reconstruccion_fiscal_{timestamp}.csv"
    current.to_csv(backup, index=False)

    inserted = []
    skipped = []
    with engine.begin() as conn:
        for row in rows:
            existing = conn.execute(
                text('SELECT 1 FROM "tareas" WHERE "id" = :id LIMIT 1'),
                {"id": row["id"]},
            ).first()
            if existing:
                skipped.append(row["tarea"])
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
            inserted.append(row["tarea"])

    print(f"Backup: {backup}")
    print(f"Insertadas: {len(inserted)}")
    for title in inserted:
        print(f"  + {title}")
    print(f"Omitidas por existir: {len(skipped)}")
    for title in skipped:
        print(f"  = {title}")


if __name__ == "__main__":
    main()
