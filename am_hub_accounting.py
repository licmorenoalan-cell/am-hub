"""Motor contable aislado para AM Hub.

La capa no depende de Streamlit ni de la base de datos. Recibe movimientos
normalizados y devuelve asientos balanceados listos para guardar como borrador.
Esto permite probar reglas, mantener la UI liviana y conservar trazabilidad.
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
from pypdf import PdfReader

from am_hub_fiscal import decimal_ar, es_nota_credito


CENTAVOS = Decimal("0.01")

CUENTA_COLUMNAS = [
    "id", "cliente", "codigo", "nombre", "tipo", "naturaleza", "activa",
    "origen", "fecha_actualizacion", "actualizado_por",
]

ASIENTO_COLUMNAS = [
    "id", "cliente", "periodo", "fecha", "tipo", "origen", "source_id",
    "descripcion", "estado", "observaciones", "fecha_carga", "creado_por",
    "fecha_autorizacion", "autorizado_por",
]

ASIENTO_LINEA_COLUMNAS = [
    "id", "asiento_id", "cliente", "periodo", "orden", "cuenta_codigo",
    "cuenta_nombre", "debe", "haber", "tercero_cuit", "tercero_nombre",
    "comprobante", "detalle",
]

BANCO_MOVIMIENTO_COLUMNAS = [
    "id", "cliente", "periodo", "cuenta_bancaria", "fecha", "descripcion",
    "referencia", "debito", "credito", "saldo", "source_hash",
    "cuenta_sugerida", "conciliado", "asiento_id", "archivo_nombre",
    "fecha_carga", "cargado_por",
]

SUELDO_COLUMNAS = [
    "id", "cliente", "periodo", "archivo_nombre", "remuneracion_bruta",
    "descuentos_aportes", "neto_sueldos", "contribuciones_patronales", "art",
    "otros_costos", "estado", "asiento_id", "observaciones", "fecha_carga",
    "cargado_por",
]

PERIODO_CONTABLE_COLUMNAS = [
    "id", "cliente", "periodo", "estado", "fecha_autorizacion",
    "autorizado_por", "observaciones", "fecha_actualizacion",
]

EJERCICIO_CONTABLE_COLUMNAS = [
    "id", "cliente", "ejercicio", "fecha_inicio", "fecha_cierre", "estado",
    "plan_cuentas_json", "fecha_apertura", "abierto_por", "fecha_cierre_real",
    "cerrado_por", "observaciones", "fecha_actualizacion",
]

ARCHIVO_CONTABLE_COLUMNAS = [
    "id", "cliente", "periodo", "categoria", "nombre", "tipo", "tamano",
    "sha256", "contenido_base64", "fecha_carga", "cargado_por",
]


# Plan mínimo. Es deliberadamente corto: cada cliente puede ampliarlo sin
# modificar las reglas del motor.
PLAN_CUENTAS_BASE = [
    ("1.1.01", "Caja", "Activo", "Deudora"),
    ("1.1.02", "Bancos", "Activo", "Deudora"),
    ("1.1.03", "Deudores por ventas", "Activo", "Deudora"),
    ("1.1.04", "IVA crédito fiscal", "Activo", "Deudora"),
    ("1.1.05", "IVA saldo técnico a favor", "Activo", "Deudora"),
    ("1.1.06", "IVA saldo de libre disponibilidad", "Activo", "Deudora"),
    ("1.1.07", "Retenciones y percepciones IIBB", "Activo", "Deudora"),
    ("1.1.08", "IIBB saldo a favor", "Activo", "Deudora"),
    ("1.1.09", "Anticipos y otros créditos fiscales", "Activo", "Deudora"),
    ("1.2.01", "Bienes de uso", "Activo", "Deudora"),
    ("2.1.01", "Proveedores", "Pasivo", "Acreedora"),
    ("2.1.02", "IVA débito fiscal", "Pasivo", "Acreedora"),
    ("2.1.03", "IVA a pagar", "Pasivo", "Acreedora"),
    ("2.1.04", "Ingresos Brutos a pagar", "Pasivo", "Acreedora"),
    ("2.1.05", "Sueldos a pagar", "Pasivo", "Acreedora"),
    ("2.1.06", "Cargas sociales a pagar", "Pasivo", "Acreedora"),
    ("2.1.07", "Otras obligaciones fiscales", "Pasivo", "Acreedora"),
    ("3.1.01", "Capital y resultados acumulados", "Patrimonio neto", "Acreedora"),
    ("4.1.01", "Ventas y servicios", "Ingresos", "Acreedora"),
    ("4.1.02", "Otros ingresos", "Ingresos", "Acreedora"),
    ("4.1.03", "Ventas no gravadas y exentas", "Ingresos", "Acreedora"),
    ("5.1.01", "Compras, gastos y servicios", "Egresos", "Deudora"),
    ("5.1.02", "Comisiones y gastos bancarios", "Egresos", "Deudora"),
    ("5.1.03", "Sueldos y jornales", "Egresos", "Deudora"),
    ("5.1.04", "Cargas sociales patronales", "Egresos", "Deudora"),
    ("5.1.05", "ART y otros costos laborales", "Egresos", "Deudora"),
    ("5.1.06", "Impuesto sobre los Ingresos Brutos", "Egresos", "Deudora"),
    ("5.9.99", "Diferencias de redondeo y clasificación", "Egresos", "Deudora"),
]

NOMBRES_CUENTAS = {codigo: nombre for codigo, nombre, _, _ in PLAN_CUENTAS_BASE}


def dinero(valor) -> Decimal:
    return decimal_ar(valor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def texto_simple(valor) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto.casefold()).strip()


def id_estable(prefijo: str, *partes) -> str:
    base = "|".join(str(p or "").strip().casefold() for p in partes)
    return f"{prefijo}-" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:28]


def plan_cuentas_inicial(cliente: str, usuario: str = "") -> pd.DataFrame:
    hoy = date.today().isoformat()
    return pd.DataFrame([
        {
            "id": id_estable("CTA", cliente, codigo),
            "cliente": cliente,
            "codigo": codigo,
            "nombre": nombre,
            "tipo": tipo,
            "naturaleza": naturaleza,
            "activa": "Sí",
            "origen": "Plan base AM HUB",
            "fecha_actualizacion": hoy,
            "actualizado_por": usuario,
        }
        for codigo, nombre, tipo, naturaleza in PLAN_CUENTAS_BASE
    ], columns=CUENTA_COLUMNAS)


def _linea(codigo, debe=0, haber=0, **extra) -> dict:
    return {
        "cuenta_codigo": str(codigo),
        "cuenta_nombre": NOMBRES_CUENTAS.get(str(codigo), ""),
        "debe": str(dinero(debe)),
        "haber": str(dinero(haber)),
        **extra,
    }


def _asiento(cliente, periodo, fecha, tipo, origen, source_id, descripcion,
             lineas, usuario="", observaciones="") -> tuple[dict, list[dict]]:
    asiento_id = id_estable("ASI", cliente, periodo, origen, source_id, tipo)
    total_debe = sum((dinero(l.get("debe", 0)) for l in lineas), Decimal("0"))
    total_haber = sum((dinero(l.get("haber", 0)) for l in lineas), Decimal("0"))
    diferencia = dinero(total_haber - total_debe)
    if diferencia > 0:
        lineas.append(_linea("5.9.99", debe=diferencia, detalle="Balanceo automático"))
    elif diferencia < 0:
        lineas.append(_linea("5.9.99", haber=-diferencia, detalle="Balanceo automático"))

    cabecera = {
        "id": asiento_id,
        "cliente": cliente,
        "periodo": periodo,
        "fecha": str(fecha or ""),
        "tipo": tipo,
        "origen": origen,
        "source_id": str(source_id or ""),
        "descripcion": descripcion,
        "estado": "Borrador",
        "observaciones": observaciones,
        "fecha_carga": pd.Timestamp.now(tz="America/Argentina/Buenos_Aires").isoformat(),
        "creado_por": usuario,
        "fecha_autorizacion": "",
        "autorizado_por": "",
    }
    salida = []
    for orden, linea in enumerate(lineas, start=1):
        salida.append({
            "id": id_estable("LIN", asiento_id, orden),
            "asiento_id": asiento_id,
            "cliente": cliente,
            "periodo": periodo,
            "orden": str(orden),
            "cuenta_codigo": linea.get("cuenta_codigo", ""),
            "cuenta_nombre": linea.get("cuenta_nombre", ""),
            "debe": str(dinero(linea.get("debe", 0))),
            "haber": str(dinero(linea.get("haber", 0))),
            "tercero_cuit": linea.get("tercero_cuit", ""),
            "tercero_nombre": linea.get("tercero_nombre", ""),
            "comprobante": linea.get("comprobante", ""),
            "detalle": linea.get("detalle", ""),
        })
    return cabecera, salida


def crear_asiento_manual(cliente: str, periodo: str, fecha: str, descripcion: str,
                         lineas: list[dict], usuario: str = "",
                         tipo: str = "Asiento manual") -> tuple[dict, list[dict]]:
    """Crea un asiento manual sin balanceo implícito.

    A diferencia de los importadores, un asiento escrito por una persona debe
    cuadrar por sí mismo: no se ocultan errores en diferencias de redondeo.
    """
    total_debe = sum((dinero(linea.get("debe", 0)) for linea in lineas), Decimal("0"))
    total_haber = sum((dinero(linea.get("haber", 0)) for linea in lineas), Decimal("0"))
    if not lineas or dinero(total_debe - total_haber) != Decimal("0.00"):
        raise ValueError("El asiento manual debe tener igual total en Debe y Haber.")
    source_id = id_estable("MAN", cliente, periodo, fecha, descripcion, pd.Timestamp.now().isoformat())
    # _asiento no agregará balanceo porque ya fue validado.
    return _asiento(
        cliente, periodo, fecha, tipo, "Carga manual", source_id,
        descripcion, lineas, usuario,
    )


def generar_asientos_comprobantes(movimientos: pd.DataFrame, cliente: str,
                                  periodo: str, usuario: str = "") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Genera un asiento por comprobante fiscal emitido/recibido."""
    cabeceras, lineas_salida = [], []
    if movimientos is None or movimientos.empty:
        return pd.DataFrame(columns=ASIENTO_COLUMNAS), pd.DataFrame(columns=ASIENTO_LINEA_COLUMNAS)

    for _, mov in movimientos.iterrows():
        if str(mov.get("impuesto", "")) != "IVA" or str(mov.get("clase", "")) not in {"emitido", "recibido"}:
            continue
        source_id = str(mov.get("id", ""))
        clase = str(mov.get("clase", ""))
        total = abs(dinero(mov.get("total", 0)))
        neto = abs(dinero(mov.get("neto_gravado", 0)))
        iva = abs(dinero(mov.get("iva", 0)))
        otros = abs(dinero(mov.get("otros_tributos", 0)))
        if total == 0:
            total = dinero(neto + iva + otros)
        if total == 0:
            continue
        es_nc = es_nota_credito(mov.get("tipo_comprobante", ""))
        comprobante = "-".join(filter(None, [
            str(mov.get("tipo_comprobante", "")).strip(),
            str(mov.get("punto_venta", "")).strip(),
            str(mov.get("numero", "")).strip(),
        ]))
        tercero = {
            "tercero_cuit": str(mov.get("cuit_contraparte", "")),
            "tercero_nombre": str(mov.get("denominacion", "")),
            "comprobante": comprobante,
        }
        if clase == "emitido":
            residual = max(dinero(total - neto - iva - otros), Decimal("0"))
            base = [
                _linea("1.1.03", debe=total, **tercero),
                _linea("4.1.01", haber=neto, **tercero),
            ]
            if iva:
                base.append(_linea("2.1.02", haber=iva, **tercero))
            if otros:
                base.append(_linea("2.1.07", haber=otros, **tercero))
            if residual:
                base.append(_linea("4.1.03", haber=residual, **tercero))
            tipo = "Nota de crédito de venta" if es_nc else "Venta"
        else:
            residual = max(dinero(total - neto - iva - otros), Decimal("0"))
            base = [
                _linea("5.1.01", debe=neto, **tercero),
            ]
            if iva:
                base.append(_linea("1.1.04", debe=iva, **tercero))
            if otros:
                base.append(_linea("5.1.01", debe=otros, **tercero))
            if residual:
                base.append(_linea("5.1.01", debe=residual, **tercero))
            base.append(_linea("2.1.01", haber=total, **tercero))
            tipo = "Nota de crédito de compra" if es_nc else "Compra"
        if es_nc:
            base = [
                {**linea, "debe": linea.get("haber", "0"), "haber": linea.get("debe", "0")}
                for linea in base
            ]
        cabecera, detalle = _asiento(
            cliente, periodo, mov.get("fecha", ""), tipo, "Comprobante fiscal",
            source_id, f"{tipo}: {comprobante or tercero['tercero_nombre']}", base, usuario,
        )
        cabeceras.append(cabecera)
        lineas_salida.extend(detalle)
    return (
        pd.DataFrame(cabeceras, columns=ASIENTO_COLUMNAS),
        pd.DataFrame(lineas_salida, columns=ASIENTO_LINEA_COLUMNAS),
    )


def generar_asientos_impuestos(registro: dict, cliente: str, periodo: str,
                               usuario: str = "") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Genera liquidaciones mensuales de IVA e IIBB desde el papel guardado."""
    cabeceras, lineas_salida = [], []
    debito = dinero(registro.get("iva_debito", 0))
    credito = dinero(registro.get("iva_credito", 0))
    tecnico_anterior = dinero(registro.get("iva_saldo_tecnico_anterior", 0))
    tecnico_final = dinero(registro.get("iva_saldo_tecnico_favor", 0))
    iva_pagar = dinero(registro.get("iva_saldo_pagar", 0))
    uso_libre = dinero(registro.get("iva_uso_libre", 0))
    fecha = str(registro.get("fecha_vencimiento_iva", "")) or f"{periodo}-28"
    if any([debito, credito, tecnico_anterior, tecnico_final, iva_pagar, uso_libre]):
        lineas = []
        if debito:
            lineas.append(_linea("2.1.02", debe=debito))
        if credito:
            lineas.append(_linea("1.1.04", haber=credito))
        tecnico_consumido = min(tecnico_anterior, max(debito - credito, Decimal("0")))
        if tecnico_consumido:
            lineas.append(_linea("1.1.05", haber=tecnico_consumido))
        if tecnico_final:
            lineas.append(_linea("1.1.05", debe=tecnico_final))
        bruto_pagar = dinero(iva_pagar + uso_libre)
        if bruto_pagar:
            lineas.append(_linea("2.1.03", haber=bruto_pagar))
        if uso_libre:
            lineas.extend([
                _linea("2.1.03", debe=uso_libre),
                _linea("1.1.06", haber=uso_libre),
            ])
        cab, det = _asiento(
            cliente, periodo, fecha, "Liquidación IVA", "Papel de trabajo fiscal",
            registro.get("id", periodo) + "-IVA", f"Liquidación IVA {periodo}", lineas, usuario,
        )
        cabeceras.append(cab); lineas_salida.extend(det)

    determinado = dinero(registro.get("iibb_determinado", 0))
    saldo_pagar = dinero(registro.get("iibb_saldo_pagar", 0))
    saldo_favor = dinero(registro.get("iibb_saldo_favor", 0))
    creditos = dinero(registro.get("iibb_retenciones", 0)) + dinero(registro.get("iibb_percepciones", 0))
    fecha_iibb = str(registro.get("fecha_vencimiento_iibb", "")) or f"{periodo}-28"
    if any([determinado, saldo_pagar, saldo_favor, creditos]):
        lineas = []
        if determinado:
            lineas.extend([
                _linea("5.1.06", debe=determinado),
                _linea("2.1.04", haber=determinado),
            ])
        aplicado = min(determinado, max(creditos, Decimal("0")))
        if aplicado:
            lineas.extend([
                _linea("2.1.04", debe=aplicado),
                _linea("1.1.07", haber=aplicado),
            ])
        if saldo_favor and saldo_favor > max(creditos - determinado, Decimal("0")):
            diferencia = dinero(saldo_favor - max(creditos - determinado, Decimal("0")))
            lineas.extend([
                _linea("1.1.08", debe=diferencia),
                _linea("2.1.04", haber=diferencia),
            ])
        cab, det = _asiento(
            cliente, periodo, fecha_iibb, "Liquidación IIBB", "Papel de trabajo fiscal",
            registro.get("id", periodo) + "-IIBB", f"Liquidación IIBB {periodo}", lineas, usuario,
        )
        cabeceras.append(cab); lineas_salida.extend(det)
    return (
        pd.DataFrame(cabeceras, columns=ASIENTO_COLUMNAS),
        pd.DataFrame(lineas_salida, columns=ASIENTO_LINEA_COLUMNAS),
    )


def _leer_tabla(contenido: bytes, nombre: str) -> pd.DataFrame:
    if str(nombre).casefold().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(contenido))
    ultimo_error = None
    for encoding in ("utf-8-sig", "latin-1", "cp1252"):
        for sep in (None, ";", ",", "\t"):
            try:
                return pd.read_csv(io.BytesIO(contenido), encoding=encoding, sep=sep, engine="python")
            except Exception as exc:
                ultimo_error = exc
    raise ValueError(f"No se pudo leer el extracto: {ultimo_error}")


def parsear_extracto_bancario(contenido: bytes, nombre: str, cliente: str,
                              cuenta_bancaria: str, usuario: str = "") -> pd.DataFrame:
    """Normaliza CSV/XLSX bancarios con encabezados habituales."""
    tabla = _leer_tabla(contenido, nombre).fillna("")
    tabla.columns = [texto_simple(c) for c in tabla.columns]

    def columna(*alias):
        for candidato in alias:
            candidato = texto_simple(candidato)
            if candidato in tabla.columns:
                return candidato
        for existente in tabla.columns:
            if any(texto_simple(a) in existente for a in alias):
                return existente
        return ""

    c_fecha = columna("fecha", "fecha movimiento", "fecha operacion")
    c_desc = columna("descripcion", "concepto", "detalle", "movimiento")
    c_ref = columna("referencia", "comprobante", "numero")
    c_debito = columna("debito", "debe", "egreso", "retiro")
    c_credito = columna("credito", "haber", "ingreso", "deposito")
    c_importe = columna("importe", "monto")
    c_saldo = columna("saldo")
    if not c_fecha or not (c_debito or c_credito or c_importe):
        raise ValueError("No se identificaron las columnas de fecha e importe del extracto.")

    filas = []
    for _, fila in tabla.iterrows():
        fecha_dt = pd.to_datetime(fila.get(c_fecha, ""), errors="coerce", dayfirst=True)
        if pd.isna(fecha_dt):
            continue
        debito = abs(dinero(fila.get(c_debito, 0))) if c_debito else Decimal("0")
        credito = abs(dinero(fila.get(c_credito, 0))) if c_credito else Decimal("0")
        if c_importe and not (debito or credito):
            importe = dinero(fila.get(c_importe, 0))
            if importe < 0:
                debito = -importe
            else:
                credito = importe
        if not (debito or credito):
            continue
        descripcion = str(fila.get(c_desc, "")).strip() if c_desc else ""
        referencia = str(fila.get(c_ref, "")).strip() if c_ref else ""
        periodo = fecha_dt.strftime("%Y-%m")
        hash_mov = id_estable(
            "BMOV", cliente, cuenta_bancaria, fecha_dt.date().isoformat(),
            descripcion, referencia, debito, credito,
        )
        filas.append({
            "id": hash_mov,
            "cliente": cliente,
            "periodo": periodo,
            "cuenta_bancaria": cuenta_bancaria,
            "fecha": fecha_dt.date().isoformat(),
            "descripcion": descripcion,
            "referencia": referencia,
            "debito": str(debito),
            "credito": str(credito),
            "saldo": str(dinero(fila.get(c_saldo, 0))) if c_saldo else "",
            "source_hash": hash_mov,
            "cuenta_sugerida": sugerir_cuenta_bancaria(descripcion, debito, credito),
            "conciliado": "No",
            "asiento_id": "",
            "archivo_nombre": nombre,
            "fecha_carga": pd.Timestamp.now(tz="America/Argentina/Buenos_Aires").isoformat(),
            "cargado_por": usuario,
        })
    return pd.DataFrame(filas, columns=BANCO_MOVIMIENTO_COLUMNAS)


def sugerir_cuenta_bancaria(descripcion: str, debito=0, credito=0) -> str:
    texto = texto_simple(descripcion)
    reglas = [
        (("comision", "mantenimiento", "gasto bancario", "impuesto ley 25413"), "5.1.02"),
        (("sueldo", "haberes", "nomina"), "2.1.05"),
        (("arca", "afip", "vep", "iva"), "2.1.03"),
        (("agip", "arba", "iibb", "sircreb"), "2.1.04"),
        (("proveedor",), "2.1.01"),
        (("cobro", "cliente"), "1.1.03"),
    ]
    for palabras, codigo in reglas:
        if any(p in texto for p in palabras):
            return codigo
    return "2.1.01" if dinero(debito) else "1.1.03"


def generar_asiento_banco(movimiento: dict, cuenta_contrapartida: str,
                          usuario: str = "") -> tuple[dict, list[dict]]:
    debito, credito = dinero(movimiento.get("debito", 0)), dinero(movimiento.get("credito", 0))
    importe = debito or credito
    if not importe:
        raise ValueError("El movimiento bancario no tiene importe.")
    if debito:
        lineas = [_linea(cuenta_contrapartida, debe=importe), _linea("1.1.02", haber=importe)]
    else:
        lineas = [_linea("1.1.02", debe=importe), _linea(cuenta_contrapartida, haber=importe)]
    return _asiento(
        movimiento.get("cliente", ""), movimiento.get("periodo", ""),
        movimiento.get("fecha", ""), "Movimiento bancario", "Extracto bancario",
        movimiento.get("id", ""), movimiento.get("descripcion", "Movimiento bancario"),
        lineas, usuario, movimiento.get("referencia", ""),
    )


def generar_asiento_sueldos(registro: dict, usuario: str = "") -> tuple[dict, list[dict]]:
    bruto = dinero(registro.get("remuneracion_bruta", 0))
    descuentos = dinero(registro.get("descuentos_aportes", 0))
    neto = dinero(registro.get("neto_sueldos", 0))
    contribuciones = dinero(registro.get("contribuciones_patronales", 0))
    art = dinero(registro.get("art", 0))
    otros = dinero(registro.get("otros_costos", 0))
    if not neto:
        neto = max(bruto - descuentos, Decimal("0"))
    if not bruto:
        bruto = dinero(neto + descuentos)
    lineas = [
        _linea("5.1.03", debe=bruto),
        _linea("2.1.05", haber=neto),
    ]
    cargas = dinero(descuentos + contribuciones + art + otros)
    if contribuciones:
        lineas.append(_linea("5.1.04", debe=contribuciones))
    if art + otros:
        lineas.append(_linea("5.1.05", debe=art + otros))
    if cargas:
        lineas.append(_linea("2.1.06", haber=cargas))
    return _asiento(
        registro.get("cliente", ""), registro.get("periodo", ""),
        f"{registro.get('periodo', '')}-28", "Devengamiento de sueldos",
        "Sueldos y F.931", registro.get("id", ""),
        f"Sueldos y cargas sociales {registro.get('periodo', '')}", lineas, usuario,
        registro.get("observaciones", ""),
    )


def extraer_totales_f931(contenido: bytes) -> dict:
    """Extrae los totales contables disponibles en un F.931 oficial.

    El neto de sueldos no forma parte del formulario y queda para completar con
    el resumen de liquidación. Los campos no reconocidos se devuelven en cero.
    """
    try:
        texto = "\n".join(
            pagina.extract_text() or ""
            for pagina in PdfReader(io.BytesIO(contenido)).pages
        )
    except Exception as exc:
        raise ValueError(f"No se pudo leer el PDF del F.931: {exc}") from exc

    def importe(patron: str) -> Decimal:
        coincidencias = re.findall(patron, texto, flags=re.IGNORECASE)
        if not coincidencias:
            return Decimal("0.00")
        valor = coincidencias[-1]
        if isinstance(valor, tuple):
            valor = next((item for item in valor if item), "0")
        return dinero(valor)

    periodo_match = re.search(r"(0[1-9]|1[0-2])\s*/\s*(20\d{2})", texto)
    periodo = f"{periodo_match.group(2)}-{periodo_match.group(1)}" if periodo_match else ""
    aportes_ss = importe(r"Total de aportes S\.S\.\s*([\d.,]+)")
    aportes_os = importe(r"Total de aportes O\.S\.\s*([\d.,]+)")
    contrib_ss = importe(r"Contribuciones S\.S\. a pagar\s*([\d.,]+)")
    contrib_os = importe(r"Contribuciones O\.S\. a pagar\s*([\d.,]+)")
    art = importe(r"L\.R\.T\. total a pagar\s*([\d.,]+)")
    seguro = importe(r"S\.C\.V\.O\. a Pagar:\s*([\d.,]+)")
    return {
        "periodo": periodo,
        "remuneracion_bruta": str(importe(r"Suma de Rem\. 1:\s*([\d.,]+)")),
        "descuentos_aportes": str(dinero(aportes_ss + aportes_os)),
        "neto_sueldos": "0.00",
        "contribuciones_patronales": str(dinero(contrib_ss + contrib_os)),
        "art": str(art),
        "otros_costos": str(seguro),
        "empleados": str(re.search(r"Empleados en n[oó]mina:\s*(\d+)", texto, re.IGNORECASE).group(1))
        if re.search(r"Empleados en n[oó]mina:\s*(\d+)", texto, re.IGNORECASE) else "",
    }


def validar_asientos(asientos: pd.DataFrame, lineas: pd.DataFrame) -> pd.DataFrame:
    if asientos is None or asientos.empty:
        return pd.DataFrame(columns=["asiento_id", "debe", "haber", "diferencia", "balanceado"])
    detalle = lineas.copy() if lineas is not None else pd.DataFrame(columns=ASIENTO_LINEA_COLUMNAS)
    detalle["debe_num"] = detalle.get("debe", pd.Series(dtype=str)).apply(dinero)
    detalle["haber_num"] = detalle.get("haber", pd.Series(dtype=str)).apply(dinero)
    totales = detalle.groupby("asiento_id", as_index=False).agg(
        debe=("debe_num", "sum"), haber=("haber_num", "sum"),
    )
    totales["diferencia"] = totales.apply(lambda f: dinero(f["debe"] - f["haber"]), axis=1)
    totales["balanceado"] = totales["diferencia"].eq(Decimal("0.00"))
    return totales


def balance_sumas_saldos(lineas: pd.DataFrame, cuentas: pd.DataFrame | None = None) -> pd.DataFrame:
    columnas = ["codigo", "cuenta", "debe", "haber", "saldo_deudor", "saldo_acreedor"]
    if lineas is None or lineas.empty:
        return pd.DataFrame(columns=columnas)
    base = lineas.copy()
    base["debe_num"] = base["debe"].apply(dinero)
    base["haber_num"] = base["haber"].apply(dinero)
    agrupado = base.groupby(["cuenta_codigo", "cuenta_nombre"], as_index=False).agg(
        debe=("debe_num", "sum"), haber=("haber_num", "sum"),
    )
    agrupado["saldo_deudor"] = agrupado.apply(lambda f: max(dinero(f["debe"] - f["haber"]), Decimal("0")), axis=1)
    agrupado["saldo_acreedor"] = agrupado.apply(lambda f: max(dinero(f["haber"] - f["debe"]), Decimal("0")), axis=1)
    return agrupado.rename(columns={"cuenta_codigo": "codigo", "cuenta_nombre": "cuenta"})[columnas]
