import json
import unittest
from datetime import date

from am_hub_tasks import (
    construir_siguiente_ocurrencia,
    siguiente_fecha_recurrente,
)


class RecurrenciasTareasTests(unittest.TestCase):
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
