import unittest
from sqlalchemy import text
from test_tax_persistence import PersistenceTests
from am_hub_tax_calendar import metadata, encode_metadata, resolve, apply_resolution, pending_label, fiscal_period_label, validate_completion
from am_hub_tasks import actualizar_estado_tarea_postgres

class PreventiveCompletionTests(PersistenceTests):
    def configure_control(self):
        with self.db.begin() as c:
            t=dict(c.execute(text("SELECT * FROM tareas WHERE id='one'")).mappings().one())
            m=metadata(t);m.update(periodo='2026-10',terminacion=0,modo_fecha='control_alta_periodo')
            t['id_externo']=encode_metadata(m)
            t=apply_resolution(t,resolve(t))
            t['descripcion']='CONTROL PREVENTIVO: verificar alta y período; no acredita DDJJ.'
            c.execute(text("UPDATE tareas SET id_externo=:id_externo,fecha_limite=:fecha_limite,descripcion=:descripcion WHERE id='one'"),t)
        return t
    def test_control_completes_and_keeps_next_as_control(self):
        t=self.configure_control()
        self.assertEqual(t['fecha_limite'],'2026-11-17')
        self.assertEqual(pending_label(t),'')
        self.assertIn('no acredita presentación',fiscal_period_label(t))
        n=actualizar_estado_tarea_postgres(self.engine,'one','Finalizada','test')['generada']
        self.assertEqual(n['fecha_limite'],'2026-12-15')
        self.assertEqual(metadata(n)['estado'],'control')
        self.assertEqual(metadata(n)['periodo'],'2026-11')
        self.assertIn('alta/obligación por verificar',n['descripcion'])
        self.assertIsNone(actualizar_estado_tarea_postgres(self.engine,'one','Finalizada','test')['generada'])
        actualizar_estado_tarea_postgres(self.engine,'one','Pendiente','test')
        self.assertIsNone(actualizar_estado_tarea_postgres(self.engine,'one','Finalizada','test')['generada'])
    def test_control_does_not_bypass_missing_period_or_wrong_date(self):
        t=self.configure_control();t['fecha_limite']='2026-11-30'
        with self.assertRaises(ValueError):validate_completion(t)
        m=metadata(t);m.pop('periodo');t['id_externo']=encode_metadata(m)
        with self.assertRaises(ValueError):validate_completion(t)
    def test_standard_pending_remains_blocked(self):
        t=self.configure_control();m=metadata(t);m.pop('modo_fecha');m.update(estado='pendiente',motivo='Falta período')
        with self.db.begin() as c:c.execute(text("UPDATE tareas SET id_externo=:m WHERE id='one'"),{'m':encode_metadata(m)})
        with self.assertRaises(ValueError):actualizar_estado_tarea_postgres(self.engine,'one','Finalizada','test')
