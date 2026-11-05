"""Exercise actual renderer AST without importing the application or its config."""
import ast
from datetime import date, timedelta
import json
from pathlib import Path
import re
import unittest
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def unique(nodes, description):
    if len(nodes) != 1:
        raise AssertionError(f'Expected exactly one {description}; found {len(nodes)}')
    return nodes[0]


def load_badge():
    app = ast.parse((ROOT / 'app.py').read_text())
    tax = ast.parse((ROOT / 'am_hub_tax_calendar.py').read_text())
    render = unique([n for n in app.body if isinstance(n, ast.FunctionDef)
                     and n.name == 'render_tareas_internas'], 'task renderer')
    due = unique([n for n in render.body if isinstance(n, ast.FunctionDef)
                  and n.name == 'vencimiento_tarjeta'], 'due-date helper')
    targets = ['vencimiento_texto', 'vencimiento_fondo', 'vencimiento_color']
    pairs = []
    for parent in ast.walk(render):
        for _, value in ast.iter_fields(parent):
            if not isinstance(value, list):
                continue
            for i, node in enumerate(value):
                if (isinstance(node, ast.Assign) and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Tuple)
                        and [getattr(x, 'id', '') for x in node.targets[0].elts] == targets):
                    pairs.append((value, i))
    statements, i = unique(pairs, 'badge assignment in task renderer')
    body = [statements[i]]
    if any(isinstance(n, ast.Name) and n.id == 'etiqueta_pendiente' for n in ast.walk(statements[i])):
        if i == 0 or not isinstance(statements[i - 1], ast.Assign):
            raise AssertionError('Expected adjacent pending-label assignment')
        pending = statements[i - 1]
        if ast.dump(pending.targets[0]) != ast.dump(ast.Name(id='etiqueta_pendiente', ctx=ast.Store())):
            raise AssertionError('Unexpected pending-label assignment')
        body.insert(0, pending)
    badge = ast.parse('def badge(row, fecha_txt, estado_actual): pass').body[0]
    badge.body = body + [ast.parse('return vencimiento_texto, vencimiento_fondo, vencimiento_color').body[0]]
    helpers = [unique([n for n in tax.body if isinstance(n, ast.FunctionDef) and n.name == name], name)
               for name in ('metadata', 'is_fiscal', 'pending_label')]
    constants = [unique([n for n in tax.body if isinstance(n, ast.Assign)
                        and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                        and n.targets[0].id == name], name) for name in ('PREFIX', 'PENDING')]
    env = dict(pd=pd, date=date, json=json, re=re)
    module = ast.fix_missing_locations(ast.Module(body=constants + helpers + [due, badge], type_ignores=[]))
    exec(compile(module, '<actual-renderer-ast>', 'exec'), env)
    return env


class BadgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = load_badge()

    def badge(self, row):
        return self.env['badge'](row, row.get('fecha_limite', ''), row.get('estado', 'Pendiente'))

    def test_old_expression_reproduces_error(self):
        label = self.env['pending_label']({'recurrente': 'Sí', 'categoria': 'IVA'})
        with self.assertRaisesRegex(ValueError, 'too many values to unpack'):
            a, b, c = label or ('normal', 'background', 'foreground')

    def test_pending(self):
        self.assertEqual(self.badge({'recurrente': 'Sí', 'categoria': 'IVA'}),
                         ('Vencimiento fiscal pendiente', '#FEF3C7', '#92400E'))

    def test_empty_values(self):
        for value in ('', None):
            self.assertEqual(self.badge({'fecha_limite': value}), ('Sin vencimiento', '#F1F5F9', '#475569'))

    def test_existing_normal_labels(self):
        for days, prefix in ((-1, 'Vencida · '), (0, 'Vence hoy · '), (3, 'Vence en 3 días · '), (10, 'Vence ')):
            day = date.today() + timedelta(days=days)
            self.assertEqual(self.badge({'fecha_limite': day.isoformat()})[0], prefix + day.strftime('%d/%m/%Y'))
        self.assertEqual(self.badge({'estado': 'Finalizada'}), ('✓ Finalizada', '#DCFCE7', '#166534'))

    def test_previous_date_warning_and_reasons(self):
        for reason, prefix in (('Calendario no disponible', 'Calendario fiscal pendiente: Calendario no disponible'),
                               ('Falta período', 'Datos fiscales por revisar: Falta período'),
                               ('', 'Vencimiento fiscal pendiente')):
            row = {'categoria': 'IVA', 'fecha_limite': '2026-01-01',
                   'id_externo': 'fiscal:v1:' + json.dumps({'estado': 'pendiente', 'motivo': reason})}
            self.assertEqual(self.badge(row), (prefix + ' · fecha previa sin verificar: 2026-01-01', '#FEF3C7', '#92400E'))

    def test_textual_contract_for_existing_consumers(self):
        for row, expected in (({}, ''), ({'recurrente': 'Sí', 'categoria': 'IVA'}, 'Vencimiento fiscal pendiente')):
            label = self.env['pending_label'](row)
            self.assertIsInstance(label, str)
            self.assertEqual(label, expected)
            self.assertEqual(bool(label), bool(expected))
            self.assertEqual(f'label: {label or "normal"}', 'label: ' + (expected or 'normal'))

    def test_ambiguous_selection_fails(self):
        with self.assertRaisesRegex(AssertionError, 'found 2'):
            unique([object(), object()], 'badge assignment')
