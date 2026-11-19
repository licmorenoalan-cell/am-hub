from contextlib import contextmanager
import unittest

from sqlalchemy import create_engine, text

from am_hub_tasks import construir_siguiente_ocurrencia
from am_hub_tax_calendar import encode_metadata, metadata
from am_hub_verified_iva import inspect_or_apply

_TEST_CUIT = '30-00000000-3'
_ARGS = ('admin_general', 'Test User', 't1', '2026-10')


class Engine:
    def __init__(self, db):
        self.db = db

    @contextmanager
    def begin(self):
        with self.db.begin() as connection:
            class Connection:
                def execute(self, stmt, params=None):
                    sql = str(stmt).replace(' FOR UPDATE', '').replace(' FOR SHARE', '')
                    return connection.execute(text(sql), params or {})
            yield Connection()


class VerifiedIvaAdminCloseTests(unittest.TestCase):
    def setUp(self):
        self.db = create_engine('sqlite://')
        self.addCleanup(self.db.dispose)
        self.engine = Engine(self.db)
        self.seed = {
            'id':'t1','tarea':'Presentar IVA','cliente':'Fixture only','categoria':'IVA',
            'estado':'Pendiente','fecha_limite':'2026-11-19','recurrente':'Sí',
            'frecuencia':'Mensual','ocurrencia':2,'intervalo':1,'serie_id':'series',
            'id_externo':encode_metadata({'impuesto':'IVA','estado':'pendiente','motivo':'Falta periodo'}),
            'comentarios':'Nota anterior\nVencimiento fiscal pendiente: Falta periodo',
            'descripcion':'Descripción original',
        }
        schema_row = dict(self.seed, id_externo=encode_metadata({'periodo':'2026-10','terminacion':3}))
        cols = sorted(set(self.seed) | set(construir_siguiente_ocurrencia(schema_row, 'test')))
        with self.db.begin() as conn:
            conn.execute(text('CREATE TABLE tareas (' + ','.join(
                f'"{k}" ' + ('INTEGER' if k in {'ocurrencia','intervalo','avance'} else 'TEXT')
                for k in cols) + ')'))
            conn.execute(text('CREATE TABLE fiscal_clientes (cliente TEXT,cuit TEXT,iibb_regimen TEXT,iibb_jurisdiccion TEXT)'))
            conn.execute(text('INSERT INTO fiscal_clientes VALUES (:cliente,:cuit,\'\',\'\')'),
                         {'cliente':self.seed['cliente'],'cuit':_TEST_CUIT})
        self.insert(self.seed)

    def insert(self, row):
        with self.db.begin() as conn:
            conn.execute(text('INSERT INTO tareas (' + ','.join(row) + ') VALUES (' + ','.join(':' + k for k in row) + ')'), row)

    def rows(self):
        with self.db.connect() as conn:
            return [dict(r) for r in conn.execute(text('SELECT * FROM tareas ORDER BY ocurrencia')).mappings()]

    def preview(self):
        return inspect_or_apply(self.engine, *_ARGS)

    def test_close_is_atomic_and_preserves_recurrence(self):
        initial = self.rows()
        preview = self.preview()
        self.assertEqual(initial, self.rows())
        self.assertEqual((preview['proximo_periodo'],preview['proxima_fecha']),('2026-11','2026-12-21'))
        inspect_or_apply(self.engine, *_ARGS, revision=preview['revision'])
        parent, child = self.rows()
        self.assertEqual((parent['estado'],child['estado']),('Finalizada','Pendiente'))
        self.assertEqual(metadata(parent)['periodo'],'2026-10')
        self.assertEqual(metadata(child)['periodo'],'2026-11')
        self.assertEqual((parent['recurrente'],child['recurrente']),('Sí','Sí'))
        self.assertEqual(parent['comentarios'],'Nota anterior')
        with self.assertRaises(ValueError):
            inspect_or_apply(self.engine, *_ARGS, revision=preview['revision'])
        self.assertEqual(len(self.rows()),2)

    def test_forbidden_role_missing_profile_and_bad_period_do_not_write(self):
        initial=self.rows()
        with self.assertRaises(PermissionError):
            inspect_or_apply(self.engine, 'admin', *_ARGS[1:])
        with self.assertRaises(ValueError):
            inspect_or_apply(self.engine, *_ARGS[:-1], 'invalido')
        with self.db.begin() as conn:
            conn.execute(text("UPDATE fiscal_clientes SET cuit=''"))
        with self.assertRaisesRegex(ValueError,'ficha fiscal'):
            self.preview()
        self.assertEqual(initial,self.rows())

    def test_wrong_date_and_stale_preview_do_not_write(self):
        preview=self.preview()
        with self.db.begin() as conn:
            conn.execute(text("UPDATE tareas SET descripcion='Otra edición'"))
        with self.assertRaisesRegex(ValueError,'después de la revisión'):
            inspect_or_apply(self.engine,*_ARGS,revision=preview['revision'])
        with self.db.begin() as conn:
            conn.execute(text("UPDATE tareas SET fecha_limite='2026-11-20'"))
        with self.assertRaisesRegex(ValueError,'calendario oficial'):
            self.preview()
        self.assertEqual([r['estado'] for r in self.rows()],['Pendiente'])

    def test_existing_correct_successor_is_reused(self):
        child=construir_siguiente_ocurrencia(dict(self.seed,id_externo=encode_metadata(
            {'periodo':'2026-10','terminacion':3})),'Test User')
        self.insert(child)
        preview=self.preview()
        self.assertTrue(preview['reutiliza'])
        result=inspect_or_apply(self.engine,*_ARGS,revision=preview['revision'])
        self.assertFalse(result['nueva'])
        self.assertEqual(result['siguiente_id'],child['id'])
        self.assertEqual(len(self.rows()),2)

    def test_other_open_series_for_november_is_not_duplicated(self):
        self.insert(dict(self.seed,id='t2',serie_id='another',fecha_limite='2026-12-21',
                         id_externo=encode_metadata({'periodo':'2026-11'})))
        with self.assertRaisesRegex(ValueError,'otra tarjeta'):
            self.preview()
        self.assertEqual([r['estado'] for r in self.rows()],['Pendiente','Pendiente'])
