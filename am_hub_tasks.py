"""Lógica compartida para las recurrencias de tareas de AM HUB y AM Pocket."""

from __future__ import annotations

from datetime import date
import json
import uuid

import pandas as pd
from sqlalchemy import text


def siguiente_fecha_recurrente(fecha_actual, frecuencia, intervalo=1) -> str:
    try:
        fecha = pd.Timestamp(fecha_actual)
    except Exception:
        fecha = pd.Timestamp(date.today())

    try:
        intervalo = max(1, int(float(intervalo or 1)))
    except (TypeError, ValueError):
        intervalo = 1

    if frecuencia == "Diaria":
        siguiente = fecha + pd.DateOffset(days=intervalo)
    elif frecuencia == "Semanal":
        siguiente = fecha + pd.DateOffset(weeks=intervalo)
    elif frecuencia == "Mensual":
        siguiente = fecha + pd.DateOffset(months=intervalo)
    elif frecuencia == "Semestral":
        siguiente = fecha + pd.DateOffset(months=6 * intervalo)
    elif frecuencia == "Primer día hábil del mes":
        mes_objetivo = fecha + pd.DateOffset(months=intervalo)
        siguiente = pd.Timestamp(
            year=mes_objetivo.year,
            month=mes_objetivo.month,
            day=1,
        )
        while siguiente.weekday() >= 5:
            siguiente += pd.DateOffset(days=1)
    elif frecuencia == "Último día hábil del mes":
        mes_objetivo = fecha + pd.DateOffset(months=intervalo)
        siguiente = (
            pd.Timestamp(
                year=mes_objetivo.year,
                month=mes_objetivo.month,
                day=1,
            )
            + pd.offsets.MonthEnd(1)
        )
        while siguiente.weekday() >= 5:
            siguiente -= pd.DateOffset(days=1)
    else:
        siguiente = fecha

    return siguiente.strftime("%Y-%m-%d")


def _checklist_reiniciado(valor) -> str:
    try:
        items = json.loads(str(valor or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        items = []

    reiniciado = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            texto_item = str(item.get("texto", "")).strip()
        else:
            texto_item = str(item).strip()
        if texto_item:
            reiniciado.append({"texto": texto_item, "hecho": False})
    return json.dumps(reiniciado, ensure_ascii=False)


def construir_siguiente_ocurrencia(
    tarea: dict,
    usuario: str,
    hoy: date | None = None,
    nueva_id: str | None = None,
) -> dict:
    hoy = hoy or date.today()
    try:
        ocurrencia = int(float(tarea.get("ocurrencia", 1) or 1)) + 1
    except (TypeError, ValueError):
        ocurrencia = 2

    try:
        intervalo = max(1, int(float(tarea.get("intervalo", 1) or 1)))
    except (TypeError, ValueError):
        intervalo = 1

    tarea_id = str(tarea.get("id", "")).strip()
    serie_id = str(tarea.get("serie_id", "")).strip() or f"SER-{tarea_id}"
    return {
        "id": nueva_id or f"TAR-{uuid.uuid4().hex}",
        "cliente": str(tarea.get("cliente", "") or ""),
        "tarea": str(tarea.get("tarea", "") or ""),
        "responsable_am": str(
            tarea.get("responsable_am", "Sin asignar") or "Sin asignar"
        ),
        "prioridad": str(tarea.get("prioridad", "Media") or "Media"),
        "estado": "Pendiente",
        "fecha_limite": siguiente_fecha_recurrente(
            tarea.get("fecha_limite", ""),
            str(tarea.get("frecuencia", "") or ""),
            intervalo,
        ),
        "descripcion": str(tarea.get("descripcion", "") or ""),
        "comentarios": "",
        "fecha_carga": hoy.strftime("%Y-%m-%d"),
        "creado_por": "Generación automática",
        "fecha_actualizacion": hoy.strftime("%Y-%m-%d"),
        "actualizado_por": str(usuario or "Sistema"),
        "checklist": _checklist_reiniciado(tarea.get("checklist", "")),
        "avance": "0",
        "recurrente": "Sí",
        "frecuencia": str(tarea.get("frecuencia", "") or ""),
        "intervalo": str(intervalo),
        "serie_id": serie_id,
        "ocurrencia": str(ocurrencia),
        "proyecto": str(tarea.get("proyecto", "") or ""),
        "origen": str(tarea.get("origen", "AM Hub") or "AM Hub"),
        "id_externo": "",
        "categoria": str(tarea.get("categoria", "") or ""),
        "unidad": str(tarea.get("unidad", "AM Consultora") or "AM Consultora"),
        "orden_manual": "",
        "archivos_habilitados": str(
            tarea.get("archivos_habilitados", "No") or "No"
        ),
        "posicion_manual": "",
    }


def actualizar_estado_tarea_postgres(
    engine,
    tarea_id: str,
    nuevo_estado: str,
    usuario: str,
) -> dict:
    """Actualiza el estado y crea atómicamente la próxima recurrencia."""
    hoy = date.today()
    with engine.begin() as conn:
        tarea = conn.execute(
            text('SELECT * FROM "tareas" WHERE "id" = :id FOR UPDATE'),
            {"id": str(tarea_id)},
        ).mappings().first()
        if tarea is None:
            raise ValueError("No se encontró la tarea.")

        tarea = dict(tarea)
        nueva = None
        debe_generar = (
            str(tarea.get("recurrente", "No")).strip() == "Sí"
            and str(nuevo_estado) == "Finalizada"
            and str(tarea.get("estado", "")) != "Finalizada"
        )
        if debe_generar:
            nueva = construir_siguiente_ocurrencia(tarea, usuario, hoy=hoy)
            ya_existe = conn.execute(
                text(
                    'SELECT 1 FROM "tareas" '
                    'WHERE "serie_id" = :serie_id '
                    'AND COALESCE("ocurrencia", 1) = :ocurrencia LIMIT 1'
                ),
                {
                    "serie_id": nueva["serie_id"],
                    "ocurrencia": int(nueva["ocurrencia"]),
                },
            ).first()
            if ya_existe:
                nueva = None
            else:
                columnas = list(nueva)
                conn.execute(
                    text(
                        'INSERT INTO "tareas" ('
                        + ", ".join(f'"{col}"' for col in columnas)
                        + ") VALUES ("
                        + ", ".join(f":{col}" for col in columnas)
                        + ")"
                    ),
                    nueva,
                )

        conn.execute(
            text(
                'UPDATE "tareas" SET "estado" = :estado, '
                '"fecha_actualizacion" = :fecha, '
                '"actualizado_por" = :usuario WHERE "id" = :id'
            ),
            {
                "estado": str(nuevo_estado),
                "fecha": hoy.strftime("%Y-%m-%d"),
                "usuario": str(usuario or "Sistema"),
                "id": str(tarea_id),
            },
        )

    return {"actualizada": str(tarea_id), "generada": nueva}
