"""Compatibilidad de áreas y persistencia móvil sin acceder a datos reales."""
import ast
import json
import sqlite3
import unittest
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from am_hub_core import normalizar_area_plan, opciones_area_plan


class WorkPlanTests(unittest.TestCase):
    def test_legacy_empty_and_null_areas_remain_unassigned(self):
        for value in (None, "", "  ", float("nan"), pd.NA):
            self.assertEqual(normalizar_area_plan(value), "Sin área")
        self.assertEqual(normalizar_area_plan(" Legal y societaria "), "Legal y societaria")

    def test_editing_does_not_silently_replace_an_existing_area(self):
        self.assertIn("Área histórica", opciones_area_plan("Área histórica"))
        self.assertEqual(opciones_area_plan("Legal y societaria").count("Legal y societaria"), 1)

    def test_pocket_saves_area_on_selected_card_and_preserves_other_cards(self):
        module = ast.parse(Path(__file__).parents[1].joinpath("pocket_app.py").read_text())
        node = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "actualizar_frente_pocket")
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        fields = "id cliente mes objetivo descripcion responsable responsable_am responsable_cliente responsable_tipo area prioridad estado fecha_limite checklist avance comentarios fecha_actualizacion actualizado_por".split()
        db.execute("CREATE TABLE objetivos (" + ",".join(f"{f} TEXT" for f in fields) + ")")
        db.executemany("INSERT INTO objetivos (id, area, comentarios) VALUES (?, ?, ?)", [("one", None, "Historial"), ("two", "Legal y societaria", "Otro")])

        class Connection:
            def execute(self, query, params):
                cursor = db.execute(query.replace(" FOR UPDATE", ""), params)
                return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: cursor.fetchone()))

        # El adaptador conserva el SQL de actualización real y simula el bloqueo
        # PostgreSQL, no disponible en SQLite.
        class SelectConnection(Connection):
            def execute(self, query, params):
                if query.startswith("SELECT"):
                    row = db.execute(query.replace(" FOR UPDATE", ""), params).fetchone()
                    return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: dict(row) if row else None))
                return super().execute(query, params)

        @contextmanager
        def begin():
            with db:
                yield SelectConnection()

        cache = SimpleNamespace(clear=Mock())
        namespace = dict(date=date, get_secret=lambda *args: "test", get_engine=lambda: SimpleNamespace(begin=begin), text=lambda x: x, normalizar_area_plan=normalizar_area_plan, serializar_checklist=json.dumps, cargar_plan_trabajo=cache)
        exec(compile(ast.Module(body=[node], type_ignores=[]), "pocket_app.py", "exec"), namespace)
        namespace["actualizar_frente_pocket"](
            frente_id="one", cliente="Demo", mes="2026-10", objetivo="Prueba",
            descripcion="Detalle", responsable_am="AM", responsable_cliente="Cliente",
            responsable_tipo="Ambos", area="Contable e impositiva", prioridad="Alta",
            estado="En curso", fecha_limite="2026-10-31", checklist=[], comentario="",
        )
        saved = dict(db.execute("SELECT * FROM objetivos WHERE id='one'").fetchone())
        self.assertEqual(saved["area"], "Contable e impositiva")
        self.assertEqual(saved["comentarios"], "Historial")
        self.assertEqual(tuple(db.execute("SELECT area, comentarios FROM objetivos WHERE id='two'").fetchone()), ("Legal y societaria", "Otro"))
        cache.clear.assert_called_once()
        db.close()
