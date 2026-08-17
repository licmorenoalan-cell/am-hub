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
CUATRO_DECIMALES = Decimal("0.0001")


def es_nota_credito(tipo_comprobante) -> bool:
    """Reconoce notas de crédito ARCA por código o descripción."""
    texto = str(tipo_comprobante or "").strip().casefold()
    codigo = re.match(r"\d+", texto)
    return bool(
        (codigo and int(codigo.group()) in {3, 8, 13, 21, 53, 203, 208, 213})
        or "nota de cr" in texto
    )


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


def periodo_aplicacion_cm05(periodo: str) -> str:
    """Año de coeficientes a usar bajo el circuito enero-marzo/ajuste abril."""
    coincidencia = re.fullmatch(r"(20\d{2})-(0[1-9]|1[0-2])", str(periodo or ""))
    if not coincidencia:
        return ""
    anio, mes = int(coincidencia.group(1)), int(coincidencia.group(2))
    return str(anio if mes >= 4 else anio - 1)


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
        if any(str(valor).strip() in {"Fecha", "Fecha de Emisión"} for valor in fila.tolist()):
            header_row = int(indice)
            break
    df = pd.read_excel(io.BytesIO(contenido), header=header_row, dtype=str).fillna("")
    df = df.rename(columns={
        "Fecha": "Fecha de Emisión",
        "Tipo": "Tipo de Comprobante",
        "Neto Gravado Total": "Imp. Neto Gravado Total",
    })
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
    razon_cm = re.search(r"Apellido y Nombres o Razón Social\s*\n\s*([^\n]+)", texto, re.I)
    if razon_arca or razon_agip or razon_cm:
        perfil["razon_social"] = (razon_arca or razon_agip or razon_cm).group(1).strip()
    actividad = re.search(r"Actividad principal:\s*(\d{6})", texto, re.I)
    if not actividad:
        actividad = re.search(r"\b(\d{6})\s+.+?PrincipalActividad", texto, re.I)
    if actividad:
        perfil["actividad_principal"] = actividad.group(1)
    actividad_cm = re.search(r"(?m)^(\d{6})\s+.+?\d{2}/\d{2}/\d{4}P\s*$", texto)
    if actividad_cm:
        perfil["actividad_principal"] = actividad_cm.group(1)
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
    sede_cm = re.search(r"Jurisdicción Sede\s*\n\s*(\d{3})\s*-\s*([^\n]+)", texto, re.I)
    if sede_cm:
        perfil.update(
            iibb_regimen="Convenio Multilateral",
            iibb_jurisdiccion=f"{sede_cm.group(1)} - {sede_cm.group(2).strip()}",
            iibb_inscripcion=perfil.get("cuit", ""),
        )
    if re.search(r"IVA\s+\d{2}-\d{4}\b", texto):
        perfil["condicion_iva"] = "Responsable inscripto"
    return perfil


def extraer_cm05_pdf(contenido: bytes) -> dict:
    """Extrae ejercicio y coeficientes unificados de una DDJJ anual CM05."""
    try:
        from pypdf import PdfReader

        texto = "\n".join(
            pagina.extract_text() or "" for pagina in PdfReader(io.BytesIO(contenido)).pages
        )
    except Exception:
        return {}
    if not re.search(r"\bCM\s*05\b", texto, re.I):
        return {}

    ejercicio_match = re.search(r"\b(20\d{2})00\s+(?:Original|Rectificativa)", texto, re.I)
    cuit_match = re.search(r"\b(\d{2}-\d{8}-\d)\b", texto)
    filas = []
    patron = re.compile(
        r"(?m)^(9\d{2})\s+(.+?)\s+([01],[0-9]{4})\s+([01],[0-9]{4})\s+([01],[0-9]{4})"
    )
    for codigo, jurisdiccion, coef_ingresos, coef_gastos, coef_unificado in patron.findall(texto):
        filas.append({
            "codigo": codigo,
            "jurisdiccion": re.sub(r"\s+", " ", jurisdiccion).strip(),
            "coeficiente_ingresos": str(decimal_ar(coef_ingresos)),
            "coeficiente_gastos": str(decimal_ar(coef_gastos)),
            "coeficiente_unificado": str(decimal_ar(coef_unificado)),
        })
    if not filas:
        return {}
    ejercicio = ejercicio_match.group(1) if ejercicio_match else ""
    return {
        "ejercicio": ejercicio,
        "periodo_aplicacion": str(int(ejercicio) + 1) if ejercicio else "",
        "cuit": cuit_match.group(1) if cuit_match else "",
        "coeficientes": filas,
        "coeficiente_total": str(dinero(sum(
            (decimal_ar(fila["coeficiente_unificado"]) for fila in filas),
            Decimal("0"),
        ))),
    }


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

    # XLSX también es internamente un ZIP; sólo abrir como lote cuando la
    # extensión subida sea realmente .zip.
    if nombre_bajo.endswith(".zip") and zipfile.is_zipfile(io.BytesIO(contenido)):
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
        cm05 = extraer_cm05_pdf(contenido)
        if cm05:
            resultado.update(
                categoria="cm05_anual", familia="cm05_anual",
                prioridad=100, cm05=cm05,
            )
        elif "2051" in nombre_bajo or "iva" in nombre_bajo:
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
        if any(marca in nombre_bajo for marca in ("sircreb", "sircupa", "srbinclusiones")):
            resultado.update(
                categoria="coeficientes_recaudacion_bancaria",
                familia="coeficientes_recaudacion_bancaria",
            )
            resultado["advertencias"].append(
                "Coeficientes SIRCREB/SIRCUPA: se guardan separados y no se usan como coeficientes CM03."
            )
            return resultado
        if not (es_emitido or es_recibido):
            try:
                vista = pd.read_excel(io.BytesIO(contenido), header=None, nrows=6)
                es_mis_comprobantes = any(
                    str(valor).strip() in {"Fecha", "Fecha de Emisión"}
                    for valor in vista.to_numpy().flatten()
                )
            except Exception:
                es_mis_comprobantes = False
            if not es_mis_comprobantes:
                resultado["advertencias"].append(
                    "El Excel se guardó como respaldo; no coincide con Mis Comprobantes de ARCA."
                )
                return resultado
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
    tipo = movimientos.get(
        "tipo_comprobante", pd.Series("", index=movimientos.index),
    ).astype(str)
    notas_credito = tipo.apply(es_nota_credito)
    ventas = iva & clase.eq("emitido")
    compras = iva & clase.eq("recibido")

    ventas_operaciones_neto = total("neto_gravado", ventas & ~notas_credito)
    ventas_notas_credito_neto = total("neto_gravado", ventas & notas_credito)
    compras_operaciones_neto = total("neto_gravado", compras & ~notas_credito)
    compras_notas_credito_neto = total("neto_gravado", compras & notas_credito)
    debito_operaciones = total("iva", ventas & ~notas_credito)
    restitucion_debito = total("iva", ventas & notas_credito)
    credito_operaciones = total("iva", compras & ~notas_credito)
    restitucion_credito = total("iva", compras & notas_credito)

    return {
        "ventas_operaciones_neto": ventas_operaciones_neto,
        "ventas_notas_credito_neto": ventas_notas_credito_neto,
        "ventas_neto": dinero(ventas_operaciones_neto - ventas_notas_credito_neto),
        "compras_operaciones_neto": compras_operaciones_neto,
        "compras_notas_credito_neto": compras_notas_credito_neto,
        "compras_neto": dinero(compras_operaciones_neto - compras_notas_credito_neto),
        "iva_debito_operaciones": debito_operaciones,
        "iva_restitucion_debito": restitucion_debito,
        "iva_credito_operaciones": credito_operaciones,
        "iva_restitucion_credito": restitucion_credito,
        # El F.2051 muestra las restituciones cruzadas: las NC recibidas
        # restituyen crédito y se suman al débito; las NC emitidas restituyen
        # débito y se suman al crédito.
        "iva_debito": dinero(debito_operaciones + restitucion_credito),
        "iva_credito": dinero(credito_operaciones + restitucion_debito),
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


def calcular_iibb_convenio(base_general, jurisdicciones) -> dict:
    """Calcula CM03 por jurisdicción sin mezclar coeficientes SIRCREB.

    ``coeficiente`` se expresa como coeficiente unificado (por ejemplo 0.1618)
    y ``alicuota`` como porcentaje (por ejemplo 3 para 3%). Cada fila puede
    informar una ``base_actividad`` propia; si está vacía se usa la base general.
    """
    base_general = dinero(base_general)
    if isinstance(jurisdicciones, pd.DataFrame):
        filas = jurisdicciones.to_dict("records")
    else:
        filas = list(jurisdicciones or [])

    detalle = []
    for fila in filas:
        codigo = str(fila.get("codigo", "")).strip()
        nombre = str(fila.get("jurisdiccion", "")).strip()
        if not codigo and not nombre:
            continue
        base_actividad_raw = fila.get("base_actividad", "")
        base_vacia = (
            base_actividad_raw is None
            or (not isinstance(base_actividad_raw, str) and pd.isna(base_actividad_raw))
            or str(base_actividad_raw).strip().casefold() in {"", "nan", "none"}
        )
        base_actividad = base_general if base_vacia else dinero(base_actividad_raw)
        coeficiente = decimal_ar(fila.get("coeficiente", 0))
        alicuota = decimal_ar(fila.get("alicuota", 0))
        base_atribuida = dinero(base_actividad * coeficiente)
        determinado = dinero(base_atribuida * alicuota / Decimal("100"))
        valores_suman = dinero(fila.get("valores_suman", 0))
        retenciones = dinero(fila.get("retenciones", 0))
        percepciones = dinero(fila.get("percepciones", 0))
        recaudaciones = dinero(fila.get("recaudaciones_bancarias", 0))
        saldo_anterior = dinero(fila.get("saldo_favor_anterior", 0))
        otros_creditos = dinero(fila.get("otros_creditos", 0))
        creditos = dinero(
            retenciones + percepciones + recaudaciones
            + saldo_anterior + otros_creditos
        )
        diferencia = dinero(determinado + valores_suman - creditos)
        detalle.append({
            **fila,
            "codigo": codigo,
            "jurisdiccion": nombre,
            "base_actividad": base_actividad,
            "coeficiente": coeficiente,
            "alicuota": alicuota,
            "base_atribuida": base_atribuida,
            "impuesto_determinado": determinado,
            "valores_suman": valores_suman,
            "retenciones": retenciones,
            "percepciones": percepciones,
            "recaudaciones_bancarias": recaudaciones,
            "saldo_favor_anterior": saldo_anterior,
            "otros_creditos": otros_creditos,
            "creditos": creditos,
            "saldo_pagar": dinero(max(diferencia, Decimal("0"))),
            "saldo_favor": dinero(max(-diferencia, Decimal("0"))),
        })

    def sumar(campo):
        return dinero(sum((decimal_ar(fila[campo]) for fila in detalle), Decimal("0")))

    coeficientes_por_jurisdiccion = {}
    for fila in detalle:
        clave = fila["codigo"] or fila["jurisdiccion"]
        coeficientes_por_jurisdiccion.setdefault(clave, decimal_ar(fila["coeficiente"]))
    return {
        "base_general": base_general,
        "coeficiente_total": sum(coeficientes_por_jurisdiccion.values(), Decimal("0")),
        "impuesto_determinado": sumar("impuesto_determinado"),
        "creditos": sumar("creditos"),
        "valores_suman": sumar("valores_suman"),
        "saldo_pagar": sumar("saldo_pagar"),
        "saldo_favor": sumar("saldo_favor"),
        "detalle": detalle,
    }


def calcular_coeficientes_cm05(jurisdicciones) -> dict:
    """Genera coeficientes CM05 desde ingresos y gastos computables anuales."""
    filas = (
        jurisdicciones.to_dict("records")
        if isinstance(jurisdicciones, pd.DataFrame)
        else list(jurisdicciones or [])
    )
    total_ingresos = sum(
        (decimal_ar(fila.get("ingresos_computables", 0)) for fila in filas),
        Decimal("0"),
    )
    total_gastos = sum(
        (decimal_ar(fila.get("gastos_computables", 0)) for fila in filas),
        Decimal("0"),
    )
    if total_ingresos <= 0 or total_gastos <= 0:
        raise ValueError(
            "El CM05 requiere ingresos y gastos computables anuales mayores que cero."
        )
    detalle = []
    for fila in filas:
        ingresos = decimal_ar(fila.get("ingresos_computables", 0))
        gastos = decimal_ar(fila.get("gastos_computables", 0))
        coef_ingresos = (ingresos / total_ingresos).quantize(
            CUATRO_DECIMALES, rounding=ROUND_HALF_UP,
        )
        coef_gastos = (gastos / total_gastos).quantize(
            CUATRO_DECIMALES, rounding=ROUND_HALF_UP,
        )
        coef_unificado = ((coef_ingresos + coef_gastos) / Decimal("2")).quantize(
            CUATRO_DECIMALES, rounding=ROUND_HALF_UP,
        )
        detalle.append({
            **fila,
            "ingresos_computables": dinero(ingresos),
            "gastos_computables": dinero(gastos),
            "coeficiente_ingresos": coef_ingresos,
            "coeficiente_gastos": coef_gastos,
            "coeficiente_unificado": coef_unificado,
        })
    return {
        "total_ingresos": dinero(total_ingresos),
        "total_gastos": dinero(total_gastos),
        "coeficiente_total": sum(
            (fila["coeficiente_unificado"] for fila in detalle), Decimal("0")
        ),
        "detalle": detalle,
    }
