import unittest

import pandas as pd

from am_hub_accounting import (
    ASIENTO_LINEA_COLUMNAS,
    balance_sumas_saldos,
    crear_asiento_manual,
    filtrar_comprobantes_ya_registrados,
    generar_asiento_banco,
    generar_asiento_operacion,
    generar_asiento_sueldos,
    generar_asientos_comprobantes,
    libro_mayor,
    parsear_extracto_bancario,
    plan_cuentas_inicial,
    proponer_conciliacion_bancaria,
    validar_asientos,
)


class AccountingTests(unittest.TestCase):
    def test_comprobante_arca_se_omite_solo_si_coincide_con_operacion(self):
        movimientos = pd.DataFrame([
            {
                "id": "V1", "clase": "emitido", "cuit_contraparte": "30-12345678-9",
                "punto_venta": "00001", "numero": "00000025",
            },
            {
                "id": "V2", "clase": "emitido", "cuit_contraparte": "30-12345678-9",
                "punto_venta": "1", "numero": "26",
            },
        ])
        operaciones = pd.DataFrame([{
            "tipo_operacion": "Venta", "tercero_cuit": "30123456789",
            "punto_venta": "1", "numero": "25",
        }])
        pendientes, omitidos = filtrar_comprobantes_ya_registrados(
            movimientos, operaciones,
        )
        self.assertEqual(omitidos, 1)
        self.assertEqual(pendientes["id"].tolist(), ["V2"])

    def test_plan_base_incluye_usos_automaticos_editables(self):
        plan = plan_cuentas_inicial("Cliente prueba", "admin")
        banco = plan[plan["codigo"].eq("1.1.02")].iloc[0]
        self.assertEqual(banco["uso_automatico"], "Banco")
        self.assertIn("clave_origen", plan.columns)

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
        _, lineas_especificas = generar_asiento_banco(
            movimientos.iloc[0].to_dict(), "2.1.03", cuenta_banco="1.1.02.001",
        )
        self.assertIn("1.1.02.001", {linea["cuenta_codigo"] for linea in lineas_especificas})

    def test_conciliacion_propone_cobro_existente_sin_duplicarlo(self):
        movimientos = pd.DataFrame([{
            "id": "B1", "fecha": "2026-07-05", "debito": "0", "credito": "1210",
            "descripcion": "TRANSFERENCIA CLIENTE ACME", "referencia": "",
            "conciliado": "No", "estado_conciliacion": "Pendiente",
        }])
        operaciones = pd.DataFrame([{
            "id": "O1", "fecha": "2026-07-04", "tipo_operacion": "Cobro",
            "importe_pesos": "1210", "tercero_nombre": "Cliente Acme",
            "asiento_id": "A1",
        }])
        propuestas = proponer_conciliacion_bancaria(movimientos, operaciones)
        self.assertEqual(propuestas.iloc[0]["match_operacion_id"], "O1")
        self.assertEqual(propuestas.iloc[0]["estado_conciliacion"], "Coincidencia propuesta")
        self.assertGreaterEqual(int(propuestas.iloc[0]["match_confianza"]), 95)

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

    def test_libro_mayor_acumula_saldo_por_cuenta(self):
        asientos = pd.DataFrame([
            {"id": "A1", "fecha": "2026-07-01", "descripcion": "Apertura"},
            {"id": "A2", "fecha": "2026-07-02", "descripcion": "Pago"},
        ])
        lineas = pd.DataFrame([
            {"asiento_id": "A1", "orden": "1", "cuenta_codigo": "1.1.01", "cuenta_nombre": "Caja", "debe": "100", "haber": "0", "detalle": ""},
            {"asiento_id": "A2", "orden": "1", "cuenta_codigo": "1.1.01", "cuenta_nombre": "Caja", "debe": "0", "haber": "30", "detalle": ""},
        ])
        mayor = libro_mayor(lineas, asientos)
        self.assertEqual(mayor.iloc[-1]["saldo_deudor"], 70)
        self.assertEqual(mayor.iloc[-1]["saldo_acreedor"], 0)

    def test_operacion_cliente_bimonetaria_genera_borrador_balanceado(self):
        operacion = {
            "id": "O1", "cliente": "Cliente prueba", "periodo": "2026-07",
            "fecha": "2026-07-03", "tipo_operacion": "Venta",
            "tercero_cuit": "30-1", "tercero_nombre": "Comprador",
            "tipo_comprobante": "Factura A", "punto_venta": "1", "numero": "25",
            "moneda": "USD", "tipo_cambio": "1000", "neto": "100",
            "iva": "21", "otros": "0", "total": "121", "importe_pesos": "121000",
            "cuenta_resultado": "4.1.01", "centro_costo": "Servicios",
        }
        cab, lineas = generar_asiento_operacion(operacion, "cliente")
        self.assertEqual(cab["estado"], "Borrador")
        self.assertEqual(cab["origen"], "Operación cliente")
        control = validar_asientos(pd.DataFrame([cab]), pd.DataFrame(lineas))
        self.assertTrue(control.iloc[0]["balanceado"])

    def test_compra_personal_no_toma_credito_fiscal(self):
        operacion = {
            "id": "O2", "cliente": "Cliente prueba", "periodo": "2026-07",
            "fecha": "2026-07-04", "tipo_operacion": "Compra",
            "tercero_nombre": "Proveedor", "neto": "1000", "iva": "210",
            "total": "1210", "importe_pesos": "1210", "tipo_cambio": "1",
            "es_personal": "Sí",
        }
        cab, lineas = generar_asiento_operacion(operacion)
        codigos = {linea["cuenta_codigo"] for linea in lineas}
        self.assertIn("3.1.02", codigos)
        self.assertNotIn("1.1.04", codigos)


if __name__ == "__main__":
    unittest.main()
