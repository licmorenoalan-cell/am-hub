"""Exercise the actual recurrence widgets without database or authentication."""
from pathlib import Path
import textwrap
import unittest

from streamlit.testing.v1 import AppTest
from am_hub_tasks import siguiente_fecha_recurrente


class RecurrenceFormTests(unittest.TestCase):
    def app(self):
        source = Path(__file__).resolve().parents[1].joinpath('app.py').read_text()
        start = source.index('                es_recurrente = st.checkbox(')
        end = source.index('            crear = st.form_submit_button(', start)
        widgets = textwrap.dedent(source[start:end])
        options_start = source.index('    frecuencias = [')
        options_end = source.index('\n    unidades_base', options_start)
        options = textwrap.dedent(source[options_start:options_end])
        return AppTest.from_string(
            'import streamlit as st\nui = lambda x: x\n' + options +
            '\nwith st.form("test"):\n' + textwrap.indent(widgets, '    ') +
            '\n    if st.form_submit_button("Crear"):\n'
            '        st.session_state["submitted"] = (es_recurrente, frecuencia_sel, intervalo_sel)\n'
        ).run()

    def test_controls_visible_before_checkbox_and_no_silent_daily_default(self):
        app = self.app()
        self.assertFalse(app.checkbox[0].value)
        self.assertIsNone(app.selectbox[0].value)
        self.assertEqual(app.number_input[0].value, 1)
        self.assertFalse(app.exception)

    def test_select_custom_interval_in_single_submission(self):
        for frequency, interval in [('Semanal', 2), ('Mensual', 3), ('Mensual', 12), ('Diaria', 30)]:
            with self.subTest(frequency=frequency, interval=interval):
                app = self.app()
                app.checkbox[0].check()
                app.selectbox[0].select(frequency)
                app.number_input[0].set_value(interval)
                app.button[0].click().run()
                self.assertEqual(app.session_state['submitted'], (True, frequency, interval))
                self.assertFalse(app.exception)

    def test_unchecking_preserves_input_but_marks_nonrecurring(self):
        app = self.app()
        app.checkbox[0].check()
        app.selectbox[0].select('Mensual')
        app.button[0].click().run()
        app.checkbox[0].uncheck()
        app.button[0].click().run()
        self.assertEqual(app.session_state['submitted'], (False, 'Mensual', 1))

    def test_creation_validates_frequency_and_clears_nonrecurring_metadata(self):
        source = Path(__file__).resolve().parents[1].joinpath('app.py').read_text()
        self.assertIn('elif es_recurrente and not frecuencia_sel:', source)
        self.assertIn('"frecuencia": frecuencia_sel if es_recurrente else ""', source)
        self.assertIn('"intervalo": int(intervalo_sel) if es_recurrente else 1', source)

    def test_custom_schedules_use_existing_engine(self):
        for frequency, interval, expected in [
            ('Diaria', 15, '2026-11-27'), ('Semanal', 2, '2026-11-26'),
            ('Mensual', 3, '2027-02-12'), ('Mensual', 12, '2027-11-12'),
            ('Semestral', 1, '2027-05-12'),
            ('Primer día hábil del mes', 1, '2026-12-01'),
            ('Último día hábil del mes', 1, '2026-12-31'),
        ]:
            self.assertEqual(siguiente_fecha_recurrente('2026-11-12', frequency, interval), expected)
