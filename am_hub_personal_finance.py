"""Reglas de negocio del tablero liviano de finanzas personales."""

from __future__ import annotations

import pandas as pd


CUENTA_PERSONAL_COLUMNAS = [
    "id", "cliente", "periodo", "cuenta", "tipo", "moneda", "saldo",
    "observaciones", "fecha_actualizacion", "actualizado_por",
]

TARJETA_PERSONAL_COLUMNAS = [
    "id", "cliente", "periodo", "tarjeta", "titular", "moneda",
    "fecha_cierre", "fecha_vencimiento", "total_resumen", "pago_minimo",
    "pago_realizado", "tasa_mensual", "estado", "observaciones",
    "fecha_actualizacion", "actualizado_por",
]


def numero(valor) -> float:
    """Convierte importes persistidos como texto en números seguros."""
    try:
        resultado = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return resultado if pd.notna(resultado) else 0.0


def ultimo_periodo_por_nombre(
    df: pd.DataFrame,
    nombre_columna: str,
) -> pd.DataFrame:
    """Devuelve la última foto de cada cuenta o tarjeta."""
    if df is None or df.empty or nombre_columna not in df.columns:
        return pd.DataFrame(columns=list(df.columns) if df is not None else [])
    base = df.copy()
    if "periodo" not in base.columns:
        base["periodo"] = ""
    base["periodo"] = base["periodo"].fillna("").astype(str)
    base[nombre_columna] = base[nombre_columna].fillna("").astype(str).str.strip()
    base = base[base[nombre_columna].ne("")]
    return (
        base.sort_values([nombre_columna, "periodo", "id"])
        .drop_duplicates(subset=[nombre_columna], keep="last")
        .reset_index(drop=True)
    )


def resumen_finanzas_personales(
    cuentas: pd.DataFrame,
    tarjetas: pd.DataFrame,
    resultado_mensual: float = 0,
    reserva_minima: float = 0,
) -> dict[str, float]:
    """Calcula los indicadores y una referencia prudente de cancelación."""
    cuentas_actuales = ultimo_periodo_por_nombre(cuentas, "cuenta")
    tarjetas_actuales = ultimo_periodo_por_nombre(tarjetas, "tarjeta")

    if not cuentas_actuales.empty:
        saldos = cuentas_actuales.get("saldo", pd.Series(dtype=float)).map(numero)
        liquidez = float(saldos.sum())
        tipos = cuentas_actuales.get("tipo", pd.Series("", index=cuentas_actuales.index))
        ahorro = float(
            saldos[tipos.fillna("").astype(str).str.casefold().eq("ahorro")].sum()
        )
    else:
        liquidez = ahorro = 0.0

    if not tarjetas_actuales.empty:
        total = tarjetas_actuales.get(
            "total_resumen", pd.Series(0, index=tarjetas_actuales.index)
        ).map(numero)
        pagado = tarjetas_actuales.get(
            "pago_realizado", pd.Series(0, index=tarjetas_actuales.index)
        ).map(numero)
        deuda = float((total - pagado).clip(lower=0).sum())
        minimo = float(
            tarjetas_actuales.get(
                "pago_minimo", pd.Series(0, index=tarjetas_actuales.index)
            ).map(numero).sum()
        )
    else:
        deuda = minimo = 0.0

    reserva = max(0.0, numero(reserva_minima))
    excedente_liquido = max(0.0, liquidez - reserva)
    capacidad_mensual = max(0.0, numero(resultado_mensual))
    cancelacion_posible = min(deuda, excedente_liquido + capacidad_mensual)
    deuda_posterior = max(0.0, deuda - cancelacion_posible)

    return {
        "liquidez": liquidez,
        "ahorro": ahorro,
        "deuda_tarjetas": deuda,
        "pago_minimo": minimo,
        "resultado_mensual": numero(resultado_mensual),
        "reserva_minima": reserva,
        "cancelacion_posible": cancelacion_posible,
        "deuda_posterior": deuda_posterior,
        "patrimonio_liquido": liquidez - deuda,
    }

