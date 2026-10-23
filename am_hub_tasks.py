"""Lógica compartida para las recurrencias de tareas de AM HUB y AM Pocket."""

from __future__ import annotations

from datetime import date
import json
import re
import uuid

import pandas as pd
from sqlalchemy import text


CATEGORIAS_IMPOSITIVAS = (
    "IVA",
    "Ingresos Brutos",
    "Monotributo",
    "Autónomos",
    "Anticipos",
    "Ganancias",
    "Tasas municipales",
)


# Vencimientos mensuales oficiales publicados para el cierre de 2026.  Las
# recurrencias fiscales no pueden limitarse a sumar un mes: feriados y grupos
# de CUIT cambian el día efectivo de cada obligación.
_VENCIMIENTOS_FISCALES_2026 = {
    "IVA": {
        "2026-11": ((0, 1, 18), (2, 3, 19), (4, 5, 20), (6, 7, 24), (8, 9, 25)),
        "2026-12": ((0, 1, 18), (2, 3, 21), (4, 5, 22), (6, 7, 23), (8, 9, 24)),
    },
    "AGIP LOCAL": {
        "2026-11": ((0, 1, 11), (2, 3, 12), (4, 5, 13), (6, 7, 16), (8, 9, 17)),
        "2026-12": ((0, 1, 11), (2, 3, 14), (4, 5, 15), (6, 7, 16), (8, 9, 17)),
        "2027-01": ((0, 1, 11), (2, 3, 12), (4, 5, 13), (6, 7, 14), (8, 9, 15)),
    },
    "ARBA LOCAL": {
        "2026-11": ((0, 1, 24), (2, 3, 25), (4, 5, 26), (6, 7, 27), (8, 9, 30)),
        "2026-12": ((0, 1, 21), (2, 3, 22), (4, 5, 23), (6, 7, 28), (8, 9, 29)),
        "2027-01": ((0, 1, 18), (2, 3, 19), (4, 5, 20), (6, 7, 21), (8, 9, 22)),
    },
    "CONVENIO MULTILATERAL": {
        "2026-11": ((0, 2, 17), (3, 5, 18), (6, 7, 19), (8, 9, 20)),
        "2026-12": ((0, 2, 15), (3, 5, 16), (6, 7, 17), (8, 9, 18)),
        "2027-01": ((0, 2, 15), (3, 5, 18), (6, 7, 19), (8, 9, 20)),
    },
}


def _cuit_desde_tarea(tarea: dict) -> str:
    texto_tarea = " ".join(
        str(tarea.get(campo, "") or "")
        for campo in ("descripcion", "comentarios", "tarea")
    )
    coincidencia = re.search(r"\b(?:20|23|24|27|30|33)-?\d{8}-?\d\b", texto_tarea)
    return re.sub(r"\D", "", coincidencia.group(0)) if coincidencia else ""


def _regimen_fiscal_desde_tarea(tarea: dict) -> str:
    categoria = categoria_visual_tarea(tarea.get("categoria", ""), tarea.get("tarea", ""))
    if categoria == "IVA":
        return "IVA"
    texto_tarea = " ".join(
        str(tarea.get(campo, "") or "")
        for campo in ("descripcion", "comentarios", "tarea")
    ).casefold()
    if "arba local" in texto_tarea:
        return "ARBA LOCAL"
    if "agip local" in texto_tarea:
        return "AGIP LOCAL"
    if "convenio multilateral" in texto_tarea or re.search(r"\bcm\b", texto_tarea):
        return "CONVENIO MULTILATERAL"
    return ""


def siguiente_fecha_fiscal(tarea: dict, intervalo=1) -> str:
    """Devuelve el próximo vencimiento oficial conocido para una serie fiscal."""
    cuit = _cuit_desde_tarea(tarea)
    regimen = _regimen_fiscal_desde_tarea(tarea)
    if len(cuit) != 11 or regimen not in _VENCIMIENTOS_FISCALES_2026:
        return ""
    try:
        fecha_actual = pd.Timestamp(tarea.get("fecha_limite", ""))
        intervalo = max(1, int(float(intervalo or 1)))
    except (TypeError, ValueError):
        return ""
    mes_objetivo = fecha_actual + pd.DateOffset(months=intervalo)
    clave_mes = mes_objetivo.strftime("%Y-%m")
    digito = int(cuit[-1])
    for desde, hasta, dia in _VENCIMIENTOS_FISCALES_2026[regimen].get(clave_mes, ()):
        if desde <= digito <= hasta:
            return pd.Timestamp(
                year=mes_objetivo.year,
                month=mes_objetivo.month,
                day=dia,
            ).strftime("%Y-%m-%d")
    return ""


def categoria_visual_tarea(categoria, titulo="") -> str:
    """Normaliza la etiqueta fiscal sin modificar el dato guardado."""
    categoria_limpia = str(categoria or "").strip()
    texto = f"{categoria_limpia} {titulo or ''}".casefold()

    reglas = (
        ((r"\bingresos brutos\b", r"\biibb\b", r"\bconvenio multilateral\b"), "Ingresos Brutos"),
        ((r"\bmonotributo\b",), "Monotributo"),
        ((r"\bautónomos?\b", r"\bautonomos?\b"), "Autónomos"),
        ((r"\banticipos?\b",), "Anticipos"),
        ((r"\bganancias\b",), "Ganancias"),
        ((r"\btasas? municipales?\b", r"\bmunicipal\b"), "Tasas municipales"),
        ((r"\biva\b",), "IVA"),
    )
    for patrones, nombre in reglas:
        if any(re.search(patron, texto) for patron in patrones):
            return nombre
    return categoria_limpia


def es_categoria_impositiva(categoria) -> bool:
    return str(categoria or "").strip() in CATEGORIAS_IMPOSITIVAS


def titulo_visual_tarea(titulo, cliente="", categoria="") -> str:
    """Evita repetir `IVA — Cliente` cuando ambos ya son etiquetas visibles."""
    titulo_limpio = str(titulo or "").strip() or "Sin título"
    cliente_limpio = str(cliente or "").strip()
    categoria_limpia = categoria_visual_tarea(categoria, titulo_limpio)
    if cliente_limpio and es_categoria_impositiva(categoria_limpia):
        return cliente_limpio
    return titulo_limpio


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
    fecha_fiscal = siguiente_fecha_fiscal(tarea, intervalo)
    return {
        "id": nueva_id or f"TAR-{uuid.uuid4().hex}",
        "cliente": str(tarea.get("cliente", "") or ""),
        "tarea": str(tarea.get("tarea", "") or ""),
        "responsable_am": str(
            tarea.get("responsable_am", "Sin asignar") or "Sin asignar"
        ),
        "prioridad": str(tarea.get("prioridad", "Media") or "Media"),
        "estado": "Pendiente",
        "fecha_limite": fecha_fiscal
        or siguiente_fecha_recurrente(
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
