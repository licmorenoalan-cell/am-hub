import io
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

import pandas as pd

from am_hub_fiscal import (
    analizar_archivo_fiscal,
    calcular_iibb,
    calcular_iva,
    decimal_ar,
    extraer_perfil_constancia_pdf,
    resumir_movimientos,
    seleccionar_fuentes_calculo,
)


class FiscalTests(unittest.TestCase):
    def test_decimal_ar_admite_formatos_usuales(self):
        self.assertEqual(decimal_ar("$ 2.124.917,39"), Decimal("2124917.39"))
        self.assertEqual(decimal_ar("446232.61"), Decimal("446232.61"))
        self.assertEqual(decimal_ar("1,00"), Decimal("1.00"))

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
