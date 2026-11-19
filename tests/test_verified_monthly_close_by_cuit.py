"""Exercise real deadline resolution and atomic closure on disposable fixtures."""
import unittest

from sqlalchemy import create_engine, text

from am_hub_tasks import actualizar_estado_tarea_postgres, construir_siguiente_ocurrencia
from am_hub_tax_calendar import encode_metadata, metadata
from test_tax_persistence import Engine


class VerifiedMonthlyCloseByCuitTests(unittest.TestCase):
    def seed(self, *, tax, suffix, due, regime='', province='', period='2026-10'):
        db = create_engine('sqlite://')
        self.addCleanup(db.dispose)
        row = {
            'id': 'origin', 'cliente': 'Fixture Fiscal', 'tarea': tax, 'categoria': tax,
            'estado': 'Pendiente', 'fecha_limite': due, 'recurrente': 'Sí',
            'frecuencia': 'Mensual', 'intervalo': 1, 'ocurrencia': 1, 'serie_id': 'series',
            'id_externo': encode_metadata({'periodo': period}) if period else '',
        }
        profile = {
            'cliente': 'fixture fiscal', 'cuit': f'30-00000000-{suffix}',
            'iibb_regimen': regime, 'iibb_jurisdiccion': province,
        }
        schema_row = dict(row, tarea='IVA', categoria='IVA',
                          id_externo=encode_metadata({'periodo': '2026-10'}))
        columns = sorted(set(construir_siguiente_ocurrencia(schema_row, 'test', perfiles=[profile])) | set(row))
        with db.begin() as conn:
            conn.execute(text('CREATE TABLE tareas (' + ','.join(
                f'"{k}" ' + ('INTEGER' if k in ('ocurrencia', 'intervalo', 'avance') else 'TEXT')
                for k in columns) + ')'))
            conn.execute(text('CREATE TABLE fiscal_clientes (cliente TEXT,cuit TEXT,iibb_regimen TEXT,iibb_jurisdiccion TEXT)'))
            conn.execute(text('INSERT INTO tareas (' + ','.join(row) + ') VALUES (' + ','.join(':' + k for k in row) + ')'), row)
            conn.execute(text('INSERT INTO fiscal_clientes VALUES (:cliente,:cuit,:iibb_regimen,:iibb_jurisdiccion)'), profile)
        return db, Engine(db)

    def test_monthly_deadlines_follow_profile_cuit_and_regime(self):
        cases = (
            ('IVA', 3, 'Convenio Multilateral', '', '2026-11-19', '2026-12-21', 'NACIONAL'),
            ('IVA', 8, 'AGIP régimen general', 'CABA', '2026-11-25', '2026-12-24', 'NACIONAL'),
            ('Ingresos Brutos', 3, 'Convenio Multilateral', '', '2026-11-18', '2026-12-16', 'COMARB'),
            ('Ingresos Brutos', 8, 'Convenio Multilateral', '', '2026-11-20', '2026-12-18', 'COMARB'),
            ('Ingresos Brutos', 3, 'AGIP régimen general', 'CABA', '2026-11-12', '2026-12-14', 'CABA'),
            ('Ingresos Brutos', 8, 'ARBA régimen general', 'Buenos Aires', '2026-11-30', '2026-12-29', 'BUENOS AIRES'),
        )
        for tax, suffix, regime, province, due, next_due, jurisdiction in cases:
            with self.subTest(tax=tax, suffix=suffix, regime=regime):
                db, engine = self.seed(tax=tax, suffix=suffix, regime=regime, province=province, due=due)
                new = actualizar_estado_tarea_postgres(engine, 'origin', 'Finalizada', 'test')['generada']
                ctx = metadata(new)
                self.assertEqual((ctx['periodo'], ctx['terminacion'], ctx['jurisdiccion']),
                                 ('2026-11', suffix, jurisdiction))
                self.assertEqual((new['fecha_limite'], new['serie_id'], new['recurrente'], new['frecuencia']),
                                 (next_due, 'series', 'Sí', 'Mensual'))
                self.assertIsNone(actualizar_estado_tarea_postgres(engine, 'origin', 'Finalizada', 'test')['generada'])
                actualizar_estado_tarea_postgres(engine, 'origin', 'Pendiente', 'test')
                self.assertIsNone(actualizar_estado_tarea_postgres(engine, 'origin', 'Finalizada', 'test')['generada'])
                with db.connect() as conn:
                    saved = conn.execute(text('SELECT estado,fecha_limite FROM tareas ORDER BY ocurrencia')).all()
                    self.assertEqual(saved, [('Finalizada', due), ('Pendiente', next_due)])

    def test_without_next_official_calendar_recurrence_remains_pending_without_date(self):
        db, engine = self.seed(tax='IVA', suffix=3, due='2026-12-21', period='2026-11')
        new = actualizar_estado_tarea_postgres(engine, 'origin', 'Finalizada', 'test')['generada']
        self.assertEqual(metadata(new)['periodo'], '2026-12')
        self.assertEqual((new['estado'], new['fecha_limite'], new['recurrente']), ('Pendiente', '', 'Sí'))
        with db.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT COUNT(*) FROM tareas')).scalar_one(), 2)

    def test_date_alone_does_not_confirm_old_period(self):
        db, engine = self.seed(tax='IVA', suffix=3, due='2026-11-19', period='')
        with self.assertRaisesRegex(ValueError, 'Vencimiento fiscal pendiente'):
            actualizar_estado_tarea_postgres(engine, 'origin', 'Finalizada', 'test')
        with db.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT estado FROM tareas')).scalar_one(), 'Pendiente')
