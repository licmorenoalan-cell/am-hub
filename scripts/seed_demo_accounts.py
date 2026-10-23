#!/usr/bin/env python3
"""Crea cuatro cuentas demo aisladas con recorridos representativos de AM HUB.

El proceso es idempotente: reemplaza solamente los clientes y usuarios demo
definidos en este archivo. Antes de aplicar, exporta a CSV las filas afectadas.
Las contraseñas se reciben por parámetros para no versionarlas en Git.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text
import toml


ROOT = Path(__file__).resolve().parents[1]
TODAY = date.today()
TODAY_ISO = TODAY.isoformat()
PERIOD = TODAY.strftime("%Y-%m")

DEMO_ACCOUNTS = (
    {
        "cliente": "DEMO — Ecosistema Digital",
        "username": "demo.digital",
        "name": "Demo Ecosistema Digital",
        "digital": "Sí",
        "consultoria": "No",
        "contabilidad": "No",
        "password_arg": "digital_password",
    },
    {
        "cliente": "DEMO — Consultoría",
        "username": "demo.consultoria",
        "name": "Demo Consultoría",
        "digital": "No",
        "consultoria": "Sí",
        "contabilidad": "No",
        "password_arg": "consultoria_password",
    },
    {
        "cliente": "DEMO — Contabilidad",
        "username": "demo.contabilidad",
        "name": "Demo Contabilidad",
        "digital": "No",
        "consultoria": "No",
        "contabilidad": "Sí",
        "password_arg": "contabilidad_password",
    },
    {
        "cliente": "DEMO — Integral",
        "username": "demo.integral",
        "name": "Demo Integral",
        "digital": "Sí",
        "consultoria": "Sí",
        "contabilidad": "Sí",
        "password_arg": "integral_password",
    },
)

CLIENT_TABLES = (
    "contenidos",
    "materiales",
    "campanias",
    "reportes",
    "tareas",
    "cuenta_corriente",
    "indicadores_movimientos",
    "fiscal_clientes",
    "contable_operaciones",
)


def database_url() -> str:
    secrets = toml.loads((ROOT / ".streamlit" / "secrets.toml").read_text())
    url = str(secrets["DATABASE_URL"])
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def due(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


def checklist(*items: str, completed: int = 0) -> str:
    return json.dumps(
        [
            {"texto": item, "hecho": index < completed}
            for index, item in enumerate(items)
        ],
        ensure_ascii=False,
    )


def insert_row(conn, table: str, row: dict) -> None:
    columns = list(row)
    conn.execute(
        text(
            f'INSERT INTO "{table}" ('
            + ", ".join(f'"{column}"' for column in columns)
            + ") VALUES ("
            + ", ".join(f":{column}" for column in columns)
            + ")"
        ),
        row,
    )


def task_row(
    *,
    row_id: str,
    client: str,
    title: str,
    status: str,
    deadline: str,
    description: str,
    items: tuple[str, ...],
    category: str,
    completed: int = 0,
) -> dict:
    progress = round(completed / len(items) * 100) if items else 0
    return {
        "id": row_id,
        "cliente": client,
        "tarea": title,
        "responsable_am": "AM Consultora",
        "prioridad": "Alta" if status != "Finalizada" else "Media",
        "estado": status,
        "fecha_limite": deadline,
        "descripcion": description,
        "comentarios": "Información ficticia preparada para recorrer la plataforma.",
        "fecha_carga": TODAY_ISO,
        "creado_por": "AM Consultora",
        "fecha_actualizacion": TODAY_ISO,
        "actualizado_por": "AM Consultora",
        "checklist": checklist(*items, completed=completed),
        "avance": progress,
        "recurrente": "No",
        "frecuencia": "",
        "intervalo": 1,
        "serie_id": "",
        "ocurrencia": 1,
        "proyecto": "Proyecto demostrativo",
        "origen": "Cuenta demo AM HUB",
        "id_externo": "",
        "categoria": category,
        "unidad": "AM Consultora",
        "orden_manual": "",
        "archivos_habilitados": "Sí",
        "posicion_manual": "",
    }


def digital_rows(client: str, prefix: str) -> dict[str, list[dict]]:
    return {
        "contenidos": [
            {
                "id": f"{prefix}-CON-01",
                "cliente": client,
                "fecha": due(3),
                "canal": "Instagram",
                "formato": "Carrusel",
                "tema": "Tres claves para ordenar el crecimiento del negocio",
                "objetivo": "Autoridad y educación",
                "copy": "Contenido demostrativo: una pieza educativa con cierre orientado a conversación.",
                "link_canva": "",
                "estado": "En revisión",
                "comentario_cliente": "Ejemplo: ajustar la portada antes de publicar.",
            },
            {
                "id": f"{prefix}-CON-02",
                "cliente": client,
                "fecha": due(7),
                "canal": "LinkedIn",
                "formato": "Post",
                "tema": "Caso de transformación de un cliente",
                "objetivo": "Prueba social",
                "copy": "Contenido demostrativo aprobado para mostrar el flujo de validación.",
                "link_canva": "",
                "estado": "Aprobado",
                "comentario_cliente": "Aprobado sin cambios.",
            },
            {
                "id": f"{prefix}-CON-03",
                "cliente": client,
                "fecha": due(11),
                "canal": "Instagram",
                "formato": "Reel",
                "tema": "Detrás de escena del servicio",
                "objetivo": "Cercanía",
                "copy": "Guion demostrativo pendiente de producción.",
                "link_canva": "",
                "estado": "En diseño",
                "comentario_cliente": "",
            },
        ],
        "materiales": [
            {
                "id": f"{prefix}-MAT-01",
                "cliente": client,
                "solicitud": "Enviar fotografías del equipo y del espacio de trabajo",
                "responsable_cliente": "Cliente Demo",
                "fecha_limite": due(5),
                "estado": "Pendiente",
                "observacion": "Material demostrativo: imágenes verticales y horizontales.",
            },
            {
                "id": f"{prefix}-MAT-02",
                "cliente": client,
                "solicitud": "Compartir testimonio breve de un cliente",
                "responsable_cliente": "Cliente Demo",
                "fecha_limite": due(9),
                "estado": "Solicitado",
                "observacion": "Puede cargarse como archivo o enlace.",
            },
        ],
        "campanias": [
            {
                "id": f"{prefix}-ADS-01",
                "cliente": client,
                "campania": "Generación de consultas — Campaña demo",
                "plataforma": "Meta Ads",
                "objetivo": "Mensajes",
                "presupuesto": "180000",
                "estado": "Activa",
                "leads": "36",
                "costo_por_lead": "5000",
                "observacion": "Datos ficticios para visualizar seguimiento y métricas.",
            }
        ],
        "reportes": [
            {
                "id": f"{prefix}-REP-01",
                "cliente": client,
                "mes": TODAY.strftime("%B %Y").capitalize(),
                "alcance": "28400",
                "interacciones": "3260",
                "consultas": "84",
                "inversion": "180000",
                "estado": "Disponible",
                "que_funciono": "Los contenidos educativos y los videos breves generaron mayor interacción.",
                "proximo_foco": "Optimizar llamados a la acción y reforzar casos reales.",
                "pdf_nombre": "",
                "pdf_tipo": "",
                "pdf_base64": "",
                "fecha_carga": TODAY_ISO,
                "cargado_por": "AM Consultora",
            }
        ],
    }


def consulting_rows(client: str, prefix: str) -> list[dict]:
    return [
        task_row(
            row_id=f"{prefix}-TAR-01",
            client=client,
            title="Definir prioridades comerciales del próximo trimestre",
            status="En curso",
            deadline=due(6),
            description="Ordenar objetivos, foco comercial y decisiones prioritarias para el próximo trimestre.",
            items=(
                "Revisar resultados del trimestre actual",
                "Definir tres prioridades",
                "Validar responsables y fechas",
            ),
            completed=1,
            category="Estrategia",
        ),
        task_row(
            row_id=f"{prefix}-TAR-02",
            client=client,
            title="Revisar estructura de costos y rentabilidad",
            status="Pendiente",
            deadline=due(10),
            description="Preparar la información necesaria para revisar margen, costos fijos y oportunidades de mejora.",
            items=(
                "Actualizar costos fijos",
                "Relevar costos variables",
                "Identificar productos o servicios más rentables",
            ),
            category="Finanzas",
        ),
        task_row(
            row_id=f"{prefix}-TAR-03",
            client=client,
            title="Actualizar propuesta de valor",
            status="Finalizada",
            deadline=due(-4),
            description="Ejemplo de una tarjeta completada con seguimiento y entregable.",
            items=(
                "Definir público principal",
                "Precisar problema y transformación",
                "Aprobar versión final",
            ),
            completed=3,
            category="Posicionamiento",
        ),
    ]


def accounting_rows(client: str, prefix: str) -> dict[str, list[dict]]:
    fiscal_tasks = [
        task_row(
            row_id=f"{prefix}-TAX-IVA",
            client=client,
            title=f"IVA — {client}",
            status="En curso",
            deadline=due(8),
            description="Liquidación mensual demostrativa. Revisar compras, ventas, retenciones y saldo técnico.",
            items=(
                "Cargar ventas del período",
                "Cargar compras del período",
                "Revisar retenciones y percepciones",
                "Validar papel de trabajo",
            ),
            completed=2,
            category="IVA",
        ),
        task_row(
            row_id=f"{prefix}-TAX-IIBB",
            client=client,
            title=f"Ingresos Brutos — {client}",
            status="Pendiente",
            deadline=due(10),
            description="Control mensual demostrativo de Ingresos Brutos local.",
            items=(
                "Controlar base imponible",
                "Revisar retenciones y percepciones",
                "Validar saldo del anticipo",
            ),
            category="Ingresos Brutos",
        ),
    ]
    movements = [
        ("01", "Ingreso", "Ventas", "1250000", "Cobros por servicios del mes"),
        ("02", "Ingreso", "Otros ingresos", "180000", "Ingreso extraordinario"),
        ("03", "Gasto", "Alquiler", "320000", "Alquiler de oficina"),
        ("04", "Gasto", "Sueldos", "410000", "Pago mensual"),
        ("05", "Gasto", "Marketing", "95000", "Campañas y producción"),
        ("06", "Gasto", "Servicios", "87000", "Servicios operativos"),
    ]
    operations = [
        {
            "id": f"{prefix}-OP-01",
            "cliente": client,
            "periodo": PERIOD,
            "fecha": TODAY.replace(day=3).isoformat(),
            "tipo_operacion": "Ingreso",
            "tercero_id": "",
            "tercero_cuit": "30-00000001-9",
            "tercero_nombre": "Cliente demostrativo A",
            "tipo_comprobante": "Factura A",
            "punto_venta": "00001",
            "numero": "00000125",
            "moneda": "ARS",
            "tipo_cambio": "1",
            "neto": "1000000",
            "iva": "210000",
            "otros": "0",
            "total": "1210000",
            "importe_pesos": "1210000",
            "condicion_pago": "Cuenta corriente",
            "medio_pago": "Transferencia",
            "cuenta_origen": "Banco demo",
            "cuenta_resultado": "Ventas de servicios",
            "centro_costo": "Operación principal",
            "es_personal": "No",
            "estado_revision": "Aprobada",
            "observaciones": "Operación ficticia de demostración.",
            "asiento_id": "",
            "fecha_carga": TODAY_ISO,
            "cargado_por": "AM Consultora",
            "fecha_revision": TODAY_ISO,
            "revisado_por": "AM Consultora",
        },
        {
            "id": f"{prefix}-OP-02",
            "cliente": client,
            "periodo": PERIOD,
            "fecha": TODAY.replace(day=8).isoformat(),
            "tipo_operacion": "Egreso",
            "tercero_id": "",
            "tercero_cuit": "30-00000002-7",
            "tercero_nombre": "Proveedor demostrativo B",
            "tipo_comprobante": "Factura A",
            "punto_venta": "00002",
            "numero": "00000410",
            "moneda": "ARS",
            "tipo_cambio": "1",
            "neto": "200000",
            "iva": "42000",
            "otros": "0",
            "total": "242000",
            "importe_pesos": "242000",
            "condicion_pago": "Contado",
            "medio_pago": "Transferencia",
            "cuenta_origen": "Banco demo",
            "cuenta_resultado": "Servicios contratados",
            "centro_costo": "Administración",
            "es_personal": "No",
            "estado_revision": "Pendiente de revisión",
            "observaciones": "Operación ficticia pendiente para mostrar el circuito de control.",
            "asiento_id": "",
            "fecha_carga": TODAY_ISO,
            "cargado_por": "Cliente Demo",
            "fecha_revision": "",
            "revisado_por": "",
        },
    ]
    return {
        "tareas": fiscal_tasks,
        "indicadores_movimientos": [
            {
                "id": f"{prefix}-MOV-{code}",
                "cliente": client,
                "mes": PERIOD,
                "tipo": movement_type,
                "categoria": category,
                "importe": amount,
                "observacion": observation,
                "fecha_carga": TODAY_ISO,
                "cargado_por": "Cliente Demo",
            }
            for code, movement_type, category, amount, observation in movements
        ],
        "fiscal_clientes": [
            {
                "id": f"{prefix}-FISCAL",
                "cliente": client,
                "cuit": "30-00000000-0",
                "razon_social": "EMPRESA DEMOSTRATIVA S.R.L.",
                "condicion_iva": "Responsable inscripto",
                "iibb_regimen": "Local",
                "iibb_jurisdiccion": "AGIP - CABA",
                "iibb_inscripcion": "DEMO",
                "actividad_principal": "Servicios profesionales",
                "actividades": "Información ficticia de demostración",
                "alicuota_iibb": "3.5",
                "email_destinatarios": "",
                "observaciones": "Ficha fiscal ficticia. No utilizar para presentaciones reales.",
                "fecha_actualizacion": datetime.now().isoformat(),
                "actualizado_por": "AM Consultora",
                "mes_cierre_ejercicio": "12",
            }
        ],
        "contable_operaciones": operations,
    }


def common_account_rows(client: str, prefix: str) -> list[dict]:
    return [
        {
            "id": f"{prefix}-CC-01",
            "cliente": client,
            "mes": PERIOD,
            "concepto": "Honorarios mensuales — ejemplo",
            "importe": 99000.0,
            "estado": "Pagado",
            "fecha_factura": TODAY.replace(day=1).isoformat(),
            "fecha_pago": TODAY.replace(day=min(10, TODAY.day)).isoformat(),
            "observacion": "Movimiento ficticio para visualizar la cuenta corriente.",
            "fecha_carga": TODAY_ISO,
            "cargado_por": "AM Consultora",
            "comprobante_nombre": "",
            "comprobante_tipo": "",
            "comprobante_base64": "",
            "servicio": "Demostración",
            "moneda": "ARS",
        }
    ]


def build_rows() -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = {table: [] for table in CLIENT_TABLES}
    for account in DEMO_ACCOUNTS:
        client = account["cliente"]
        prefix = {
            "demo.digital": "DEMO-DIG",
            "demo.consultoria": "DEMO-CON",
            "demo.contabilidad": "DEMO-ACC",
            "demo.integral": "DEMO-INT",
        }[account["username"]]
        rows["cuenta_corriente"].extend(common_account_rows(client, prefix))
        if account["digital"] == "Sí":
            for table, values in digital_rows(client, prefix).items():
                rows[table].extend(values)
        if account["consultoria"] == "Sí":
            rows["tareas"].extend(consulting_rows(client, prefix))
        if account["contabilidad"] == "Sí":
            for table, values in accounting_rows(client, prefix).items():
                rows[table].extend(values)
    return rows


def backup_rows(engine, backup_dir: Path) -> list[Path]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clients = [account["cliente"] for account in DEMO_ACCOUNTS]
    usernames = [account["username"] for account in DEMO_ACCOUNTS]
    paths = []
    with engine.connect() as conn:
        for table in ("clientes", *CLIENT_TABLES):
            current = pd.read_sql(
                text(f'SELECT * FROM "{table}" WHERE "cliente" = ANY(:values)'),
                conn,
                params={"values": clients},
            )
            if not current.empty:
                path = backup_dir / f"{table}_demo_antes_{stamp}.csv"
                current.to_csv(path, index=False)
                paths.append(path)
        current_users = pd.read_sql(
            text('SELECT * FROM "usuarios" WHERE "username" = ANY(:values)'),
            conn,
            params={"values": usernames},
        )
        if not current_users.empty:
            path = backup_dir / f"usuarios_demo_antes_{stamp}.csv"
            current_users.to_csv(path, index=False)
            paths.append(path)
    return paths


def require_passwords(args: argparse.Namespace) -> None:
    missing = [
        account["username"]
        for account in DEMO_ACCOUNTS
        if not getattr(args, account["password_arg"])
    ]
    if missing:
        raise SystemExit("Faltan contraseñas para: " + ", ".join(missing))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--digital-password")
    parser.add_argument("--consultoria-password")
    parser.add_argument("--contabilidad-password")
    parser.add_argument("--integral-password")
    parser.add_argument("--backup-dir", default=str(ROOT / "backups_locales"))
    args = parser.parse_args()

    rows = build_rows()
    if not args.apply:
        for account in DEMO_ACCOUNTS:
            services = [
                name
                for name, enabled in (
                    ("Digital", account["digital"]),
                    ("Consultoría", account["consultoria"]),
                    ("Contabilidad", account["contabilidad"]),
                )
                if enabled == "Sí"
            ]
            print(f'{account["username"]}: {", ".join(services)}')
        print("Filas demo:", {table: len(values) for table, values in rows.items()})
        return

    require_passwords(args)
    engine = create_engine(database_url(), connect_args={"prepare_threshold": None})
    backups = backup_rows(engine, Path(args.backup_dir))
    clients = [account["cliente"] for account in DEMO_ACCOUNTS]
    usernames = [account["username"] for account in DEMO_ACCOUNTS]

    with engine.begin() as conn:
        for table in CLIENT_TABLES:
            conn.execute(
                text(f'DELETE FROM "{table}" WHERE "cliente" = ANY(:values)'),
                {"values": clients},
            )
        conn.execute(
            text('DELETE FROM "usuarios" WHERE "username" = ANY(:values)'),
            {"values": usernames},
        )
        conn.execute(
            text('DELETE FROM "clientes" WHERE "cliente" = ANY(:values)'),
            {"values": clients},
        )

        for account in DEMO_ACCOUNTS:
            insert_row(
                conn,
                "clientes",
                {
                    "cliente": account["cliente"],
                    "rubro": "Empresa demostrativa",
                    "estado": "Activo",
                    "plan": "Demo comercial",
                    "responsable_am": "AM Consultora",
                    "fecha_inicio": TODAY_ISO,
                    "servicio_digital": account["digital"],
                    "servicio_consultoria": account["consultoria"],
                    "servicio_contabilidad": account["contabilidad"],
                    "notas": "Cuenta ficticia para demostraciones comerciales.",
                },
            )
            insert_row(
                conn,
                "usuarios",
                {
                    "username": account["username"],
                    "password": getattr(args, account["password_arg"]),
                    "role": "cliente",
                    "name": account["name"],
                    "cliente": account["cliente"],
                    "activo": "Sí",
                    "idioma": "es",
                },
            )

        for table, table_rows in rows.items():
            for row in table_rows:
                insert_row(conn, table, row)

    print("Cuentas demo creadas:", ", ".join(usernames))
    print("Backups previos:", len(backups))


if __name__ == "__main__":
    main()
