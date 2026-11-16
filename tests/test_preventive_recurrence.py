import unittest
from am_hub_tax_calendar import encode_metadata, metadata, resolve, apply_resolution, pending_label, fiscal_period_label, validate_completion
from am_hub_tasks import construir_siguiente_ocurrencia

class PreventiveRecurrenceTests(unittest.TestCase):
    def task(self, tax='IVA'):
        m=dict(impuesto=tax, obligacion='MENSUAL' if tax=='IVA' else 'CM03', jurisdiccion='NACIONAL' if tax=='IVA' else 'COMARB', periodo='2026-11', modo_fecha='preventiva_sin_cuit', dia_control=20 if tax=='IVA' else 13)
        t=dict(id='x',cliente='Demo',categoria=tax,recurrente='Sí',frecuencia='Mensual',intervalo=1,id_externo=encode_metadata(m))
        return apply_resolution(t, resolve(t, calendar=[]))
    def test_repeat_without_cuit_and_year_rollover(self):
        for tax,day in [('IVA',20),('IIBB',13)]:
            t=self.task(tax)
            self.assertEqual(t['fecha_limite'],f'2026-12-{day}')
            self.assertEqual(pending_label(t),'')
            self.assertIn('no vencimiento fiscal oficial', fiscal_period_label(t))
            validate_completion(t)
            n=construir_siguiente_ocurrencia(t,'test',calendario=[])
            self.assertEqual(n['fecha_limite'],f'2027-01-{day}')
            self.assertEqual(metadata(n)['periodo'],'2026-12')
            self.assertEqual(metadata(n)['estado'],'estimado')
            self.assertEqual(construir_siguiente_ocurrencia(n,'test',calendario=[])['fecha_limite'],f'2027-02-{day}')
    def test_normal_missing_cuit_stays_blocked(self):
        t=self.task(); m=metadata(t);m.pop('modo_fecha');t['id_externo']=encode_metadata(m)
        r=resolve(t,calendar=[])
        self.assertIn('CUIT',r['motivo']); self.assertEqual(r['fecha'],'')
    def test_invalid_mode_fails_closed(self):
        t=self.task();m=metadata(t);m['dia_control']=30;t['id_externo']=encode_metadata(m)
        self.assertTrue(resolve(t,calendar=[])['motivo'])
        with self.assertRaises(ValueError):validate_completion(t)
    def test_cuit_uses_official_calendar_only(self):
        t=self.task(); profiles=[dict(cliente='Demo',cuit='30719024420')]
        r=resolve(t, profiles, [],next_period=True)
        self.assertEqual(r['fecha'],''); self.assertIn('Calendario',r['motivo'])
        self.assertNotIn('modo_fecha',r['contexto'])
        row=dict(impuesto='IVA',obligacion='MENSUAL',jurisdiccion='NACIONAL',periodo='2026-12',terminaciones=[0],vencimiento='2027-01-18',verificado=True,fuente='https://official.example',norma='test',verificado_el='2026-11-16')
        r=resolve(t,profiles,[row],next_period=True)
        self.assertEqual(r['fecha'],'2027-01-18');self.assertEqual(r['contexto']['estado'],'verificado')
    def test_no_auto_finalization(self):
        t=self.task();t['estado']='Pendiente';n=construir_siguiente_ocurrencia(t,'test',calendario=[])
        self.assertEqual(t['estado'],'Pendiente');self.assertEqual(n['estado'],'Pendiente')
if __name__=='__main__':unittest.main()
