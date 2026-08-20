import tempfile
import unittest
from pathlib import Path

import pandas as pd

from am_hub_core import (
    buscar_dataframe,
    clientes_asignados_activos,
    crear_evento_actividad,
    escribir_csv_atomico,
    filtrar_por_clientes_permitidos,
    filtrar_tareas_por_estado,
    normalizar_dataframe,
    validar_identificador_sql,
)
from am_hub_i18n import normalize_language, translate


def _siguiente_fecha_tarea(fecha_actual, frecuencia, intervalo=1):
    import ast
    from pathlib import Path

    modulo = ast.parse(Path(__file__).parents[1].joinpath("app.py").read_text())
    nodo = next(
        item
        for item in modulo.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "siguiente_fecha_tarea"
    )
    mini_modulo = ast.Module(body=[nodo], type_ignores=[])
    namespace = {"pd": __import__("pandas"), "date": __import__("datetime").date}
    exec(compile(mini_modulo, "app.py", "exec"), namespace)
    return namespace["siguiente_fecha_tarea"](
        fecha_actual,
        frecuencia,
        intervalo,
    )


class CoreTests(unittest.TestCase):
    def test_plan_trabajo_respeta_solo_asignaciones_activas(self):
        asignaciones = pd.DataFrame([
            {"username": "Lali", "cliente": "Cliente A", "activo": "Sí"},
            {"username": "lali", "cliente": "Cliente B", "activo": "No"},
            {"username": "otro", "cliente": "Cliente C", "activo": "Sí"},
            {"username": " lali ", "cliente": "Cliente A", "activo": "activo"},
            {"username": "lali", "cliente": "Cliente eliminado", "activo": "Sí"},
        ])
        visibles = clientes_asignados_activos(
            asignaciones,
            "lali",
            ["Cliente A", "Cliente B", "Cliente C"],
        )
        self.assertEqual(visibles, ["Cliente A"])

        tarjetas = pd.DataFrame([
            {"id": "1", "cliente": "cliente a"},
            {"id": "2", "cliente": "Cliente B"},
            {"id": "3", "cliente": "Cliente C"},
        ])
        resultado = filtrar_por_clientes_permitidos(tarjetas, visibles)
        self.assertEqual(resultado["id"].tolist(), ["1"])

    def test_plan_trabajo_sin_asignaciones_no_expone_tarjetas(self):
        tarjetas = pd.DataFrame([{"id": "1", "cliente": "Cliente A"}])
        resultado = filtrar_por_clientes_permitidos(tarjetas, [])
        self.assertTrue(resultado.empty)

    def test_ultimo_dia_habil_del_mes_evade_fin_de_semana(self):
        self.assertEqual(
            _siguiente_fecha_tarea(
                "2026-07-31",
                "Último día hábil del mes",
            ),
            "2026-08-31",
        )
        self.assertEqual(
            _siguiente_fecha_tarea(
                "2026-08-31",
                "Último día hábil del mes",
            ),
            "2026-09-30",
        )

    def test_recurrencia_semestral_alterna_febrero_y_agosto(self):
        self.assertEqual(
            _siguiente_fecha_tarea(
                "2026-08-03",
                "Semestral",
            ),
            "2027-02-03",
        )
        self.assertEqual(
            _siguiente_fecha_tarea(
                "2027-02-03",
                "Semestral",
            ),
            "2027-08-03",
        )

    def test_traduccion_local_preserva_valores_desconocidos(self):
        self.assertEqual(translate("Pendiente", "en"), "Pending")
        self.assertEqual(translate("Cliente inventado", "en"), "Cliente inventado")
        self.assertEqual(normalize_language("English"), "en")

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

    def test_busqueda_exige_todas_las_palabras_y_no_interpreta_regex(self):
        datos = pd.DataFrame([
            {"tarea": "Preparar reporte mensual", "cliente": "Ritual"},
            {"tarea": "Revisar pauta", "cliente": "Ritual"},
            {"tarea": "Reporte [final]", "cliente": "EZCA"},
        ])
        resultado = buscar_dataframe(datos, "reporte ritual", ["tarea", "cliente"])
        self.assertEqual(resultado.index.tolist(), [0])
        literal = buscar_dataframe(datos, "[final]", ["tarea"])
        self.assertEqual(literal.index.tolist(), [2])

    def test_evento_actividad_es_compacto_y_trunca_detalle(self):
        evento = crear_evento_actividad(
            usuario=" alan ",
            nombre="Alan",
            role="admin",
            cliente="",
            accion="guardar",
            recurso="tareas",
            registro_id="TAR-1",
            detalle="x" * 1200,
        )
        self.assertTrue(evento["id"].startswith("EVT-"))
        self.assertEqual(evento["usuario"], "alan")
        self.assertEqual(len(evento["detalle"]), 1000)

    def test_tareas_finalizadas_solo_aparecen_con_filtro_explicito(self):
        tareas = pd.DataFrame([
            {"id": "1", "estado": "Pendiente"},
            {"id": "2", "estado": "En curso"},
            {"id": "3", "estado": "Finalizada"},
        ])

        sin_filtro = filtrar_tareas_por_estado(tareas, [])
        self.assertEqual(sin_filtro["id"].tolist(), ["1", "2"])

        activas = filtrar_tareas_por_estado(tareas, ["Activas"])
        self.assertEqual(activas["id"].tolist(), ["1", "2"])

        finalizadas = filtrar_tareas_por_estado(tareas, ["Finalizada"])
        self.assertEqual(finalizadas["id"].tolist(), ["3"])

        combinadas = filtrar_tareas_por_estado(
            tareas,
            ["Pendiente", "Finalizada"],
        )
        self.assertEqual(combinadas["id"].tolist(), ["1", "3"])


if __name__ == "__main__":
    unittest.main()
