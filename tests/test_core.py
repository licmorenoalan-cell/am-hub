import tempfile
import unittest
from pathlib import Path

import pandas as pd

from am_hub_core import (
    escribir_csv_atomico,
    normalizar_dataframe,
    validar_identificador_sql,
)


class CoreTests(unittest.TestCase):
    def test_normalizar_dataframe_agrega_requeridas_y_conserva_extras(self):
        original = pd.DataFrame([{"extra": "x", "id": "1"}])
        resultado = normalizar_dataframe(original, ["id", "cliente"])
        self.assertEqual(list(resultado.columns), ["id", "cliente", "extra"])
        self.assertEqual(resultado.loc[0, "cliente"], "")

    def test_identificador_sql_rechaza_fragmentos(self):
        self.assertEqual(validar_identificador_sql("tareas_2026"), "tareas_2026")
        for invalido in ('tareas"', "tareas; DROP TABLE usuarios", "con espacios"):
            with self.subTest(invalido=invalido):
                with self.assertRaises(ValueError):
                    validar_identificador_sql(invalido)

    def test_escritura_csv_reemplaza_archivo_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.csv"
            escribir_csv_atomico(pd.DataFrame([{"id": "1", "valor": "antes"}]), path)
            escribir_csv_atomico(pd.DataFrame([{"id": "2", "valor": "después"}]), path)
            resultado = pd.read_csv(path, dtype=str)
            self.assertEqual(resultado.to_dict("records"), [{"id": "2", "valor": "después"}])
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
