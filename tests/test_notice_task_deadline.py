import copy,json,unittest
from am_hub_notice_extract import card_deadline,parse_ddjj

class NoticeDeadlineTests(unittest.TestCase):
 def setUp(self):
  self.meta=dict(impuesto='IIBB',obligacion='CM03',jurisdiccion='COMARB',periodo='2026-10',estado='verificado',terminacion=2,fuente='https://example.com/official')
  self.task=dict(id='task-1',cliente='PRUEBA',fecha_limite='2026-11-17',estado='Pendiente',id_externo='fiscal:v1:'+json.dumps(self.meta))
  self.entry=dict(self.meta,vencimiento='2026-11-17',terminaciones=[0,1,2],verificado=True,norma='test',verificado_el='2026-11-16')
 def run_case(self,tasks=None,**kw):
  args=dict(cliente='PRUEBA',profile_cuit='27408847112',document_cuit='27-40884711-2',period='10/2026',tasks=[self.task] if tasks is None else tasks,impuesto='Ingresos Brutos',calendar=[self.entry]);args.update(kw)
  return card_deadline(**args)
 def test_exact_cm03_and_trace(self):
  day,source=self.run_case();self.assertEqual(day,'17/11/2026');self.assertIn('task-1',source);self.assertIn('https://example.com/official',source)
 def test_exact_iva(self):
  self.meta.update(impuesto='IVA',obligacion='MENSUAL',jurisdiccion='NACIONAL')
  self.task['id_externo']='fiscal:v1:'+json.dumps(self.meta)
  self.entry.update(self.meta)
  self.assertEqual(self.run_case(impuesto='IVA')[0],'17/11/2026')
 def test_wrong_identity_or_period(self):
  for kwargs in [dict(cliente='OTRO'),dict(document_cuit='27408847113'),dict(profile_cuit=''),dict(period='11/2026'),dict(impuesto='IVA')]:
   self.assertEqual(self.run_case(**kwargs)[0],'')
 def test_duplicate_same_date_is_ambiguous(self):
  self.assertEqual(self.run_case([self.task,dict(self.task,id='task-2')])[0],'')
 def test_wrong_metadata_never_used(self):
  for change in [dict(obligacion='CM05'),dict(jurisdiccion='CABA'),dict(estado='estimado'),dict(estado='control'),dict(estado='pendiente'),dict(modo_fecha='preventiva_sin_cuit'),dict(motivo='pendiente'),dict(terminacion=3),dict(fuente=''),dict(cuit='27408847113')]:
   t=dict(self.task,id_externo='fiscal:v1:'+json.dumps(dict(self.meta,**change)))
   self.assertEqual(self.run_case([t])[0],'',change)
 def test_obsolete_date_rejected(self):
  self.assertEqual(self.run_case([dict(self.task,fecha_limite='2026-11-13')])[0],'')
 def test_absent_calendar_is_proposal_only(self):
  day,source=self.run_case(calendar=[]);self.assertEqual(day,'17/11/2026');self.assertIn('propuesta',source);self.assertIn('sin verificación independiente',source)
 def test_conflicting_calendar_blocks(self):
  self.assertEqual(self.run_case(calendar=[self.entry,dict(self.entry,vencimiento='2026-11-18')])[0],'')
 def test_cancelled_bad_date_empty_id(self):
  for change in [dict(estado='Cancelada'),dict(fecha_limite='2026-99-99'),dict(id='')]:
   self.assertEqual(self.run_case([dict(self.task,**change)],calendar=[])[0],'')
 def test_only_exact_current_free_balance(self):
  pre='IVA SIMPLE\nSaldo técnico a favor del contribuyente $ 418.915,49\nSaldo de libre disponibilidad del período anterior neto de usos $ 2.994.007,80\n'
  self.assertEqual(parse_ddjj(pre)['monto'],'')
  current='Saldo de libre disponibilidad a favor del contribuyente del período $ 3.109.738,91'
  self.assertEqual(parse_ddjj(pre+current)['monto'],'3.109.738,91')
  self.assertEqual(parse_ddjj(pre+current+'\n'+current.replace('3.109.738,91','2,00'))['monto'],'')
