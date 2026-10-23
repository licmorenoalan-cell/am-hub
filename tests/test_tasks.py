import json
import unittest
from datetime import date

from am_hub_tasks import (
    categoria_visual_tarea,
    construir_siguiente_ocurrencia,
    titulo_visual_tarea,
    siguiente_fecha_recurrente,
)


class RecurrenciasTareasTests(unittest.TestCase):
    def test_etiquetas_impositivas_se_normalizan_desde_categoria_o_titulo(self):
        self.assertEqual(categoria_visual_tarea("IIBB"), "Ingresos Brutos")
        self.assertEqual(
            categoria_visual_tarea("Impuestos", "Pago de anticipos"),
            "Anticipos",
        )
        self.assertEqual(categoria_visual_tarea("", "Autonomos — socio"), "Autónomos")
        self.assertEqual(
            categoria_visual_tarea("Bandeja de entrada", "Activar acceso"),
            "Bandeja de entrada",
        )

    def test_tarjeta_impositiva_usa_cliente_como_titulo_visual(self):
        self.assertEqual(
            titulo_visual_tarea("IVA — CASA DESER SRL", "CASA DESER SRL", "IVA"),
            "CASA DESER SRL",
        )
        self.assertEqual(
            titulo_visual_tarea("Preparar propuesta", "Cliente", "Comercial"),
            "Preparar propuesta",
        )

    def test_recurrencia_mensual_conserva_dia(self):
        self.assertEqual(
            siguiente_fecha_recurrente("2026-10-20", "Mensual", 1),
            "2026-11-20",
        )

    def test_recurrencia_mensual_ajusta_fin_de_mes(self):
        self.assertEqual(
            siguiente_fecha_recurrente("2026-01-31", "Mensual", 1),
            "2026-02-28",
        )

    def test_nueva_ocurrencia_reinicia_estado_y_checklist(self):
        tarea = {
            "id": "TAR-1",
            "cliente": "CASA DESER SRL",
            "tarea": "IVA — CASA DESER SRL",
            "estado": "En curso",
            "fecha_limite": "2026-10-21",
            "recurrente": "Sí",
            "frecuencia": "Mensual",
            "intervalo": "1",
            "serie_id": "SER-IVA-CASA-DESER",
            "ocurrencia": "4",
            "checklist": json.dumps(
                [
                    {"texto": "Preparar papel de trabajo", "hecho": True},
                    {"texto": "Presentar", "hecho": True},
                ]
            ),
            "comentarios": "Presentado",
            "categoria": "IVA",
        }

        nueva = construir_siguiente_ocurrencia(
            tarea,
            "Alan Moreno",
            hoy=date(2026, 10, 18),
            nueva_id="TAR-2",
        )

        self.assertEqual(nueva["id"], "TAR-2")
        self.assertEqual(nueva["estado"], "Pendiente")
        self.assertEqual(nueva["fecha_limite"], "2026-11-21")
        self.assertEqual(nueva["ocurrencia"], "5")
        self.assertEqual(nueva["comentarios"], "")
        self.assertEqual(
            json.loads(nueva["checklist"]),
            [
                {"texto": "Preparar papel de trabajo", "hecho": False},
                {"texto": "Presentar", "hecho": False},
            ],
        )


if __name__ == "__main__":
    unittest.main()
