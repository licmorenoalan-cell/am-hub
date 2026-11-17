import unittest
from unittest.mock import MagicMock,patch
from am_hub_fiscal_onboarding_ui import render_fiscal_onboarding

class OnboardingUITests(unittest.TestCase):
 def setup_ui(self,verified=True):
  st=MagicMock();st.session_state={}
  st.radio.return_value='Completar cliente existente';st.selectbox.return_value='PRUEBA'
  st.multiselect.return_value=['IVA'];st.checkbox.return_value=verified
  def inp(label,value='',**kw):
   return {'CUIT':'27-40884711-2','Referencia de la constancia / evidencia revisada':'Constancia confirmada','Primer período fiscal a organizar (AAAA-MM)':'2026-10'}.get(label,value)
  st.text_input.side_effect=inp
  st.button.side_effect=lambda label,**kw: label=='Revisar ficha y tarjetas antes de guardar'
  return st
 def test_preview_never_applies_and_retains_plan(self):
  st=self.setup_ui()
  snap=dict(clients=[{'cliente':'PRUEBA'}],profiles=[],tasks=[],fingerprint='fp')
  plan=dict(profile={'cliente':'PRUEBA'},tasks=[],existing=[],conflicts=[],warnings=[])
  with patch('am_hub_onboarding_store.snapshot_onboarding',return_value=snap),patch('am_hub_fiscal_onboarding.plan_onboarding',return_value=plan) as planner,patch('am_hub_onboarding_store.apply_plan') as apply:
   render_fiscal_onboarding(st,object(),actor='TEST')
  apply.assert_not_called();planner.assert_called_once();self.assertTrue(st.session_state)
 def test_missing_confirmation_blocks_planner(self):
  st=self.setup_ui(False)
  with patch('am_hub_onboarding_store.snapshot_onboarding',return_value=dict(clients=[{'cliente':'PRUEBA'}],profiles=[],tasks=[],fingerprint='fp')),patch('am_hub_fiscal_onboarding.plan_onboarding') as plan,patch('am_hub_onboarding_store.apply_plan') as apply:
   render_fiscal_onboarding(st,object())
  plan.assert_not_called();apply.assert_not_called();st.error.assert_called_once()
 def test_snapshot_failure_no_write(self):
  st=self.setup_ui()
  with patch('am_hub_onboarding_store.snapshot_onboarding',side_effect=RuntimeError('offline')),patch('am_hub_onboarding_store.apply_plan') as apply:
   render_fiscal_onboarding(st,object())
  apply.assert_not_called();st.error.assert_called_once()
 def test_route_blocks_legacy_accounting_bypass(self):
  from pathlib import Path
  source=Path('app.py').read_text()
  section=source[source.index('def render_onboarding_cliente():'):source.index('def render_onboarding_cliente():')+8500]
  self.assertIn('if onboarding_flow == "Contabilidad / gestión":',section)
  self.assertIn('servicio_contabilidad = False',section)
  self.assertNotIn('servicio_contabilidad = st.checkbox',section)

 def test_new_preview_apply_preserves_audit_and_no_accounts(self):
  st=self.setup_ui();st.radio.return_value='Crear cliente contable'
  st.selectbox.return_value='Ingresar un nombre nuevo'
  old=st.text_input.side_effect
  st.text_input.side_effect=lambda label,value='',**kw:'NUEVO' if label=='Nombre del nuevo cliente / razón social' else old(label,value,**kw)
  snap=dict(clients=[],profiles=[],tasks=[],fingerprint='fp')
  plan=dict(profile={'cliente':'NUEVO'},tasks=[],existing=[],conflicts=[],warnings=[])
  callback=MagicMock()
  with patch('am_hub_onboarding_store.snapshot_onboarding',return_value=snap),patch('am_hub_fiscal_onboarding.plan_onboarding',return_value=plan),patch('am_hub_onboarding_store.apply_plan',return_value={'changed':True,'changes':[]}) as apply:
   render_fiscal_onboarding(st,object(),actor='TEST',on_saved=callback)
   apply.assert_not_called()
   st.button.side_effect=lambda label,**kw:label=='Guardar ficha y tarjetas propuestas'
   render_fiscal_onboarding(st,object(),actor='TEST',on_saved=callback)
  apply.assert_called_once();callback.assert_called_once()
  self.assertEqual(apply.call_args.kwargs['client_insert']['servicio_contabilidad'],'Sí')
  self.assertEqual(callback.call_args.args[0]['evidence'],'Constancia confirmada')
  self.assertEqual(callback.call_args.args[0]['requested_taxes'],['IVA'])
  self.assertFalse(st.session_state)
 def test_changed_fields_disable_old_preview(self):
  st=self.setup_ui();snap=dict(clients=[{'cliente':'PRUEBA'}],profiles=[],tasks=[],fingerprint='fp')
  plan=dict(profile={'cliente':'PRUEBA'},tasks=[],existing=[],conflicts=[],warnings=[])
  with patch('am_hub_onboarding_store.snapshot_onboarding',return_value=snap),patch('am_hub_fiscal_onboarding.plan_onboarding',return_value=plan),patch('am_hub_onboarding_store.apply_plan') as apply:
   render_fiscal_onboarding(st,object())
   st.multiselect.return_value=['Monotributo']
   st.button.side_effect=lambda label,**kw:label=='Guardar ficha y tarjetas propuestas'
   render_fiscal_onboarding(st,object())
  apply.assert_not_called()
