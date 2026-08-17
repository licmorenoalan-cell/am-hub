"""Motor fiscal aislado de Streamlit para AM Hub.

Los importadores aceptan los formatos habituales de ARCA y AGIP y devuelven
movimientos normalizados. Mantener este módulo separado evita cargar archivos o
dependencias pesadas durante la navegación normal de la aplicación.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import pandas as pd


MOVIMIENTO_COLUMNAS = [
    "id", "periodo_id", "cliente", "periodo", "archivo_id", "origen",
    "impuesto", "clase", "fecha", "tipo_comprobante", "punto_venta",
    "numero", "cuit_contraparte", "denominacion", "neto_gravado", "iva",
    "otros_tributos", "total", "importe", "base_calculo", "regimen",
    "computado", "observacion",
]

CENTAVOS = Decimal("0.01")


def decimal_ar(valor) -> Decimal:
    """Convierte números argentinos, anglosajones y valores de pandas."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return Decimal("0")
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))

    texto = re.sub(r"[^0-9,.-]", "", str(valor).strip())
    if not texto or texto in {"-", ".", ","}:
        return Decimal("0")
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return Decimal("0")


def dinero(valor) -> Decimal:
    return decimal_ar(valor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def normalizar_cuit(valor: str) -> str:
    digitos = re.sub(r"\D", "", str(valor or ""))
    if len(digitos) == 11:
        return f"{digitos[:2]}-{digitos[2:10]}-{digitos[10]}"
    return str(valor or "").strip()


def periodo_desde_fecha(valor: str) -> str:
    fecha = pd.to_datetime(valor, errors="coerce", dayfirst=True)
    return "" if pd.isna(fecha) else fecha.strftime("%Y-%m")


def _texto(contenido: bytes) -> str:
    for encoding in ("utf-8-sig", "latin-1", "cp1252"):
        try:
            return contenido.decode(encoding)
        except UnicodeDecodeError:
            continue
    return contenido.decode("utf-8", errors="replace")


def _valor(fila: pd.Series, *nombres: str):
    for nombre in nombres:
        if nombre in fila.index:
            return fila.get(nombre, "")
    return ""


def _id_movimiento(*partes) -> str:
    base = "|".join(str(parte or "").strip().casefold() for parte in partes)
    return "FMOV-" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:28]


def _movimiento_base(**cambios) -> dict:
    registro = {col: "" for col in MOVIMIENTO_COLUMNAS}
    registro.update({"computado": "Sí", **cambios})
    return registro


def parsear_comprobantes_arca(contenido: bytes, clase: str) -> pd.DataFrame:
    texto = _texto(contenido)
    df = pd.read_csv(io.StringIO(texto), sep=";", dtype=str).fillna("")
    if "Fecha de Emisión" not in df.columns:
        raise ValueError("El archivo no tiene el encabezado de Mis Comprobantes.")

    recibidos = clase == "recibido"
    registros = []
    for _, fila in df.iterrows():
        fecha = str(_valor(fila, "Fecha de Emisión"))
        tipo = str(_valor(fila, "Tipo de Comprobante"))
        punto = str(_valor(fila, "Punto de Venta"))
        numero = str(_valor(fila, "Número Desde"))
        cuit = str(_valor(
            fila,
            "Nro. Doc. Emisor" if recibidos else "Nro. Doc. Receptor",
        ))
        denominacion = str(_valor(
            fila,
            "Denominación Emisor" if recibidos else "Denominación Receptor",
        ))
        iva = dinero(_valor(fila, "Total IVA"))
        neto = dinero(_valor(fila, "Imp. Neto Gravado Total"))
        otros = dinero(_valor(fila, "Otros Tributos"))
        total = dinero(_valor(fila, "Imp. Total"))
        registro = _movimiento_base(
            id=_id_movimiento(
                "ARCA", clase, fecha, tipo, punto, numero, cuit, total,
            ),
            origen="ARCA Mis Comprobantes",
            impuesto="IVA",
            clase=clase,
            fecha=fecha,
            tipo_comprobante=tipo,
            punto_venta=punto,
            numero=numero,
            cuit_contraparte=normalizar_cuit(cuit),
            denominacion=denominacion,
            neto_gravado=f"{neto:.2f}",
            iva=f"{iva:.2f}",
            otros_tributos=f"{otros:.2f}",
            total=f"{total:.2f}",
            importe=f"{iva:.2f}",
            base_calculo=f"{neto:.2f}",
        )
        registros.append(registro)
    return pd.DataFrame(registros, columns=MOVIMIENTO_COLUMNAS)


def parsear_comprobantes_arca_xlsx(contenido: bytes, clase: str) -> pd.DataFrame:
    # Las descargas de ARCA incluyen una fila de título antes del encabezado.
    vista = pd.read_excel(io.BytesIO(contenido), header=None, nrows=5)
    header_row = 0
    for indice, fila in vista.iterrows():
        if any(str(valor).strip() == "Fecha de Emisión" for valor in fila.tolist()):
            header_row = int(indice)
            break
    df = pd.read_excel(io.BytesIO(contenido), header=header_row, dtype=str).fillna("")
    salida = io.StringIO()
    df.to_csv(salida, index=False, sep=";")
    return parsear_comprobantes_arca(salida.getvalue().encode("utf-8"), clase)


def parsear_agip_tabular(contenido: bytes) -> tuple[str, pd.DataFrame]:
    texto = _texto(contenido).replace("N�", "N°")
    lineas = texto.splitlines()
    inicio = next(
        (i for i, linea in enumerate(lineas) if linea.strip().startswith("CUIT,")),
        None,
    )
    if inicio is None:
        raise ValueError("No se encontró el encabezado de retenciones/percepciones AGIP.")
    df = pd.read_csv(
        io.StringIO("\n".join(lineas[inicio:])),
        dtype=str,
        index_col=False,
    ).fillna("")
    es_retencion = any("Retencion" in col for col in df.columns)
    clase = "retencion" if es_retencion else "percepcion"
    fecha_col = next(col for col in df.columns if "Fecha Retencion" in col or "Fecha Percepcion" in col)
    importe_col = "Monto Retenido" if es_retencion else "Monto Percibido"
    registros = []
    for _, fila in df.iterrows():
        fecha = str(fila.get(fecha_col, ""))
        cuit = str(fila.get("CUIT", ""))
        certificado = str(_valor(fila, "N° Certificado", "Nº Certificado", "N Certificado"))
        comprobante = str(_valor(fila, "N° Comprobante", "Nº Comprobante", "N Comprobante"))
        importe = dinero(fila.get(importe_col, ""))
        base = dinero(fila.get("Base Calculo", ""))
        registros.append(_movimiento_base(
            id=_id_movimiento("AGIP", clase, fecha, cuit, certificado, comprobante, importe),
            origen="AGIP Rentas Ciudad",
            impuesto="IIBB",
            clase=clase,
            fecha=fecha,
            numero=certificado or comprobante,
            cuit_contraparte=normalizar_cuit(cuit),
            denominacion=str(fila.get("Razon Social", "")),
            importe=f"{importe:.2f}",
            base_calculo=f"{base:.2f}",
            regimen=str(fila.get("Norma", "")),
        ))
    return clase, pd.DataFrame(registros, columns=MOVIMIENTO_COLUMNAS)


def parsear_percepciones_iva(contenido: bytes) -> pd.DataFrame:
    df = pd.read_csv(
        io.StringIO(_texto(contenido)), sep=";", header=None, dtype=str,
        names=["regimen", "cuit", "extra", "fecha", "tipo", "numero", "importe"],
    ).fillna("")
    registros = []
    for _, fila in df.iterrows():
        importe = dinero(fila["importe"])
        registros.append(_movimiento_base(
            id=_id_movimiento(
                "ARCA_PER", fila["regimen"], fila["cuit"], fila["fecha"],
                fila["tipo"], fila["numero"], importe,
            ),
            origen="ARCA Mis Retenciones",
            impuesto="IVA",
            clase="percepcion",
            fecha=fila["fecha"],
            tipo_comprobante=fila["tipo"],
            numero=fila["numero"],
            cuit_contraparte=normalizar_cuit(fila["cuit"]),
            importe=f"{importe:.2f}",
            regimen=fila["regimen"],
        ))
    return pd.DataFrame(registros, columns=MOVIMIENTO_COLUMNAS)


def extraer_perfil_constancia_pdf(contenido: bytes) -> dict[str, str]:
    """Extrae datos básicos de constancias ARCA/AGIP sin bloquear si son imágenes."""
    try:
        from pypdf import PdfReader

        lector = PdfReader(io.BytesIO(contenido))
        texto = "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
    except Exception:
        return {}
    if not texto.strip():
        return {}

    perfil: dict[str, str] = {}
    cuit = re.search(r"\b(\d{2}-\d{8}-\d)\b", texto)
    if cuit:
        perfil["cuit"] = cuit.group(1)
    razon_arca = re.search(r"CONSTANCIA DE INSCRIPCION\s+(.+?)\s+CUIT:", texto, re.I)
    razon_agip = re.search(r"Apellido y Nombre / Razón Social\s*\n([^\n]+)", texto, re.I)
    if razon_arca or razon_agip:
        perfil["razon_social"] = (razon_arca or razon_agip).group(1).strip()
    actividad = re.search(r"Actividad principal:\s*(\d{6})", texto, re.I)
    if not actividad:
        actividad = re.search(r"\b(\d{6})\s+.+?PrincipalActividad", texto, re.I)
    if actividad:
        perfil["actividad_principal"] = actividad.group(1)
    actividades = re.findall(r"\b(\d{6})\b", texto)
    if actividades:
        perfil["actividades"] = ", ".join(dict.fromkeys(actividades))
    inscripcion = re.search(r"ISIB-RG\s+\d{2}/\d{2}/\d{4}\s+\d{2}/\d{2}/\d{4}\s+([\d\s-]+)", texto, re.I)
    if inscripcion:
        perfil.update(
            iibb_regimen="Local",
            iibb_jurisdiccion="AGIP - CABA",
            iibb_inscripcion=re.sub(r"\s+", "", inscripcion.group(1)),
        )
    if re.search(r"IVA\s+\d{2}-\d{4}\b", texto):
        perfil["condicion_iva"] = "Responsable inscripto"
    return perfil


def analizar_archivo_fiscal(nombre: str, contenido: bytes) -> dict:
    """Clasifica un archivo fiscal y extrae movimientos cuando corresponde."""
    nombre_bajo = Path(nombre).name.casefold()
    resultado = {
        "categoria": "respaldo",
        "familia": "respaldo",
        "prioridad": 0,
        "movimientos": pd.DataFrame(columns=MOVIMIENTO_COLUMNAS),
        "advertencias": [],
        "perfil": {},
    }

    if zipfile.is_zipfile(io.BytesIO(contenido)):
        with zipfile.ZipFile(io.BytesIO(contenido)) as archivo_zip:
            miembros = [n for n in archivo_zip.namelist() if n.casefold().endswith(".csv")]
            if not miembros:
                resultado["advertencias"].append("El ZIP no contiene un CSV compatible.")
                return resultado
            interno = miembros[0]
            resultado = analizar_archivo_fiscal(interno, archivo_zip.read(interno))
            resultado["prioridad"] = max(100, int(resultado["prioridad"]))
            return resultado

    if nombre_bajo.endswith(".pdf"):
        resultado["perfil"] = extraer_perfil_constancia_pdf(contenido)
        if "2051" in nombre_bajo or "iva" in nombre_bajo:
            resultado.update(categoria="ddjj_iva", familia="ddjj_iva")
        elif "iibb" in nombre_bajo or "ddjjpresentacion" in nombre_bajo:
            resultado.update(categoria="ddjj_iibb", familia="ddjj_iibb")
        elif "agip" in nombre_bajo or "ingresos brutos" in nombre_bajo:
            resultado.update(categoria="constancia_iibb", familia="constancia_iibb")
        elif "constancia" in nombre_bajo:
            resultado.update(categoria="constancia_arca", familia="constancia_arca")
        elif "vep" in nombre_bajo:
            resultado.update(categoria="vep", familia="vep")
        return resultado

    texto_inicial = _texto(contenido[:10000])
    es_emitido = "emitid" in nombre_bajo
    es_recibido = "recibid" in nombre_bajo

    if "Fecha de Emisión" in texto_inicial and ";" in texto_inicial:
        if es_recibido:
            clase = "recibido"
        elif es_emitido:
            clase = "emitido"
        else:
            encabezado = texto_inicial.splitlines()[0]
            clase = "recibido" if "Nro. Doc. Emisor" in encabezado else "emitido"
        resultado.update(
            categoria=f"comprobantes_{clase}s",
            familia=f"comprobantes_{clase}s",
            prioridad=90,
            movimientos=parsear_comprobantes_arca(contenido, clase),
        )
        return resultado

    if nombre_bajo.endswith(".xlsx"):
        clase = "emitido" if es_emitido else "recibido"
        resultado.update(
            categoria=f"comprobantes_{clase}s",
            familia=f"comprobantes_{clase}s",
            prioridad=80,
            movimientos=parsear_comprobantes_arca_xlsx(contenido, clase),
        )
        return resultado

    if "Fecha Retencion" in texto_inicial or "Fecha Percepcion" in texto_inicial:
        clase, movimientos = parsear_agip_tabular(contenido)
        resultado.update(
            categoria=f"{clase}es_iibb" if clase == "retencion" else "percepciones_iibb",
            familia=f"{clase}es_iibb" if clase == "retencion" else "percepciones_iibb",
            prioridad=100,
            movimientos=movimientos,
        )
        return resultado

    primera = next((linea for linea in texto_inicial.splitlines() if linea.strip()), "")
    if primera.count(";") == 6:
        resultado.update(
            categoria="percepciones_iva",
            familia="percepciones_iva",
            prioridad=100,
            movimientos=parsear_percepciones_iva(contenido),
        )
        return resultado

    # Los TXT para SIFERE/e-SICOL se conservan como respaldo de importación. El
    # archivo tabular de AGIP es la fuente auditable para evitar duplicaciones.
    if nombre_bajo.endswith(".txt") and ("retencion" in nombre_bajo or "percepcion" in nombre_bajo):
        clase = "retenciones" if "retencion" in nombre_bajo else "percepciones"
        resultado.update(
            categoria=f"{clase}_iibb_importacion",
            familia=f"{clase}_iibb",
            prioridad=10,
        )
        resultado["advertencias"].append(
            "Se guardó como respaldo. Para calcular automáticamente, cargá también el detalle XLS/CSV de AGIP."
        )
    return resultado


def seleccionar_fuentes_calculo(analisis: list[dict]) -> set[int]:
    """Elige una fuente por familia para no duplicar XLSX/CSV/PDF equivalentes."""
    elegidos: set[int] = set()
    por_familia: dict[str, list[tuple[int, dict]]] = {}
    for indice, item in enumerate(analisis):
        if item.get("movimientos") is None or item["movimientos"].empty:
            continue
        por_familia.setdefault(str(item.get("familia", "")), []).append((indice, item))
    for items in por_familia.values():
        indice, _ = max(items, key=lambda par: int(par[1].get("prioridad", 0)))
        elegidos.add(indice)
    return elegidos


def resumir_movimientos(movimientos: pd.DataFrame) -> dict[str, Decimal]:
    if movimientos is None or movimientos.empty:
        movimientos = pd.DataFrame(columns=MOVIMIENTO_COLUMNAS)

    def total(columna: str, mascara) -> Decimal:
        if columna not in movimientos.columns:
            return Decimal("0.00")
        valores = movimientos.loc[mascara, columna].apply(decimal_ar)
        return dinero(sum(valores, Decimal("0")))

    impuesto = movimientos.get("impuesto", pd.Series("", index=movimientos.index)).astype(str)
    clase = movimientos.get("clase", pd.Series("", index=movimientos.index)).astype(str)
    computado = movimientos.get("computado", pd.Series("Sí", index=movimientos.index)).astype(str).str.casefold().isin(["sí", "si", "true", "1"])
    iva = impuesto.eq("IVA")
    iibb = impuesto.eq("IIBB")
    return {
        "ventas_neto": total("neto_gravado", iva & clase.eq("emitido")),
        "iva_debito": total("iva", iva & clase.eq("emitido")),
        "compras_neto": total("neto_gravado", iva & clase.eq("recibido")),
        "iva_credito": total("iva", iva & clase.eq("recibido")),
        "iva_percepciones": total("importe", iva & clase.eq("percepcion") & computado),
        "iibb_retenciones": total("importe", iibb & clase.eq("retencion") & computado),
        "iibb_percepciones": total("importe", iibb & clase.eq("percepcion") & computado),
    }


def calcular_iva(
    debito, credito, saldo_tecnico_anterior=0, saldo_libre_anterior=0,
    percepciones_retenciones=0, ajustes=0, uso_libre_disponibilidad=0,
) -> dict[str, Decimal]:
    debito, credito = dinero(debito), dinero(credito)
    tecnico_anterior = dinero(saldo_tecnico_anterior)
    libre_anterior = dinero(saldo_libre_anterior)
    deducciones = dinero(percepciones_retenciones) + dinero(ajustes)
    determinado = dinero(debito - credito)
    saldo_tecnico_favor = dinero(max(tecnico_anterior + credito - debito, Decimal("0")))
    saldo_antes_libre = dinero(max(debito - credito - tecnico_anterior, Decimal("0")))
    uso_libre = dinero(min(max(dinero(uso_libre_disponibilidad), Decimal("0")), libre_anterior + deducciones, saldo_antes_libre))
    return {
        "debito_fiscal": debito,
        "credito_fiscal": credito,
        "saldo_tecnico_anterior": tecnico_anterior,
        "resultado_periodo": determinado,
        "saldo_tecnico_favor": saldo_tecnico_favor,
        "saldo_libre_anterior": libre_anterior,
        "retenciones_percepciones": deducciones,
        "uso_libre_disponibilidad": uso_libre,
        "saldo_libre_favor": dinero(libre_anterior + deducciones - uso_libre),
        "saldo_pagar": dinero(saldo_antes_libre - uso_libre),
    }


def calcular_iibb(
    base_imponible, alicuota, retenciones=0, percepciones=0,
    saldo_favor_anterior=0, otros_creditos=0, ajustes=0,
) -> dict[str, Decimal]:
    base = dinero(base_imponible)
    tasa = decimal_ar(alicuota)
    determinado = dinero(base * tasa / Decimal("100"))
    creditos = dinero(retenciones) + dinero(percepciones) + dinero(saldo_favor_anterior) + dinero(otros_creditos) + dinero(ajustes)
    diferencia = dinero(determinado - creditos)
    return {
        "base_imponible": base,
        "alicuota": tasa,
        "impuesto_determinado": determinado,
        "creditos": creditos,
        "saldo_pagar": dinero(max(diferencia, Decimal("0"))),
        "saldo_favor": dinero(max(-diferencia, Decimal("0"))),
    }
