import unittest
from am_hub_tasks import descripcion_siguiente_ocurrencia, construir_siguiente_ocurrencia
from am_hub_tax_calendar import encode_metadata

class SuccessorDescriptionTests(unittest.TestCase):
    def result(self, period='2026-11', due='2026-12-15', state='verificado'):
        return dict(contexto=dict(periodo=period,estado=state),fecha=due,motivo='')
    def test_free_text_dates_and_history_preserved(self):
        original='Período: octubre 2026. Vencimiento: 13/11/2026.\nNo modificar factura 10/2026 ni pago 13/11/2026.\n'
        desc=descripcion_siguiente_ocurrencia(original,self.result())
        self.assertTrue(desc.startswith('[AM HUB: datos de esta ocurrencia]\nPeríodo de esta ocurrencia: 2026-11\nVencimiento de esta ocurrencia: 2026-12-15'))
        self.assertTrue(desc.endswith(original));self.assertIn('son antecedentes',desc)
    def test_second_generation_replaces_header_without_growth(self):
        original='Primer período: octubre 2026. Nota libre.'
        first=descripcion_siguiente_ocurrencia(original,self.result())
        second=descripcion_siguiente_ocurrencia(first,self.result('2026-12','2027-01-15'))
        self.assertEqual(second.count('[AM HUB: datos de esta ocurrencia]'),1)
        self.assertEqual(second.count('Notas heredadas'),1)
        self.assertNotIn('2026-12-15',second);self.assertTrue(second.endswith(original))
    def test_pending_and_estimated_never_claim_official(self):
        self.assertIn('Pendiente de validar',descripcion_siguiente_ocurrencia('',self.result(due='',state='pendiente')))
        self.assertIn('Fecha de control estimada (no oficial)',descripcion_siguiente_ocurrencia('',self.result(state='estimado')))
    def test_actual_successor_and_source_untouched(self):
        desc='Período fiscal: 2026-11. Instrucción libre.'
        t=dict(id='test',cliente='test',recurrente='Sí',frecuencia='Mensual',intervalo=1,descripcion=desc,
               id_externo=encode_metadata(dict(impuesto='IVA',obligacion='MENSUAL',jurisdiccion='NACIONAL',periodo='2026-11',modo_fecha='preventiva_sin_cuit',dia_control=20)))
        n=construir_siguiente_ocurrencia(t,'test',calendario=[])
        self.assertIn('Período de esta ocurrencia: 2026-12',n['descripcion'])
        self.assertIn('2027-01-20',n['descripcion']);self.assertEqual(t['descripcion'],desc)
    def test_non_fiscal_remains_exact(self):
        t=dict(id='test',tarea='Visitar',descripcion='Visita anterior 2026-11-10',fecha_limite='2026-11-20',frecuencia='Mensual')
        self.assertEqual(construir_siguiente_ocurrencia(t,'test')['descripcion'],t['descripcion'])
