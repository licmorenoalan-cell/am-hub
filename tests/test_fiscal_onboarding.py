import copy
import unittest
from datetime import date
from am_hub_fiscal_onboarding import (plan_onboarding, reconciliation_inventory,
                                      snapshot_fingerprint, validate_cuit)
from am_hub_tax_calendar import metadata, encode_metadata

CUIT='27408847112'
CLIENT={'cliente':'PRUEBA','servicio_contabilidad':'Sí'}

def entry(tax='IVA',obligation='MENSUAL',jurisdiction='NACIONAL',day='2026-11-18'):
    return dict(impuesto=tax,obligacion=obligation,jurisdiccion=jurisdiction,periodo='2026-10',
                terminaciones=[2],vencimiento=day,fuente='https://example.org/official',
                norma='N-1',verificado=True,verificado_el='2026-11-16')

class OnboardingPlanTests(unittest.TestCase):
 def plan(self,**kwargs):
    args=dict(cliente='PRUEBA',cuit=CUIT,taxes=['IVA'],period='2026-10',clients=[CLIENT],
              calendar=[entry()],actor='tester',today=date(2026,11,16));args.update(kwargs)
    return plan_onboarding(**args)
 def test_valid_cuit(self):
    self.assertEqual(validate_cuit('27-40884711-2'),CUIT)
    for bad in ('27408847113','00000000000','2740884711','CUIT 27408847112',''):
        with self.assertRaises(ValueError):validate_cuit(bad)
 def test_new_profile_and_card(self):
    p=self.plan();self.assertFalse(p['conflicts']);self.assertEqual(len(p['tasks']),1)
    t=p['tasks'][0];self.assertEqual(t['fecha_limite'],'2026-11-18');self.assertEqual(t['recurrente'],'Sí')
    self.assertEqual(metadata(t)['estado'],'verificado');self.assertNotIn(CUIT,t['id_externo'])
    self.assertEqual(p['profile_insert']['cuit'],CUIT);self.assertIsNone(p['client_insert'])
 def test_calendar_prorogation_not_arithmetic(self):
    p=self.plan(calendar=[entry(day='2026-11-20')]);self.assertEqual(p['tasks'][0]['fecha_limite'],'2026-11-20')
 def test_missing_calendar_is_pending(self):
    t=self.plan(calendar=[])['tasks'][0]
    self.assertEqual(t['fecha_limite'],'');self.assertEqual(metadata(t)['estado'],'pendiente')
    self.assertIn('Calendario',t['comentarios'])
 def test_second_run_has_no_inserts(self):
    p=self.plan();q=self.plan(profiles=[p['profile']],tasks=p['tasks'])
    self.assertFalse(q['tasks']);self.assertIsNone(q['profile_insert']);self.assertIsNone(q['profile_updates'])
    self.assertEqual(len(q['existing']),1)
 def test_recurring_other_period_reused(self):
    t=self.plan()['tasks'][0];m=metadata(t);m['periodo']='2026-09';t['id_externo']=encode_metadata(m)
    q=self.plan(tasks=[t]);self.assertFalse(q['tasks']);self.assertEqual(len(q['existing']),1)
 def test_completed_same_period_not_duplicated(self):
    t=self.plan()['tasks'][0];t['estado']='Finalizada';self.assertFalse(self.plan(tasks=[t])['tasks'])
 def test_duplicate_cards_block(self):
    t=self.plan()['tasks'][0];p=self.plan(tasks=[t,dict(t,id='another')]);self.assertTrue(p['conflicts']);self.assertFalse(p['tasks'])
 def test_legacy_card_blocks_no_guess(self):
    p=self.plan(tasks=[dict(cliente='PRUEBA',id='old',tarea='IVA',categoria='IVA')])
    self.assertTrue(p['conflicts']);self.assertFalse(p['tasks']);self.assertIsNone(p['profile'])
 def test_other_client_not_reused(self):
    t=self.plan()['tasks'][0];t['cliente']='OTRO';self.assertEqual(len(self.plan(tasks=[t])['tasks']),1)
 def test_duplicate_cuit_alias_blocks(self):
    p=self.plan(profiles=[dict(id='x',cliente='OTRO',cuit=CUIT)])
    self.assertTrue(p['conflicts']);self.assertFalse(p['tasks'])
 def test_name_variant_no_merge(self):
    self.assertTrue(self.plan(clients=[dict(cliente='prueba')])['conflicts'])
 def test_multiple_profiles_block(self):
    self.assertTrue(self.plan(profiles=[dict(cliente='PRUEBA'),dict(cliente='PRUEBA')])['conflicts'])
 def test_wrong_cuit_existing_not_overwritten(self):
    p=self.plan(profiles=[dict(id='f',cliente='PRUEBA',cuit='30123456781')]);self.assertTrue(p['conflicts'])
 def test_preserve_nonblank_profile_data_and_patch_blanks(self):
    before=dict(id='f',cliente='PRUEBA',cuit='',email_destinatarios='private@example.com',mes_cierre_ejercicio='06')
    p=self.plan(profiles=[before]);self.assertEqual(p['profile']['mes_cierre_ejercicio'],'06')
    self.assertNotIn('email_destinatarios',p['profile_updates']['changes']);self.assertEqual(before['cuit'],'')
 def test_explicit_client_insert_only(self):
    self.assertTrue(self.plan(clients=[])['conflicts'])
    p=self.plan(clients=[],client_record=dict(CLIENT,role='admin',username='not allowed'))
    self.assertFalse(p['conflicts']);self.assertNotIn('role',p['client_insert']);self.assertNotIn('username',p['client_insert'])
 def test_impossible_selections(self):
    for taxes in ([],['Unsupported'],['IVA','Monotributo'],['Convenio Multilateral (CM03)','Ingresos Brutos local CABA (régimen general)']):
        self.assertTrue(self.plan(taxes=taxes)['conflicts'])
 def test_cm03_separate_from_local(self):
    p=self.plan(taxes=['Convenio Multilateral (CM03)'],calendar=[entry('IIBB','CM03','COMARB')])
    self.assertEqual(metadata(p['tasks'][0])['obligacion'],'CM03')
    self.assertEqual(p['profile']['iibb_regimen'],'Convenio Multilateral')
 def test_period_required_no_guess(self):
    for period in ('','2026-13','10/2026'):
        self.assertTrue(self.plan(period=period)['conflicts'])
 def test_task_generation_does_not_mutate_inputs(self):
    rows=[CLIENT];original=copy.deepcopy(rows);self.plan(clients=rows);self.assertEqual(rows,original)
 def test_fingerprint_order_independent_content_sensitive(self):
    a=[dict(cliente='A'),dict(cliente='B')]
    self.assertEqual(snapshot_fingerprint(a),snapshot_fingerprint(list(reversed(a))))
    self.assertNotEqual(snapshot_fingerprint(a),snapshot_fingerprint([dict(cliente='C')]))
 def test_inventory_missing_and_conflicts(self):
    rows=reconciliation_inventory([CLIENT],[dict(cliente='PRUEBA',cuit='')],[dict(cliente='HUERFANO'),dict(cliente='PRUEBA')])
    self.assertEqual({r['cliente']:r['estado'] for r in rows},{'HUERFANO':'cliente_solo_en_tareas','PRUEBA':'ficha_incompleta'})
    rows=reconciliation_inventory([CLIENT,dict(cliente='prueba')]);self.assertTrue(all(r['estado']=='conflicto' for r in rows))

 def test_matching_formatted_cuit_is_not_rewritten(self):
    p=self.plan(profiles=[dict(id='f',cliente='PRUEBA',cuit='27-40884711-2')])
    self.assertEqual(p['profile']['cuit'],'27-40884711-2')
    self.assertNotIn('cuit',p['profile_updates']['changes'])
 def test_contradictory_profile_blocks_tasks(self):
    p=self.plan(profiles=[dict(id='f',cliente='PRUEBA',cuit=CUIT,condicion_iva='Monotributo')])
    self.assertTrue(p['conflicts']);self.assertFalse(p['tasks']);self.assertIsNone(p['profile'])

 def test_incomplete_fiscal_metadata_blocks_duplicate(self):
    for meta in ({'impuesto':'IVA'},
                 {'impuesto':'IVA','obligacion':'MENSUAL','jurisdiccion':'NACIONAL'},
                 {'impuesto':'IVA','obligacion':'MENSUAL','jurisdiccion':'NACIONAL','periodo':'2026-13'},
                 {'periodo':'2026-10'}):
        with self.subTest(meta=meta):
            t=dict(id='old',cliente='PRUEBA',tarea='IVA',id_externo=encode_metadata(meta))
            p=self.plan(tasks=[t])
            self.assertTrue(p['conflicts']);self.assertFalse(p['tasks'])
 def test_local_regime_uses_existing_ui_enum(self):
    for before in ([],[dict(id='f',cliente='PRUEBA',cuit=CUIT,iibb_regimen='Local',iibb_jurisdiccion='CABA')]):
        p=self.plan(profiles=before,taxes=['Ingresos Brutos local CABA (régimen general)'],calendar=[entry('IIBB','MENSUAL','CABA')])
        self.assertFalse(p['conflicts']);self.assertEqual(p['profile']['iibb_regimen'],'Local')
        self.assertEqual(metadata(p['tasks'][0])['obligacion'],'MENSUAL')
        self.assertEqual(metadata(p['tasks'][0])['jurisdiccion'],'CABA')
