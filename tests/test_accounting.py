import unittest

import pandas as pd

from am_hub_accounting import (
    ASIENTO_LINEA_COLUMNAS,
    balance_sumas_saldos,
    crear_asiento_manual,
    generar_asiento_banco,
    generar_asiento_sueldos,
    generar_asientos_comprobantes,
    parsear_extracto_bancario,
    validar_asientos,
)


class AccountingTests(unittest.TestCase):
    def test_comprobantes_generan_asientos_balanceados(self):
        movimientos = pd.DataFrame([
            {
                "id": "V1", "impuesto": "IVA", "clase": "emitido",
                "fecha": "2026-07-01", "tipo_comprobante": "1 - Factura A",
                "punto_venta": "1", "numero": "10", "cuit_contraparte": "20-1",
                "denominacion": "Cliente", "neto_gravado": "1000",
                "iva": "210", "otros_tributos": "0", "total": "1210",
            },
            {
                "id": "C1", "impuesto": "IVA", "clase": "recibido",
                "fecha": "2026-07-02", "tipo_comprobante": "1 - Factura A",
                "punto_venta": "2", "numero": "20", "cuit_contraparte": "30-1",
                "denominacion": "Proveedor", "neto_gravado": "500",
                "iva": "105", "otros_tributos": "5", "total": "610",
            },
        ])
        asientos, lineas = generar_asientos_comprobantes(
            movimientos, "Cliente prueba", "2026-07", "admin",
        )
        self.assertEqual(len(asientos), 2)
        control = validar_asientos(asientos, lineas)
        self.assertTrue(control["balanceado"].all())

    def test_extracto_bancario_normaliza_y_sugiere(self):
        contenido = (
            "Fecha;Descripción;Débito;Crédito;Saldo\n"
            "15/07/2026;PAGO VEP ARCA;1210,00;;5000,00\n"
            "16/07/2026;COBRO CLIENTE;;2500,00;7500,00\n"
        ).encode("latin-1")
        movimientos = parsear_extracto_bancario(
            contenido, "banco.csv", "Cliente prueba", "Banco 1", "admin",
        )
        self.assertEqual(len(movimientos), 2)
        self.assertEqual(movimientos.iloc[0]["cuenta_sugerida"], "2.1.03")
        cab, lineas = generar_asiento_banco(movimientos.iloc[0].to_dict(), "2.1.03")
        control = validar_asientos(pd.DataFrame([cab]), pd.DataFrame(lineas))
        self.assertTrue(control.iloc[0]["balanceado"])

    def test_sueldos_balancean_y_alimentan_sumas_saldos(self):
        registro = {
            "id": "S1", "cliente": "Cliente prueba", "periodo": "2026-07",
            "remuneracion_bruta": "100000", "descuentos_aportes": "17000",
            "neto_sueldos": "83000", "contribuciones_patronales": "25000",
            "art": "3000", "otros_costos": "1000", "observaciones": "",
        }
        cab, lineas = generar_asiento_sueldos(registro)
        detalle = pd.DataFrame(lineas, columns=ASIENTO_LINEA_COLUMNAS)
        control = validar_asientos(pd.DataFrame([cab]), detalle)
        self.assertTrue(control.iloc[0]["balanceado"])
        balance = balance_sumas_saldos(detalle)
        self.assertEqual(sum(balance["debe"]), sum(balance["haber"]))

    def test_asiento_manual_no_oculta_descuadres(self):
        with self.assertRaises(ValueError):
            crear_asiento_manual(
                "Cliente", "2026-07", "2026-07-01", "Apertura",
                [{"cuenta_codigo": "1.1.02", "debe": 100, "haber": 0}],
            )


if __name__ == "__main__":
    unittest.main()
