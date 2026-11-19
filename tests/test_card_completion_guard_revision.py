import unittest
from unittest.mock import Mock, patch

from am_hub_tasks import construir_siguiente_ocurrencia, MISSING_RECURRENCE_DATE, actualizar_estado_tarea_en_conexion
from am_hub_tax_calendar import is_fiscal, encode_metadata


class CompletionGuardTests(unittest.TestCase):
    def test_blank_or_invalid_date_never_invents_a_next_date(self):
        for fecha in ('', 'NaT', 'no es una fecha', None):
            task = dict(id='m', tarea='Enviar minuta', categoria='Marketing', recurrente='Sí', frecuencia='Mensual', fecha_limite=fecha)
            with self.subTest(fecha=fecha), self.assertRaisesRegex(ValueError, MISSING_RECURRENCE_DATE):
                construir_siguiente_ocurrencia(task, 'test')

    def test_no_writes_when_missing_date_raises(self):
        task = dict(id='m', tarea='Enviar minuta', categoria='Marketing', estado='Pendiente',
                    recurrente='Sí', frecuencia='Mensual', fecha_limite='')
        conn = Mock()
        conn.execute.return_value.mappings.return_value.first.return_value = task
        with self.assertRaisesRegex(ValueError, MISSING_RECURRENCE_DATE):
            actualizar_estado_tarea_en_conexion(conn, 'm', 'Finalizada', 'test')
        self.assertEqual(conn.execute.call_count, 1)
        self.assertTrue(str(conn.execute.call_args.args[0]).startswith('SELECT'))

    def test_explicit_operational_category_note_not_fiscal(self):
        task = dict(id='m', tarea='Preparar piezas', categoria=' Marketing  ',
                    descripcion='Ideas de contenido sobre IVA', recurrente='Sí',
                    frecuencia='Mensual', fecha_limite='2026-11-19')
        self.assertFalse(is_fiscal(task))
        result = construir_siguiente_ocurrencia(task, 'test')
        self.assertEqual(result['fecha_limite'], '2026-12-19')
        self.assertEqual(result['ocurrencia'], '2')

    def test_legacy_admin_and_positive_fiscal_signals_keep_precedence(self):
        for categoria in ('Administración', 'Bandeja de entrada', 'Obligaciones fiscales', 'Gestiones', ''):
            self.assertTrue(is_fiscal(dict(categoria=categoria, descripcion='Presentar IVA')))
        self.assertTrue(is_fiscal(dict(categoria='Marketing', tarea='IVA 2026-10')))
        self.assertTrue(is_fiscal(dict(categoria='Marketing', tarea='Pendiente',
                                      id_externo=encode_metadata({'impuesto':'IVA'}))))
        self.assertTrue(is_fiscal(dict(categoria='IVA', tarea='Declaración')))


if __name__ == '__main__':
    unittest.main()
