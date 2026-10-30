#!/usr/bin/env python3
"""Deja una empresa modelo contable lista para una prueba integral.

Es idempotente y sólo modifica registros con prefijo DEMO-PILOT dentro de
DEMO — Contabilidad. No toca datos de clientes reales.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys

import pandas as pd
from sqlalchemy import create_engine, inspect, text
import toml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from am_hub_accounting import (  # noqa: E402
    generar_asiento_operacion,
    generar_asientos_comprobantes,
    generar_asientos_impuestos,
)


CLIENTE = "DEMO — Contabilidad"
PERIODO = "2026-10"
PERIODO_ID = "DEMO-ACC-FPER-2026-10"
USUARIO = "AM Consultora"


def database_url() -> str:
    url = str(toml.loads((ROOT / ".streamlit" / "secrets.toml").read_text())["DATABASE_URL"])
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def upsert(conn, table: str, row: dict) -> None:
    columnas_tabla = {c["name"] for c in inspect(conn).get_columns(table)}
    row = {k: v for k, v in row.items() if k in columnas_tabla}
    columnas = list(row)
    actualizaciones = [c for c in columnas if c != "id"]
    sentencia = text(
        f'INSERT INTO "{table}" ('
        + ", ".join(f'"{c}"' for c in columnas)
        + ") VALUES ("
        + ", ".join(f":{c}" for c in columnas)
        + ') ON CONFLICT ("id") DO UPDATE SET '
        + ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in actualizaciones)
    )
    conn.execute(sentencia, row)


def main() -> None:
    engine = create_engine(database_url())
    ahora = date.today().isoformat()
    with engine.begin() as conn:
        periodo = {
            "id": PERIODO_ID, "cliente": CLIENTE, "periodo": PERIODO,
            "estado": "Borrador", "responsable": USUARIO,
            "fecha_vencimiento_iva": "2026-11-20",
            "fecha_vencimiento_iibb": "2026-11-20",
            "ventas_neto": "1350000", "iva_debito": "283500",
            "compras_neto": "200000", "iva_credito": "42000",
            "iva_saldo_tecnico_anterior": "0", "iva_saldo_libre_anterior": "0",
            "iva_deducciones": "18500", "iva_ajustes": "0",
            "iva_uso_libre": "18500", "iva_saldo_tecnico_favor": "0",
            "iva_saldo_libre_favor": "0", "iva_saldo_pagar": "223000",
            "iibb_base": "1350000", "iibb_alicuota": "3.5",
            "iibb_determinado": "47250", "iibb_retenciones": "5000",
            "iibb_percepciones": "1750", "iibb_saldo_favor_anterior": "0",
            "iibb_otros_creditos": "0", "iibb_ajustes": "0",
            "iibb_saldo_favor": "0", "iibb_saldo_pagar": "40500",
            "observaciones": "Período ficticio preparado para probar el circuito completo.",
            "fecha_actualizacion": ahora, "actualizado_por": USUARIO,
            "sin_ventas": "No", "sin_compras": "No",
            "sin_deducciones_iva": "No", "sin_deducciones_iibb": "No",
            "iva_estado_presentacion": "Borrador", "iibb_estado_presentacion": "Borrador",
        }
        upsert(conn, "fiscal_periodos", periodo)

        operaciones = conn.execute(
            text(
                'SELECT * FROM "contable_operaciones" '
                'WHERE "cliente"=:cliente AND "periodo"=:periodo ORDER BY "id"'
            ), {"cliente": CLIENTE, "periodo": PERIODO},
        ).mappings().all()
        for operacion_db in operaciones:
            operacion = dict(operacion_db)
            cabecera, lineas = generar_asiento_operacion(operacion, USUARIO)
            upsert(conn, "contable_asientos", cabecera)
            for linea in lineas:
                upsert(conn, "contable_asiento_lineas", linea)
            conn.execute(
                text('UPDATE "contable_operaciones" SET "asiento_id"=:asiento WHERE "id"=:id'),
                {"asiento": cabecera["id"], "id": operacion["id"]},
            )

        movimientos = [
            {
                "id": "DEMO-PILOT-MOV-VENTA-125", "periodo_id": PERIODO_ID,
                "cliente": CLIENTE, "periodo": PERIODO, "archivo_id": "DEMO-PILOT-ARCA",
                "origen": "ARCA - Mis comprobantes", "impuesto": "IVA", "clase": "emitido",
                "fecha": "2026-10-03", "tipo_comprobante": "1 - Factura A",
                "punto_venta": "00001", "numero": "00000125",
                "cuit_contraparte": "30-00000001-9", "denominacion": "Cliente demostrativo A",
                "neto_gravado": "1000000", "iva": "210000", "otros_tributos": "0",
                "total": "1210000", "computado": "Sí", "observacion": "Coincide con operación diaria.",
            },
            {
                "id": "DEMO-PILOT-MOV-COMPRA-410", "periodo_id": PERIODO_ID,
                "cliente": CLIENTE, "periodo": PERIODO, "archivo_id": "DEMO-PILOT-ARCA",
                "origen": "ARCA - Mis comprobantes", "impuesto": "IVA", "clase": "recibido",
                "fecha": "2026-10-08", "tipo_comprobante": "1 - Factura A",
                "punto_venta": "00002", "numero": "00000410",
                "cuit_contraparte": "30-00000002-7", "denominacion": "Proveedor demostrativo B",
                "neto_gravado": "200000", "iva": "42000", "otros_tributos": "0",
                "total": "242000", "computado": "Sí", "observacion": "Coincide con operación diaria.",
            },
            {
                "id": "DEMO-PILOT-MOV-VENTA-126", "periodo_id": PERIODO_ID,
                "cliente": CLIENTE, "periodo": PERIODO, "archivo_id": "DEMO-PILOT-ARCA",
                "origen": "ARCA - Mis comprobantes", "impuesto": "IVA", "clase": "emitido",
                "fecha": "2026-10-15", "tipo_comprobante": "1 - Factura A",
                "punto_venta": "00001", "numero": "00000126",
                "cuit_contraparte": "30-00000003-5", "denominacion": "Cliente ARCA sin carga diaria",
                "neto_gravado": "350000", "iva": "73500", "otros_tributos": "0",
                "total": "423500", "computado": "Sí", "observacion": "Debe generar borrador fiscal.",
            },
        ]
        for movimiento in movimientos:
            upsert(conn, "fiscal_movimientos", movimiento)

        for impuesto in ("IVA", "IIBB"):
            datos = {k: v for k, v in periodo.items() if k.startswith("iva_") or k.startswith("iibb_")}
            upsert(conn, "fiscal_papeles", {
                "id": f"DEMO-PILOT-PAPEL-{impuesto}", "periodo_id": PERIODO_ID,
                "cliente": CLIENTE, "periodo": PERIODO, "impuesto": impuesto,
                "version": "1", "estado": "Autorizado", "datos_json": json.dumps(datos),
                "fuente_oficial_json": "{}", "fecha_guardado": ahora,
                "guardado_por": USUARIO, "fecha_autorizacion": ahora,
                "autorizado_por": USUARIO,
                "observaciones": "Papel ficticio autorizado para probar la integración contable.",
            })

        # La tercera factura no tiene operación diaria y se contabiliza desde ARCA.
        cab_fiscal, lin_fiscal = generar_asientos_comprobantes(
            pd.DataFrame([movimientos[2]]), CLIENTE, PERIODO, USUARIO,
        )
        cab_imp, lin_imp = generar_asientos_impuestos(periodo, CLIENTE, PERIODO, USUARIO)
        for fila in pd.concat([cab_fiscal, cab_imp], ignore_index=True).to_dict("records"):
            upsert(conn, "contable_asientos", fila)
        for fila in pd.concat([lin_fiscal, lin_imp], ignore_index=True).to_dict("records"):
            upsert(conn, "contable_asiento_lineas", fila)

        upsert(conn, "contable_banco_movimientos", {
            "id": "DEMO-PILOT-BANCO-01", "cliente": CLIENTE, "periodo": PERIODO,
            "cuenta_bancaria": "Banco Demo CC 1234", "fecha": "2026-10-05",
            "descripcion": "TRANSFERENCIA CLIENTE DEMOSTRATIVO A", "referencia": "FAC 00001-125",
            "debito": "0", "credito": "1210000", "saldo": "1210000",
            "source_hash": "DEMO-PILOT-BANCO-01", "cuenta_sugerida": "1.1.03",
            "conciliado": "No", "asiento_id": "", "archivo_nombre": "extracto_demo_octubre.csv",
            "estado_conciliacion": "Coincidencia propuesta", "match_operacion_id": "DEMO-ACC-OP-01",
            "match_confianza": "100", "match_motivo": "Mismo importe y referencia de cliente",
            "fecha_carga": ahora, "cargado_por": USUARIO,
        })
        upsert(conn, "contable_periodos", {
            "id": "DEMO-PILOT-PERIODO-2026-10", "cliente": CLIENTE, "periodo": PERIODO,
            "estado": "Abierto", "fecha_autorizacion": "", "autorizado_por": "",
            "observaciones": "Mes modelo pendiente de revisión final.", "fecha_actualizacion": ahora,
        })
        conn.execute(
            text(
                'UPDATE "contable_cuentas" SET "clave_origen"=:clave '
                'WHERE "cliente"=:cliente AND "codigo"=:codigo'
            ), {"clave": "Banco Demo CC 1234", "cliente": CLIENTE, "codigo": "1.1.02"},
        )
    print("Empresa modelo contable preparada: DEMO — Contabilidad / 2026-10")


if __name__ == "__main__":
    main()
