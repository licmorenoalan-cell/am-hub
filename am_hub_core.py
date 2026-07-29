"""Utilidades compartidas y testeables de AM Hub.

Este módulo no importa Streamlit para que las reglas de persistencia puedan
probarse sin iniciar la interfaz.
"""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def crear_evento_actividad(
    *,
    usuario: str,
    nombre: str,
    role: str,
    cliente: str,
    accion: str,
    recurso: str,
    registro_id: str = "",
    detalle: str = "",
) -> dict[str, str]:
    """Construye un evento compacto sin incluir datos sensibles completos."""
    return {
        "id": f"EVT-{uuid.uuid4().hex}",
        "fecha_hora": datetime.now(timezone.utc).isoformat(),
        "usuario": str(usuario).strip(),
        "nombre": str(nombre),
        "role": str(role),
        "cliente": str(cliente),
        "accion": str(accion).strip(),
        "recurso": str(recurso).strip(),
        "registro_id": str(registro_id or ""),
        "detalle": str(detalle or "")[:1000],
    }


def validar_identificador_sql(valor: str) -> str:
    """Acepta únicamente identificadores SQL simples y predecibles."""
    valor = str(valor)
    if not IDENTIFIER_RE.fullmatch(valor):
        raise ValueError(f"Identificador SQL inválido: {valor!r}")
    return valor


def normalizar_dataframe(df: pd.DataFrame, columns: list[str] | None) -> pd.DataFrame:
    """Completa columnas requeridas conservando las columnas adicionales."""
    clean = df.copy()
    requeridas = list(columns or [])
    for col in requeridas:
        if col not in clean.columns:
            clean[col] = ""
    extras = [col for col in clean.columns if col not in requeridas]
    return clean[requeridas + extras] if requeridas else clean


def buscar_dataframe(
    df: pd.DataFrame,
    consulta: str,
    columnas: list[str],
) -> pd.DataFrame:
    """Filtra filas que contienen todas las palabras en las columnas indicadas."""
    palabras = [
        palabra.casefold()
        for palabra in str(consulta or "").split()
        if palabra.strip()
    ]
    if df.empty or not palabras:
        return df.copy()

    columnas_validas = [col for col in columnas if col in df.columns]
    if not columnas_validas:
        return df.iloc[0:0].copy()

    texto = pd.Series("", index=df.index, dtype="object")
    for columna in columnas_validas:
        texto = texto + " " + df[columna].fillna("").astype(str).str.casefold()

    mascara = pd.Series(True, index=df.index)
    for palabra in palabras:
        mascara &= texto.str.contains(palabra, regex=False, na=False)
    return df.loc[mascara].copy()


def filtrar_tareas_por_estado(
    df: pd.DataFrame,
    estados_seleccionados: list[str] | None,
) -> pd.DataFrame:
    """Oculta finalizadas salvo que se soliciten explícitamente."""
    if df.empty or "estado" not in df.columns:
        return df.copy()

    seleccion = [
        str(valor).strip()
        for valor in (estados_seleccionados or [])
        if str(valor).strip()
    ]
    estados = df["estado"].fillna("").astype(str).str.strip()

    if not seleccion:
        return df.loc[estados.ne("Finalizada")].copy()

    mascara = pd.Series(False, index=df.index)
    if "Activas" in seleccion:
        mascara |= estados.ne("Finalizada")

    concretos = [valor for valor in seleccion if valor != "Activas"]
    if concretos:
        mascara |= estados.isin(concretos)

    return df.loc[mascara].copy()


def escribir_csv_atomico(df: pd.DataFrame, path: Path) -> None:
    """Escribe un CSV completo sin dejar archivos parciales ante un fallo."""
    destino = Path(path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    clean = df.copy().fillna("")

    fd, temporal = tempfile.mkstemp(
        prefix=f".{destino.name}.", suffix=".tmp", dir=destino.parent
    )
    os.close(fd)
    temporal_path = Path(temporal)
    try:
        clean.to_csv(temporal_path, index=False)
        os.replace(temporal_path, destino)
    finally:
        temporal_path.unlink(missing_ok=True)
