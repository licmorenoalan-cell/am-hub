import io
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

import pandas as pd

from am_hub_fiscal import (
    analizar_archivo_fiscal,
    calcular_iibb,
    calcular_iibb_local_actividades,
    calcular_iibb_convenio,
    calcular_coeficientes_cm05,
    calcular_iva,
    decimal_ar,
    extraer_perfil_constancia_pdf,
    extraer_cm05_pdf,
    extraer_libro_iva_pdf,
    evaluar_expediente_fiscal,
    id_periodo_fiscal,
    periodo_aplicacion_cm05,
    periodo_desde_fecha,
    preparar_movimientos_periodo,
    resumir_libro_iva,
    resumir_movimientos,
    seleccionar_fuentes_calculo,
)


class FiscalTests(unittest.TestCase):
    def test_extrae_libro_iva_casa_deser_mayo_2025(self):
        ruta = Path(
            "/Users/alanmoreno/Downloads/"
            "formulario_2083_300_30718935225_1_1102224462.pdf"
        )
        if not ruta.exists():
            self.skipTest("El F.2083 de Casa Deser no está disponible.")
        libro = extraer_libro_iva_pdf(ruta.read_bytes())
        self.assertEqual(libro["periodo"], "2025-05")
        self.assertEqual(libro["transaccion"], "1102224462")
        self.assertEqual(decimal_ar(libro["compras"]["neto"]), Decimal("12446734.00"))
        self.assertEqual(decimal_ar(libro["compras"]["iva"]), Decimal("1753864.14"))
        self.assertEqual(decimal_ar(libro["compras_sin_credito"]), Decimal("5713791.00"))

    def test_resumen_libro_iva_separa_compras_sin_credito(self):
        movimientos = pd.DataFrame([
            {
                "clase": "recibido", "impuesto": "IVA", "tipo_comprobante": "Factura A",
                "neto_gravado": "100.00", "iva": "21.00", "otros_tributos": "0",
                "total": "151.00",
            },
            {
                "clase": "emitido", "impuesto": "IVA", "tipo_comprobante": "Factura A",
                "neto_gravado": "200.00", "iva": "42.00", "otros_tributos": "0",
                "total": "242.00",
            },
        ])
        libro = resumir_libro_iva(movimientos)
        self.assertEqual(libro["compras"]["neto"], Decimal("100.00"))
        self.assertEqual(libro["compras"]["iva"], Decimal("21.00"))
        self.assertEqual(libro["compras_sin_credito"], Decimal("30.00"))
        self.assertEqual(libro["ventas"]["neto"], Decimal("200.00"))

    def test_periodo_nuevo_conserva_id_entre_recargas(self):
        primero = id_periodo_fiscal("CASA DESER SRL", "2026-07")
        segundo = id_periodo_fiscal(" casa deser srl ", "2026-07")
        otro = id_periodo_fiscal("CASA DESER SRL", "2026-08")
        self.assertEqual(primero, segundo)
        self.assertNotEqual(primero, otro)

    def test_lote_excluye_otros_periodos_y_movimientos_duplicados(self):
        movimientos = pd.DataFrame([
            {"id": "A", "fecha": "20/05/2025", "importe": "10"},
            {"id": "A", "fecha": "20/05/2025", "importe": "10"},
            {"id": "B", "fecha": "14/06/2025", "importe": "20"},
            {"id": "C", "fecha": "", "importe": "30"},
        ])
        filtrados, excluidos, duplicados = preparar_movimientos_periodo(
            movimientos, "2025-05",
        )
        self.assertEqual(set(filtrados["id"]), {"A", "C"})
        self.assertEqual(excluidos, 1)
        self.assertEqual(duplicados, 1)

    def test_decimal_ar_admite_formatos_usuales(self):
        self.assertEqual(decimal_ar("$ 2.124.917,39"), Decimal("2124917.39"))
        self.assertEqual(decimal_ar("446232.61"), Decimal("446232.61"))
        self.assertEqual(decimal_ar("1,00"), Decimal("1.00"))
        self.assertEqual(periodo_aplicacion_cm05("2026-03"), "2025")
        self.assertEqual(periodo_aplicacion_cm05("2026-04"), "2026")
        self.assertEqual(periodo_desde_fecha("2025-05-07"), "2025-05")
        self.assertEqual(periodo_desde_fecha("07/05/2025"), "2025-05")

    def test_importa_zip_arca_sin_duplicar_fuentes(self):
        csv = (
            '"Fecha de Emisión";"Tipo de Comprobante";"Punto de Venta";'
            '"Número Desde";"Nro. Doc. Receptor";"Denominación Receptor";'
            '"Imp. Neto Gravado Total";"Otros Tributos";"Total IVA";"Imp. Total"\n'
            '2026-07-01;6;2;1209;0;;12975,21;0,00;2724,79;15700,00\n'
        ).encode("utf-8")
        memoria = io.BytesIO()
        with zipfile.ZipFile(memoria, "w") as salida:
            salida.writestr("comprobantes_emitidos.csv", csv)
        analisis = analizar_archivo_fiscal("emitidos.zip", memoria.getvalue())
        self.assertEqual(analisis["categoria"], "comprobantes_emitidos")
        self.assertEqual(len(analisis["movimientos"]), 1)
        resumen = resumir_movimientos(analisis["movimientos"])
        self.assertEqual(resumen["iva_debito"], Decimal("2724.79"))

        duplicado = analizar_archivo_fiscal("comprobantes_emitidos.csv", csv)
        self.assertEqual(seleccionar_fuentes_calculo([analisis, duplicado]), {0})

    def test_importa_exportacion_compras_portal_iva(self):
        csv = (
            '"Fecha de Emisión";"Tipo de Comprobante";"Punto de Venta";'
            '"Número de Comprobante";"Nro. Doc. Vendedor";"Denominación Vendedor";'
            '"Importe Total";"Crédito Fiscal Computable";"Total Neto Gravado";"Total IVA"\n'
            '2025-05-29;1;2;846;30680108346;"AF CONSTRUCCIONES SRL";'
            '5150285,14;893851,14;4256434,00;893851,10\n'
        ).encode("utf-8")
        analisis = analizar_archivo_fiscal(
            "comprobantes_periodo_compras.csv", csv,
        )
        self.assertEqual(analisis["categoria"], "comprobantes_recibidos")
        movimiento = analisis["movimientos"].iloc[0]
        self.assertEqual(movimiento["numero"], "846")
        self.assertEqual(movimiento["cuit_contraparte"], "30-68010834-6")
        self.assertEqual(movimiento["total"], "5150285.14")
        self.assertEqual(movimiento["iva"], "893851.14")

    def test_calculo_casa_deser_julio(self):
        iva = calcular_iva(
            446232.61,
            531549.25,
            saldo_tecnico_anterior=7844228.27,
            saldo_libre_anterior=116150.12,
            percepciones_retenciones=3454.23,
        )
        self.assertEqual(iva["saldo_tecnico_favor"], Decimal("7929544.91"))
        self.assertEqual(iva["saldo_libre_favor"], Decimal("119604.35"))
        self.assertEqual(iva["saldo_pagar"], Decimal("0.00"))

        iibb = calcular_iibb(
            2124917.39,
            3,
            retenciones=180339.05,
            percepciones=7781.46,
            saldo_favor_anterior=344160.72,
            ajustes=7697.40,
        )
        self.assertEqual(iibb["impuesto_determinado"], Decimal("63747.52"))
        self.assertEqual(iibb["saldo_favor"], Decimal("476231.11"))

    def test_notas_credito_restituyen_iva_en_f2051(self):
        movimientos = pd.DataFrame([
            {"impuesto": "IVA", "clase": "emitido", "tipo_comprobante": "1 - Factura A", "neto_gravado": "1000", "iva": "210", "computado": "Sí"},
            {"impuesto": "IVA", "clase": "emitido", "tipo_comprobante": "3 - Nota de Crédito A", "neto_gravado": "100", "iva": "21", "computado": "Sí"},
            {"impuesto": "IVA", "clase": "recibido", "tipo_comprobante": "1 - Factura A", "neto_gravado": "500", "iva": "105", "computado": "Sí"},
            {"impuesto": "IVA", "clase": "recibido", "tipo_comprobante": "3 - Nota de Crédito A", "neto_gravado": "50", "iva": "10.50", "computado": "Sí"},
        ])
        resumen = resumir_movimientos(movimientos)
        self.assertEqual(resumen["ventas_neto"], Decimal("900.00"))
        self.assertEqual(resumen["compras_neto"], Decimal("450.00"))
        self.assertEqual(resumen["iva_debito"], Decimal("220.50"))
        self.assertEqual(resumen["iva_credito"], Decimal("126.00"))
        self.assertEqual(resumen["iva_restitucion_debito"], Decimal("21.00"))
        self.assertEqual(resumen["iva_restitucion_credito"], Decimal("10.50"))

    def test_convenio_multilateral_calcula_por_jurisdiccion(self):
        calculo = calcular_iibb_convenio(18808448.77, [
            {"codigo": "901", "jurisdiccion": "CABA", "coeficiente": ".1618", "alicuota": "3", "otros_creditos": "2311.97"},
            {"codigo": "908", "jurisdiccion": "Entre Ríos", "coeficiente": ".0017", "alicuota": "5", "otros_creditos": "57.70"},
        ])
        self.assertEqual(calculo["detalle"][0]["impuesto_determinado"], Decimal("91296.21"))
        self.assertEqual(calculo["detalle"][0]["saldo_pagar"], Decimal("88984.24"))
        self.assertEqual(calculo["detalle"][1]["impuesto_determinado"], Decimal("1598.72"))
        self.assertEqual(calculo["detalle"][1]["saldo_pagar"], Decimal("1541.02"))

    def test_iibb_local_separa_actividades_y_deducciones(self):
        calculo = calcular_iibb_local_actividades([
            {"codigo": "1", "actividad": "Servicios", "tratamiento": "Gravada", "base_imponible": "100000", "alicuota": "3"},
            {"codigo": "2", "actividad": "Intereses exentos", "tratamiento": "Exenta", "base_imponible": "20000", "alicuota": "3"},
            {"codigo": "3", "actividad": "No alcanzada", "tratamiento": "No gravada", "base_imponible": "5000", "alicuota": "0"},
        ], retenciones=500, percepciones=250, recaudaciones_bancarias=100, saldo_favor_anterior=50)
        self.assertEqual(calculo["base_imponible"], Decimal("100000.00"))
        self.assertEqual(calculo["base_exenta"], Decimal("20000.00"))
        self.assertEqual(calculo["base_no_gravada"], Decimal("5000.00"))
        self.assertEqual(calculo["impuesto_determinado"], Decimal("3000.00"))
        self.assertEqual(calculo["creditos"], Decimal("900.00"))
        self.assertEqual(calculo["saldo_pagar"], Decimal("2100.00"))

    def test_cm05_calcula_coeficiente_ingresos_gastos_y_unificado(self):
        calculo = calcular_coeficientes_cm05([
            {"codigo": "901", "ingresos_computables": "3236", "gastos_computables": "0"},
            {"codigo": "902", "ingresos_computables": "6303", "gastos_computables": "10000"},
            {"codigo": "903", "ingresos_computables": "21", "gastos_computables": "0"},
            {"codigo": "904", "ingresos_computables": "61", "gastos_computables": "0"},
            {"codigo": "924", "ingresos_computables": "36", "gastos_computables": "0"},
        ])
        caba = calculo["detalle"][0]
        buenos_aires = calculo["detalle"][1]
        self.assertEqual(caba["coeficiente_unificado"], Decimal("0.1676"))
        self.assertEqual(buenos_aires["coeficiente_gastos"], Decimal("1.0000"))
        self.assertEqual(buenos_aires["coeficiente_unificado"], Decimal("0.8264"))

    def test_expediente_detecta_faltantes_y_declaraciones_sin_movimientos(self):
        perfil = {"cuit": "30-12345678-9", "condicion_iva": "Responsable inscripto", "iibb_regimen": "Local"}
        registro = {"sin_compras": "Sí", "sin_deducciones_iva": "Sí", "sin_deducciones_iibb": "Sí"}
        movimientos = pd.DataFrame([{"clase": "emitido", "impuesto": "IVA"}])
        control = evaluar_expediente_fiscal(perfil, registro, pd.DataFrame(), movimientos)
        self.assertFalse(control["listo_para_revision"])
        registro.update(iva_debito="210.00", iibb_determinado="30.00")
        control = evaluar_expediente_fiscal(perfil, registro, pd.DataFrame(), movimientos)
        self.assertTrue(control["listo_para_revision"])

    def test_fuentes_reales_villalobo_mallo_si_estan_disponibles(self):
        rutas = [
            Path("/Users/alanmoreno/Downloads/comprobantes_consulta_csv_emitidos_204547631_27408847112_20260817-1917.zip"),
            Path("/Users/alanmoreno/Downloads/comprobantes_consulta_csv_recibidos_204547662_27408847112_20260817-1917.zip"),
        ]
        if not all(ruta.exists() for ruta in rutas):
            self.skipTest("Los archivos locales de Villalobo Mallo no están disponibles.")
        analisis = [analizar_archivo_fiscal(ruta.name, ruta.read_bytes()) for ruta in rutas]
        movimientos = pd.concat([item["movimientos"] for item in analisis], ignore_index=True)
        resumen = resumir_movimientos(movimientos)
        self.assertEqual(resumen["ventas_neto"], Decimal("18808448.77"))
        self.assertEqual(resumen["compras_neto"], Decimal("8180943.08"))
        self.assertEqual(resumen["iva_debito"], Decimal("2083907.32"))
        self.assertEqual(resumen["iva_credito"], Decimal("1384768.90"))

        coeficientes = Path("/Users/alanmoreno/Downloads/SrbInclusionesCoeficientesX.xlsx")
        if coeficientes.exists():
            clasificacion = analizar_archivo_fiscal(coeficientes.name, coeficientes.read_bytes())
            self.assertEqual(clasificacion["categoria"], "coeficientes_recaudacion_bancaria")
            self.assertTrue(clasificacion["movimientos"].empty)

        emitidos_xlsx = Path("/Users/alanmoreno/Downloads/Mis Comprobantes Emitidos - CUIT 27408847112.xlsx")
        if emitidos_xlsx.exists():
            clasificacion = analizar_archivo_fiscal(emitidos_xlsx.name, emitidos_xlsx.read_bytes())
            self.assertEqual(clasificacion["categoria"], "comprobantes_emitidos")
            self.assertEqual(len(clasificacion["movimientos"]), 53)
            generico = analizar_archivo_fiscal(
                "archivo_generico.xlsx", emitidos_xlsx.read_bytes(), categoria_hint="ventas",
            )
            self.assertEqual(generico["categoria"], "comprobantes_emitidos")

        constancia_cm = Path("/Users/alanmoreno/Downloads/CInsc_0 (1).pdf")
        if constancia_cm.exists():
            perfil = extraer_perfil_constancia_pdf(constancia_cm.read_bytes())
            self.assertEqual(perfil["iibb_regimen"], "Convenio Multilateral")
            self.assertEqual(perfil["iibb_jurisdiccion"], "902 - BUENOS AIRES")
            self.assertEqual(perfil["actividad_principal"], "952100")

        cm05 = Path("/Users/alanmoreno/Downloads/DDJJ_ANUAL_422071950.pdf")
        if cm05.exists():
            anual = extraer_cm05_pdf(cm05.read_bytes())
            self.assertEqual(anual["ejercicio"], "2025")
            self.assertEqual(anual["periodo_aplicacion"], "2026")
            self.assertEqual(len(anual["coeficientes"]), 24)
            self.assertEqual(anual["coeficiente_total"], "1.00")
            buenos_aires = next(fila for fila in anual["coeficientes"] if fila["codigo"] == "902")
            self.assertEqual(buenos_aires["coeficiente_unificado"], "0.8152")

    def test_fuentes_reales_casa_deser_si_estan_disponibles(self):
        rutas = [
            Path("/Users/alanmoreno/Downloads/comprobantes_consulta_csv_emitidos_204535368_30718935225_20260817-1755.zip"),
            Path("/Users/alanmoreno/Downloads/comprobantes_consulta_csv_recibidos_204535400_30718935225_20260817-1755.zip"),
            Path("/Users/alanmoreno/Downloads/RentasCiudad.xls"),
            Path("/Users/alanmoreno/Downloads/RentasCiudad (2).xls"),
        ]
        if not all(ruta.exists() for ruta in rutas):
            self.skipTest("Los archivos locales del piloto no están disponibles.")
        analisis = [analizar_archivo_fiscal(ruta.name, ruta.read_bytes()) for ruta in rutas]
        movimientos = pd.concat(
            [analisis[i]["movimientos"] for i in seleccionar_fuentes_calculo(analisis)],
            ignore_index=True,
        )
        resumen = resumir_movimientos(movimientos)
        self.assertEqual(resumen["ventas_neto"], Decimal("2124917.39"))
        self.assertEqual(resumen["iva_debito"], Decimal("446232.61"))
        self.assertEqual(resumen["compras_neto"], Decimal("2557862.77"))
        self.assertEqual(resumen["iva_credito"], Decimal("531549.25"))
        self.assertEqual(resumen["iibb_retenciones"], Decimal("180339.05"))
        self.assertEqual(resumen["iibb_percepciones"], Decimal("7781.46"))

    def test_constancia_arca_prefill_casa_deser_si_esta_disponible(self):
        ruta = Path("/Users/alanmoreno/Desktop/CONSTANCIA CUIT CASA DESER SRL.pdf")
        if not ruta.exists():
            self.skipTest("La constancia local del piloto no está disponible.")
        perfil = extraer_perfil_constancia_pdf(ruta.read_bytes())
        self.assertEqual(perfil["cuit"], "30-71893522-5")
        self.assertEqual(perfil["actividad_principal"], "561019")
        self.assertEqual(perfil["condicion_iva"], "Responsable inscripto")


if __name__ == "__main__":
    unittest.main()
