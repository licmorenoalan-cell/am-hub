"""Test Pocket's actual handlers without importing UI startup or live config."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock


class PocketStateErrorTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path(__file__).parents[1].joinpath('pocket_app.py').read_text())
        names = {'mensaje_error_actualizacion', 'actualizar_estado'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.assertEqual(len(nodes), 2)
        self.env = dict(st=Mock(), logger=Mock(), get_engine=Mock(return_value=object()),
                        get_secret=Mock(return_value='test'), limpiar_cache=Mock(),
                        actualizar_estado_tarea_postgres=Mock())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<Pocket actual handlers>', 'exec'), self.env)

    def fail_with(self, error):
        self.env['actualizar_estado_tarea_postgres'].side_effect = error
        self.assertFalse(self.env['actualizar_estado']('test-id', 'Finalizada'))
        self.env['limpiar_cache'].assert_not_called()
        self.env['actualizar_estado_tarea_postgres'].assert_called_once_with(
            self.env['get_engine'].return_value, 'test-id', 'Finalizada', 'test')
        return self.env['st'].error.call_args.args[0]

    def test_known_fiscal_reason_is_visible(self):
        message = self.fail_with(ValueError(
            'Vencimiento fiscal pendiente: fecha no validada contra el calendario oficial.'))
        self.assertIn('fecha no está validada contra el calendario oficial', message)
        self.assertIn('La recurrencia no se modificó.', message)

    def test_all_known_fiscal_reasons_have_controlled_messages(self):
        cases = {
            'completar los datos y el calendario antes de finalizar.': 'faltan datos fiscales',
            'frecuencia no válida; no se repite el período anterior.': 'frecuencia fiscal no es válida',
            'falta período de origen; no se genera una ocurrencia sin período.': 'falta el período fiscal',
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                message = self.env['mensaje_error_actualizacion'](ValueError('Vencimiento fiscal pendiente: ' + source))
                self.assertIn(expected, message)

    def test_unknown_valueerror_is_generic_and_not_leaked(self):
        message = self.fail_with(ValueError('Vencimiento fiscal pendiente: secret-db-value'))
        self.assertNotIn('secret-db-value', message)
        self.assertIn('No pudimos actualizar la tarjeta.', message)

    def test_unexpected_error_is_generic_even_with_known_text(self):
        message = self.fail_with(RuntimeError(
            'Vencimiento fiscal pendiente: fecha no validada contra el calendario oficial.'))
        self.assertIn('No pudimos actualizar la tarjeta.', message)
        self.assertNotIn('calendario oficial', message)

    def test_success_still_calls_engine_once_and_clears_cache(self):
        self.assertTrue(self.env['actualizar_estado']('test-id', 'Finalizada'))
        self.env['actualizar_estado_tarea_postgres'].assert_called_once()
        self.env['limpiar_cache'].assert_called_once()
        self.env['st'].error.assert_not_called()


if __name__ == '__main__':
    unittest.main()
