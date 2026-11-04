import json
import sys
from pathlib import Path
import unittest
from sqlalchemy import create_engine, text
from am_hub_tasks import actualizar_estado_tarea_postgres, construir_siguiente_ocurrencia
from am_hub_tax_calendar import encode_metadata
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from audit_fiscal_recurrences import proposed
ALAN = "example-activation"


class Connection:
    def __init__(self, connection):
        self.connection=connection
    def execute(self, statement, params=None):
        return self.connection.execute(text(str(statement).replace(' FOR UPDATE','')),params or {})


class Transaction:
    def __init__(self, engine):
        self.engine=engine
    def __enter__(self):
        self.transaction=self.engine.begin()
        return Connection(self.transaction.__enter__())
    def __exit__(self,*args):
        return self.transaction.__exit__(*args)


class Engine:
    def __init__(self, engine): self.engine=engine
    def begin(self): return Transaction(self.engine)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.db=create_engine('sqlite://')
        seed={'id':'one','cliente':'','tarea':'CM03','categoria':'Ingresos Brutos',
              'estado':'Pendiente','fecha_limite':'2026-12-18','recurrente':'Sí',
              'frecuencia':'Mensual','intervalo':'1','ocurrencia':'1','serie_id':'series',
              'id_externo':encode_metadata(dict(impuesto='IIBB',obligacion='CM03',
                     jurisdiccion='COMARB',periodo='2026-11',terminacion=8))}
        cols=set(construir_siguiente_ocurrencia(seed,'test'))|set(seed)
        with self.db.begin() as c:
            c.execute(text('CREATE TABLE tareas ('+','.join('"'+k+'" '+('INTEGER' if k in ('intervalo','ocurrencia','avance') else 'TEXT') for k in cols)+')'))
            c.execute(text('CREATE TABLE fiscal_clientes (cliente TEXT,cuit TEXT,iibb_regimen TEXT,iibb_jurisdiccion TEXT)'))
            c.execute(text('INSERT INTO tareas ('+','.join(seed)+') VALUES ('+','.join(':'+k for k in seed)+')'),seed)
        self.engine=Engine(self.db)

    def test_complete_replay_and_reopen_do_not_duplicate(self):
        r=actualizar_estado_tarea_postgres(self.engine,'one','Finalizada','test')
        self.assertEqual(r['generada']['fecha_limite'],'2027-01-20')
        self.assertIsNone(actualizar_estado_tarea_postgres(self.engine,'one','Finalizada','test')['generada'])
        actualizar_estado_tarea_postgres(self.engine,'one','Pendiente','test')
        self.assertIsNone(actualizar_estado_tarea_postgres(self.engine,'one','Finalizada','test')['generada'])
        with self.db.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM tareas')).scalar(),2)

    def test_advance_cycle_transaction_replay_preserves_history_and_cm03(self):
        from am_hub_tax_calendar import metadata
        seed=dict(id='advance-origin',tarea='Anticipo Ganancias',frecuencia='Mensual',intervalo=2,
                  id_externo=encode_metadata(dict(impuesto='GANANCIAS',obligacion='ANTICIPO_PH',
                     jurisdiccion='NACIONAL',periodo='2026-12',terminacion=5)))
        fourth=construir_siguiente_ocurrencia(seed,'test',nueva_id='fourth')
        with self.db.begin() as c:
            c.execute(text('INSERT INTO tareas ('+','.join(fourth)+') VALUES ('+','.join(':'+k for k in fourth)+')'),fourth)
            for i in range(113):
                c.execute(text("INSERT INTO tareas(id,estado,comentarios) VALUES(:id,'Finalizada','History')"),{'id':f'history-{i}'})
            untouched=[dict(r) for r in c.execute(text("SELECT * FROM tareas WHERE id<>'fourth' ORDER BY id")).mappings()]
        fifth=actualizar_estado_tarea_postgres(self.engine,'fourth','Finalizada','test')['generada']
        self.assertIsNone(actualizar_estado_tarea_postgres(self.engine,'fourth','Finalizada','test')['generada'])
        actualizar_estado_tarea_postgres(self.engine,'fourth','Pendiente','test')
        self.assertIsNone(actualizar_estado_tarea_postgres(self.engine,'fourth','Finalizada','test')['generada'])
        first=actualizar_estado_tarea_postgres(self.engine,fifth['id'],'Finalizada','test')['generada']
        self.assertEqual(metadata(first)['periodo'],'2027-08')
        self.assertEqual(first['fecha_limite'],'')
        with self.assertRaises(ValueError):actualizar_estado_tarea_postgres(self.engine,first['id'],'Finalizada','test')
        with self.db.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM tareas')).scalar(),117)
            self.assertEqual([dict(r) for r in c.execute(text("SELECT * FROM tareas WHERE id='one' OR id LIKE 'history-%' ORDER BY id")).mappings()],untouched)

    def test_unknown_next_calendar_persists_and_cannot_be_finalized(self):
        r=actualizar_estado_tarea_postgres(self.engine,'one','Finalizada','test')
        r2=actualizar_estado_tarea_postgres(self.engine,r['generada']['id'],'Finalizada','test')
        self.assertEqual(r2['generada']['fecha_limite'],'')
        with self.assertRaisesRegex(ValueError,'Vencimiento fiscal pendiente'):
            actualizar_estado_tarea_postgres(self.engine,r2['generada']['id'],'Finalizada','test')
        with self.db.connect() as c:
            self.assertEqual(c.execute(text('SELECT estado FROM tareas WHERE id=:id'),{'id':r2['generada']['id']}).scalar(),'Pendiente')

    def test_activation_preserves_history_and_enables_alan_exactly(self):
        self.assertIsNone(proposed({'id':ALAN,'estado':'Finalizada'},[]))
        changes=proposed({'id':ALAN,'estado':'Pendiente','tarea':'CM03','categoria':'Ingresos Brutos','fecha_limite':'2027-01-20'},[],{ALAN:dict(impuesto='IIBB',obligacion='CM03',jurisdiccion='COMARB',periodo='2026-12',terminacion=8)},{ALAN:dict(tarea='CM03')})
        self.assertEqual(changes['fecha_limite'],'2027-01-20')
        self.assertEqual(changes['recurrente'],'Sí')
        self.assertEqual(changes['frecuencia'],'Mensual')
        self.assertNotIn('cuit',changes['id_externo'])

    def test_manually_changed_date_cannot_bypass_calendar(self):
        with self.db.begin() as c:
            c.execute(text("UPDATE tareas SET fecha_limite='2026-12-31' WHERE id='one'"))
        with self.assertRaisesRegex(ValueError,'calendario oficial'):
            actualizar_estado_tarea_postgres(self.engine,'one','Finalizada','test')

    def test_current_date_is_reconciled_when_config_becomes_available(self):
        t={'id':'x','tarea':'CM03','estado':'Pendiente','recurrente':'Sí','fecha_limite':'',
           'frecuencia':'Mensual','id_externo':'','comentarios':'Vencimiento fiscal pendiente: Falta periodo'}
        cfg={'x':dict(impuesto='IIBB',obligacion='CM03',jurisdiccion='COMARB',periodo='2026-12',terminacion=8)}
        changes=proposed(t,[],cfg)
        self.assertEqual(changes['fecha_limite'],'2027-01-20')
        self.assertEqual(changes['comentarios'],'')

    def test_pocket_detail_finishes_and_generates_in_same_transaction(self):
        import ast
        from datetime import date
        from am_hub_tasks import actualizar_estado_tarea_en_conexion
        source=ast.parse(Path(__file__).parents[1].joinpath('pocket_app.py').read_text())
        node=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='actualizar_detalle_tarea')
        ns=dict(date=date,get_engine=lambda:self.engine,get_secret=lambda *a:'test',
                text=text,serializar_checklist=json.dumps,limpiar_cache=lambda:None,
                actualizar_estado_tarea_en_conexion=actualizar_estado_tarea_en_conexion)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'pocket_app.py','exec'),ns)
        ns['actualizar_detalle_tarea']('one','AM Consultora','Fiscal','Finalizada','test','Alta','2026-12-18','',[],'Hecho')
        with self.db.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM tareas')).scalar(),2)
            self.assertEqual(c.execute(text("SELECT estado FROM tareas WHERE id='one'")).scalar(),'Finalizada')

    def test_grid_save_retains_generated_rows(self):
        import ast
        import pandas as pd
        source=ast.parse(Path(__file__).parents[1].joinpath('app.py').read_text())
        node=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='generar_recurrencias_desde_edicion')
        ns=dict(pd=pd,usar_postgres=lambda:True,get_postgres_engine=lambda:self.engine,
                actualizar_estado_tarea_postgres=actualizar_estado_tarea_postgres,
                _limpiar_cache_postgres=lambda:None)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'app.py','exec'),ns)
        with self.db.connect() as c:
            before=pd.DataFrame([dict(r) for r in c.execute(text('SELECT * FROM tareas')).mappings()])
        after=before.copy();after.loc[0,'estado']='Finalizada'
        saved=ns['generar_recurrencias_desde_edicion'](before,after,'test')
        self.assertEqual(len(saved),2)
        self.assertEqual(saved.iloc[1]['fecha_limite'],'2027-01-20')

    def test_audit_keeps_unverified_legacy_date_and_marks_review(self):
        from am_hub_tax_calendar import pending_label
        old={'id':'legacy','tarea':'IVA','recurrente':'Sí','estado':'Pendiente','fecha_limite':'2026-11-25'}
        result=proposed(old,[])
        self.assertEqual(result['fecha_limite'],'2026-11-25')
        self.assertIn('fecha previa sin verificar',pending_label(dict(old,**result)))

    def test_legacy_date_without_period_cannot_generate_by_completion(self):
        with self.db.begin() as c:
            c.execute(text("UPDATE tareas SET id_externo='', descripcion='' WHERE id='one'"))
        with self.assertRaisesRegex(ValueError,'Vencimiento fiscal pendiente'):
            actualizar_estado_tarea_postgres(self.engine,'one','Finalizada','test')
        with self.db.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM tareas')).scalar(),1)

    def test_audit_plan_roundtrip_is_idempotent_and_preserves_completed_rows(self):
        from audit_fiscal_recurrences import audit
        with self.db.begin() as c:
            c.execute(text("INSERT INTO tareas (id,tarea,estado,recurrente,fecha_limite,comentarios) VALUES ('legacy','IVA','Pendiente','Sí','2026-11-25','Nota conservada'),('done','IVA','Finalizada','Sí','2026-10-20','Historial')"))
            before_done=dict(c.execute(text("SELECT * FROM tareas WHERE id='done'")).mappings().one())
            planned=audit(Connection(c))
            applied=audit(Connection(c),apply=True)
            self.assertEqual(planned,applied)
        with self.db.connect() as c:
            self.assertEqual(audit(Connection(c)),[])
            self.assertEqual(dict(c.execute(text("SELECT * FROM tareas WHERE id='done'")).mappings().one()),before_done)
            legacy=c.execute(text("SELECT * FROM tareas WHERE id='legacy'")).mappings().one()
            self.assertEqual(legacy['fecha_limite'],'2026-11-25')
            self.assertIn('Nota conservada',legacy['comentarios'])

    def test_activation_roundtrip_needs_only_last_digit(self):
        t={'id':ALAN,'estado':'Pendiente','tarea':'CM03','fecha_limite':'2027-01-20','cliente':''}
        cfg={ALAN:dict(impuesto='IIBB',obligacion='CM03',jurisdiccion='COMARB',periodo='2026-12',terminacion=8)}
        activations={ALAN:dict(tarea='CM03')}
        first=proposed(t,[],cfg,activations)
        second=proposed(dict(t,**first),[],cfg,activations)
        self.assertEqual(first,second)
        self.assertEqual(first['fecha_limite'],'2027-01-20')
        self.assertEqual(first['recurrente'],'Sí')
        self.assertNotIn('cuit',json.dumps(first).lower())
