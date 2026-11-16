import unittest
from am_hub_payment_notice import extraction_state_key
from unittest.mock import patch
class RereadTests(unittest.TestCase):
 def test_new_revision_invalidates_parsed_and_widget_keys(self):
  a=extraction_state_key('same-upload',0)
  with patch('am_hub_payment_notice.PARSER_REVISION','next-parser'):
   self.assertNotEqual(a,extraction_state_key('same-upload',0))
 def test_user_reread_and_doc_are_separate(self):
  a=extraction_state_key('same-upload',0)
  self.assertNotEqual(a,extraction_state_key('same-upload',0,1))
  self.assertNotEqual(a,extraction_state_key('same-upload',1))
 def test_legacy_ddjj_only_does_not_return_silently(self):
  from pathlib import Path
  source=Path('am_hub_payment_notice.py').read_text()
  start=source.index('auto_ddjj=bool')
  end=source.index('vep_files=',start)
  self.assertIn('credits=ddjj',source[start:end]);self.assertIn('if not veps and not credits: return',source[start:end])
 def test_legacy_ddjj_upload_prefills_without_vep(self):
  import sys
  from unittest.mock import MagicMock
  from am_hub_payment_notice import render_payment_notice
  uploaded=MagicMock();uploaded.name='CM03.pdf';uploaded.getvalue.return_value=b'%PDF-synthetic'
  ui=MagicMock();ui.session_state={};ui.file_uploader.side_effect=[[],[uploaded],[]]
  ui.button.return_value=False;ui.checkbox.return_value=False
  ui.selectbox.side_effect=lambda label,options,**kw:options[kw.get('index',0)]
  seen={}
  def inp(label,value='',**kw):seen[label]=value;return value
  ui.text_input.side_effect=inp
  data=dict(impuesto='Ingresos Brutos',periodo='10/2026',resultado='Saldo a favor',monto='7.738,23',vencimiento='',cuit='30123456781',advertencias=[])
  with patch.dict(sys.modules,{'streamlit':ui}),patch('am_hub_payment_notice.pdf_text',return_value='CM03'),patch('am_hub_notice_extract.parse_ddjj',return_value=data):
   render_payment_notice('PRUEBA',{'cuit':'30123456781'})
  self.assertEqual(seen['Impuesto'],'Ingresos Brutos');self.assertEqual(seen['Período fiscal'],'10/2026');self.assertEqual(seen['Saldo a favor del contribuyente en pesos'],'7.738,23')
  ui.error.assert_not_called()

 def test_iva_simple_screen_export(self):
  from am_hub_notice_extract import parse_ddjj
  text='IVA SIMPLE\nDeterminación del impuesto | 10/2026\nSaldo técnico a favor del contribuyente del período anterior $ 6.804.191,58\nSaldo técnico a favor del contribuyente $ 7.554.648,62\nSaldo técnico a favor del contribuyente $ 7.554.648,62\nSaldo de libre disponibilidad a favor del contribuyente del período $ 64.779,11'
  d=parse_ddjj(text)
  self.assertEqual(d['impuesto'],'IVA');self.assertEqual(d['periodo'],'10/2026');self.assertEqual(d['monto'],'7.554.648,62');self.assertEqual(d['resultado'],'Saldo a favor')
  self.assertEqual(d['cuit'],'');self.assertEqual(d['vencimiento'],'')
