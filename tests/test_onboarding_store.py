import unittest
from unittest.mock import Mock
from sqlalchemy import create_engine, text
from am_hub_onboarding_store import (apply_plan, snapshot_onboarding, snapshot_fingerprint,
                                    _apply_locked, OnboardingConflict)


class OnboardingStoreTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite:///:memory:')
        with self.engine.begin() as c:
            c.execute(text('CREATE TABLE clientes (cliente TEXT PRIMARY KEY, servicio_contabilidad TEXT, notas TEXT)'))
            c.execute(text('CREATE TABLE fiscal_clientes (id TEXT PRIMARY KEY, cliente TEXT, cuit TEXT, razon_social TEXT, email_destinatarios TEXT, fecha_actualizacion TEXT, actualizado_por TEXT)'))
            c.execute(text('CREATE TABLE tareas (id TEXT PRIMARY KEY, cliente TEXT, tarea TEXT, descripcion TEXT, fecha_limite TEXT, estado TEXT)'))
        self.profile=dict(id='P1',cliente='PRUEBA',cuit='27408847112',razon_social='PRUEBA',fecha_actualizacion='2026-11-17')
        self.task=dict(id='T1',cliente='PRUEBA',tarea='IVA',descripcion='Test',fecha_limite='2026-11-18',estado='Pendiente')
        self.plan=dict(profile=self.profile,tasks=[self.task],conflicts=[])
        self.master=dict(cliente='PRUEBA',servicio_contabilidad='Sí',notas='')

    def apply(self, plan=None, fingerprint=None, client_insert=True):
        if fingerprint is None:fingerprint=snapshot_onboarding(self.engine)['fingerprint']
        with self.engine.begin() as c:
            return _apply_locked(c,self.plan if plan is None else plan,fingerprint,self.master if client_insert else None)

    def test_new_and_idempotent_replay(self):
        before=snapshot_onboarding(self.engine)['fingerprint']
        result=self.apply(fingerprint=before)
        self.assertEqual([x['table'] for x in result['changes']],['clientes','fiscal_clientes','tareas'])
        again=self.apply(fingerprint=before)
        self.assertFalse(again['changed'])
        self.assertEqual(len(snapshot_onboarding(self.engine)['tasks']),1)

    def test_existing_profile_fill_only_blank_preserves_history(self):
        self.apply()
        with self.engine.begin() as c:
            c.execute(text("UPDATE fiscal_clientes SET email_destinatarios='user@example.com' WHERE id='P1'"))
            c.execute(text("UPDATE tareas SET descripcion='User history' WHERE id='T1'"))
        plan=dict(profile=dict(self.profile,email_destinatarios='user@example.com'),tasks=[],conflicts=[])
        result=self.apply(plan=plan,client_insert=False)
        self.assertFalse(result['changed'])
        self.assertEqual(snapshot_onboarding(self.engine)['tasks'][0]['descripcion'],'User history')

    def test_fill_blank_audit(self):
        self.apply()
        plan=dict(profile=dict(self.profile,email_destinatarios='user@example.com'),tasks=[],conflicts=[])
        result=self.apply(plan=plan,client_insert=False)
        self.assertEqual(result['changes'][0]['operation'],'update')
        self.assertEqual(result['changes'][0]['before']['email_destinatarios'],None)

    def test_nonempty_profile_never_overwritten(self):
        self.apply()
        plan=dict(profile=dict(self.profile,razon_social='DIFFERENT'),tasks=[],conflicts=[])
        with self.assertRaises(OnboardingConflict):self.apply(plan=plan,client_insert=False)
        self.assertEqual(snapshot_onboarding(self.engine)['profiles'][0]['razon_social'],'PRUEBA')

    def test_stale_preview_rolls_back_all(self):
        stale=snapshot_onboarding(self.engine)['fingerprint']
        with self.engine.begin() as c:c.execute(text("INSERT INTO clientes(cliente) VALUES ('OTRO')"))
        with self.assertRaises(OnboardingConflict):self.apply(fingerprint=stale)
        snap=snapshot_onboarding(self.engine)
        self.assertEqual(len(snap['profiles']),0)
        self.assertEqual(len(snap['tasks']),0)

    def test_cuit_in_another_client_blocks(self):
        with self.engine.begin() as c:c.execute(text("INSERT INTO fiscal_clientes(id,cliente,cuit) VALUES ('OTHER','OTRO','27-40884711-2')"))
        with self.assertRaises(OnboardingConflict):self.apply()
        self.assertEqual(len(snapshot_onboarding(self.engine)['clients']),0)

    def test_name_variant_blocks(self):
        with self.engine.begin() as c:c.execute(text("INSERT INTO clientes(cliente) VALUES (' prueba ')"))
        with self.assertRaises(OnboardingConflict):self.apply()

    def test_duplicate_profiles_blocks(self):
        self.apply()
        with self.engine.begin() as c:c.execute(text("INSERT INTO fiscal_clientes(id,cliente) VALUES ('P2','PRUEBA')"))
        with self.assertRaises(OnboardingConflict):self.apply()

    def test_no_client_autocreation_without_explicit_details(self):
        with self.assertRaises(OnboardingConflict):self.apply(client_insert=False)

    def test_tasks_not_modified_if_id_collision(self):
        self.apply()
        plan=dict(self.plan,tasks=[dict(self.task,estado='Finalizada')])
        with self.assertRaises(OnboardingConflict):self.apply(plan=plan)
        self.assertEqual(snapshot_onboarding(self.engine)['tasks'][0]['estado'],'Pendiente')

    def test_conflict_invalid_cuit_wrong_client_and_unknown_fields(self):
        invalid=[dict(self.plan,conflicts=['Review']),dict(self.plan,profile=dict(self.profile,cuit='27408847113')),
                 dict(self.plan,tasks=[dict(self.task,cliente='OTRO')]),dict(self.plan,profile=dict(self.profile,password='secret'))]
        for plan in invalid:
            with self.subTest(plan=plan):
                with self.assertRaises(OnboardingConflict):self.apply(plan=plan)
        self.assertEqual(len(snapshot_onboarding(self.engine)['clients']),0)

    def test_snapshot_canonical_order(self):
        rows={'clients':[{'cliente':'A'},{'cliente':'B'}],'profiles':[],'tasks':[]}
        self.assertEqual(snapshot_fingerprint(rows),snapshot_fingerprint(dict(rows,clients=list(reversed(rows['clients'])))))

    def test_sqlite_public_writes_refused(self):
        with self.assertRaisesRegex(OnboardingConflict,'PostgreSQL'):apply_plan(self.engine,self.plan,'fingerprint',self.master)

    def test_database_failure_rolls_back_previous_inserts(self):
        # A database failure on task insertion must undo the client and profile too.
        with self.engine.begin() as c:c.execute(text('DROP TABLE tareas'));c.execute(text('CREATE TABLE tareas (id TEXT PRIMARY KEY, cliente TEXT)'))
        before=snapshot_onboarding(self.engine)['fingerprint']
        with self.assertRaises(Exception):self.apply(fingerprint=before)
        self.assertEqual(len(snapshot_onboarding(self.engine)['clients']),0)
        self.assertEqual(len(snapshot_onboarding(self.engine)['profiles']),0)

class VerifiedLinkTests(unittest.TestCase):
    def setUp(self):
        OnboardingStoreTests.setUp(self)
        from am_hub_onboarding_store import _link_locked
        self.link_locked = _link_locked
        with self.engine.begin() as c:
            c.execute(text('ALTER TABLE tareas ADD COLUMN id_externo TEXT'))
            c.execute(text("INSERT INTO clientes(cliente) VALUES ('PRUEBA')"))
            c.execute(text("INSERT INTO fiscal_clientes(id,cliente) VALUES ('P1','PRUEBA')"))
            c.execute(text("INSERT INTO tareas(id,cliente,tarea,descripcion,fecha_limite,estado) VALUES ('L1','Alias','IVA','Historia intacta','2026-11-18','En curso')"))
    def link(self, fingerprint=None, **kw):
        args=dict(source_client='Alias',target_client='PRUEBA',cuit='27408847112',expected_fingerprint=fingerprint or snapshot_onboarding(self.engine)['fingerprint'],evidence='PDF verificado por usuario',actor='Alan',task_ids=['L1'],razon_social='PRUEBA LEGAL')
        args.update(kw)
        with self.engine.begin() as c:return self.link_locked(c,**args)
    def test_link_preserves_all_other_task_fields_and_replay(self):
        before=snapshot_onboarding(self.engine)
        result=self.link(fingerprint=before['fingerprint'])
        after=snapshot_onboarding(self.engine)
        task=after['tasks'][0]
        self.assertEqual(task,dict(before['tasks'][0],cliente='PRUEBA'))
        self.assertEqual(after['profiles'][0]['cuit'],'27408847112')
        self.assertEqual(len(result['changes']),2)
        self.assertFalse(self.link(fingerprint=before['fingerprint'])['changed'])
    def test_source_master_blocks(self):
        with self.engine.begin() as c:c.execute(text("INSERT INTO clientes(cliente) VALUES ('Alias')"))
        with self.assertRaises(OnboardingConflict):self.link()
    def test_source_profile_blocks(self):
        with self.engine.begin() as c:c.execute(text("INSERT INTO fiscal_clientes(id,cliente) VALUES ('PA','Alias')"))
        with self.assertRaises(OnboardingConflict):self.link()
    def test_incomplete_scope_blocks(self):
        with self.engine.begin() as c:c.execute(text("INSERT INTO tareas(id,cliente) VALUES ('L2','Alias')"))
        with self.assertRaises(OnboardingConflict):self.link()
    def test_stale_link_blocks(self):
        old=snapshot_onboarding(self.engine)['fingerprint']
        with self.engine.begin() as c:c.execute(text("UPDATE tareas SET estado='Finalizada' WHERE id='L1'"))
        with self.assertRaises(OnboardingConflict):self.link(fingerprint=old)
        self.assertEqual(snapshot_onboarding(self.engine)['tasks'][0]['cliente'],'Alias')
    def test_target_duplicate_obligation_blocks(self):
        import json
        meta='fiscal:v1:'+json.dumps(dict(impuesto='IVA',obligacion='MENSUAL',jurisdiccion='NACIONAL',periodo='2026-10'))
        with self.engine.begin() as c:
            c.execute(text("UPDATE tareas SET id_externo=:m WHERE id='L1'"),{'m':meta})
            c.execute(text("INSERT INTO tareas(id,cliente,id_externo) VALUES ('TARGET','PRUEBA',:m)"),{'m':meta})
        with self.assertRaises(OnboardingConflict):self.link()
    def test_explicit_evidence_actor_and_ids_required(self):
        for kw in [dict(evidence=''),dict(actor=''),dict(task_ids=[]),dict(task_ids=['L1','L1']),dict(task_ids=['UNKNOWN'])]:
            with self.subTest(kw=kw):
                with self.assertRaises(OnboardingConflict):self.link(**kw)

class CalendarGuardTests(unittest.TestCase):
    def test_changed_calendar_prevents_transaction(self):
        from unittest.mock import patch
        engine=Mock();engine.dialect.name='postgresql'
        plan=dict(profile=dict(cliente='PRUEBA',cuit='27408847112'),tasks=[dict(fecha_limite='2026-11-13')])
        with patch('am_hub_tax_calendar.resolve',return_value=dict(fecha='2026-11-17',contexto=dict(estado='verificado'))):
            with self.assertRaisesRegex(OnboardingConflict,'calendario'):
                apply_plan(engine,plan,'snapshot')
        engine.begin.assert_not_called()
