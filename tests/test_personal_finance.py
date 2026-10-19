import unittest

import pandas as pd

from am_hub_personal_finance import (
    resumen_finanzas_personales,
    ultimo_periodo_por_nombre,
)


class PersonalFinanceTests(unittest.TestCase):
    def test_ultimo_periodo_conserva_una_foto_por_cuenta(self):
        df = pd.DataFrame([
            {"id": "1", "periodo": "2026-08", "cuenta": "Banco", "saldo": "100"},
            {"id": "2", "periodo": "2026-09", "cuenta": "Banco", "saldo": "150"},
            {"id": "3", "periodo": "2026-09", "cuenta": "Ahorro", "saldo": "200"},
        ])

        actual = ultimo_periodo_por_nombre(df, "cuenta")

        self.assertEqual(set(actual["cuenta"]), {"Banco", "Ahorro"})
        self.assertEqual(
            actual.loc[actual["cuenta"].eq("Banco"), "saldo"].iloc[0], "150"
        )

    def test_resumen_calcula_deuda_y_preserva_reserva(self):
        cuentas = pd.DataFrame([
            {"id": "1", "periodo": "2026-09", "cuenta": "Banco", "tipo": "Banco", "saldo": "300000"},
            {"id": "2", "periodo": "2026-09", "cuenta": "Plazo", "tipo": "Ahorro", "saldo": "500000"},
        ])
        tarjetas = pd.DataFrame([
            {
                "id": "3", "periodo": "2026-09", "tarjeta": "Visa",
                "total_resumen": "600000", "pago_minimo": "100000",
                "pago_realizado": "150000",
            }
        ])

        resumen = resumen_finanzas_personales(
            cuentas, tarjetas, resultado_mensual=50000, reserva_minima=400000
        )

        self.assertEqual(resumen["liquidez"], 800000)
        self.assertEqual(resumen["ahorro"], 500000)
        self.assertEqual(resumen["deuda_tarjetas"], 450000)
        self.assertEqual(resumen["cancelacion_posible"], 450000)
        self.assertEqual(resumen["deuda_posterior"], 0)
        self.assertEqual(resumen["patrimonio_liquido"], 350000)

    def test_resumen_no_propone_usar_una_reserva_insuficiente(self):
        cuentas = pd.DataFrame([
            {"id": "1", "periodo": "2026-09", "cuenta": "Banco", "tipo": "Banco", "saldo": "100000"},
        ])
        tarjetas = pd.DataFrame([
            {"id": "2", "periodo": "2026-09", "tarjeta": "Visa", "total_resumen": "200000", "pago_realizado": "0"},
        ])

        resumen = resumen_finanzas_personales(
            cuentas, tarjetas, resultado_mensual=-20000, reserva_minima=100000
        )

        self.assertEqual(resumen["cancelacion_posible"], 0)
        self.assertEqual(resumen["deuda_posterior"], 200000)
