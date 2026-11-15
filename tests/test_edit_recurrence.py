import unittest
from sqlalchemy import text
from test_tax_persistence import PersistenceTests
from am_hub_tasks import guardar_detalle_tarea_postgres

class EditRecurrenceTests(PersistenceTests):
    def labor(self):
        with self.db.begin() as c:
            c.execute(text("UPDATE tareas SET tarea='Boletas sindicales', categoria='BOLETAS SINDICALES', id_externo='', fecha_limite='2026-11-12', frecuencia='Diaria'"))
    def test_edit_only_does_not_generate(self):
        self.labor()
        r=guardar_detalle_tarea_postgres(self.engine,'one',{'frecuencia':'Mensual','intervalo':3},'Pendiente','test')
        self.assertIsNone(r['generada'])
        with self.db.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM tareas')).scalar(),1)
            self.assertEqual(c.execute(text('SELECT frecuencia FROM tareas')).scalar(),'Mensual')
    def test_edit_and_finish_uses_new_rule(self):
        self.labor()
        r=guardar_detalle_tarea_postgres(self.engine,'one',{'frecuencia':'Mensual','intervalo':3},'Finalizada','test')
        self.assertEqual(r['generada']['fecha_limite'],'2027-02-12')
        self.assertEqual(r['generada']['frecuencia'],'Mensual')
        self.assertIsNone(guardar_detalle_tarea_postgres(self.engine,'one',{},'Finalizada','test')['generada'])
    def test_disabling_avoids_next(self):
        self.labor()
        r=guardar_detalle_tarea_postgres(self.engine,'one',{'recurrente':'No'},'Finalizada','test')
        self.assertIsNone(r['generada'])
    def test_enabling_and_finishing_creates_next(self):
        self.labor()
        with self.db.begin() as c: c.execute(text("UPDATE tareas SET recurrente='No'"))
        r=guardar_detalle_tarea_postgres(self.engine,'one',{'recurrente':'Sí','frecuencia':'Mensual'},'Finalizada','test')
        self.assertEqual(r['generada']['fecha_limite'],'2026-12-12')
    def test_fiscal_failure_rolls_back_fields(self):
        with self.assertRaises(ValueError):
            guardar_detalle_tarea_postgres(self.engine,'one',{'fecha_limite':'2026-12-31'},'Finalizada','test')
        with self.db.connect() as c:
            self.assertEqual(c.execute(text('SELECT fecha_limite FROM tareas')).scalar(),'2026-12-18')
