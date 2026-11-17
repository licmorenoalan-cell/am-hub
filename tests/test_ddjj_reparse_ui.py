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
 def test_legacy_ddjj_upload_prefills_without_vep(self):
  import sys
  from unittest.mock import MagicMock
  from am_hub_payment_notice import render_payment_notice
  uploaded=MagicMock();uploaded.name='CM03.pdf';uploaded.getvalue.return_value=b'%PDF-synthetic'
  ui=MagicMock();ui.session_state={};ui.file_uploader.return_value=[uploaded]
  ui.button.return_value=False;ui.checkbox.return_value=False
  ui.selectbox.side_effect=lambda label,options,**kw:options[kw.get('index',0)]
  seen={}
  def inp(label,value='',**kw):seen[label]=value;return value
  ui.text_input.side_effect=inp
  data=dict(impuesto='Ingresos Brutos',periodo='10/2026',resultado='Saldo a favor',monto='7.738,23',vencimiento='',cuit='30123456781',advertencias=[])
  with patch.dict(sys.modules,{'streamlit':ui}),patch('am_hub_payment_notice.pdf_text',return_value='CONVENIO MULTILATERAL DJ MENSUAL - CM03'),patch('am_hub_notice_extract.parse_ddjj',return_value=data):
   render_payment_notice('PRUEBA',{'cuit':'30123456781'})
  self.assertEqual(seen['Impuesto'],'Ingresos Brutos');self.assertEqual(seen['Período fiscal'],'10/2026');self.assertEqual(seen['Saldo a favor del contribuyente en pesos'],'7.738,23')
  ui.error.assert_not_called()

 def test_iva_simple_screen_export(self):
  from am_hub_notice_extract import parse_ddjj
  text='IVA SIMPLE\nDeterminación del impuesto | 10/2026\nSaldo técnico a favor del contribuyente del período anterior $ 6.804.191,58\nSaldo técnico a favor del contribuyente $ 7.554.648,62\nSaldo técnico a favor del contribuyente $ 7.554.648,62\nSaldo de libre disponibilidad a favor del contribuyente del período $ 64.779,11'
  d=parse_ddjj(text)
  self.assertEqual(d['impuesto'],'IVA');self.assertEqual(d['periodo'],'10/2026');self.assertEqual(d['monto'],'64.779,11');self.assertEqual(d['resultado'],'Saldo a favor')
  self.assertEqual(d['cuit'],'');self.assertEqual(d['vencimiento'],'')

 def test_type_detection_avoids_filename_guessing(self):
  from am_hub_payment_notice import detect_document_type
  for value in ['IVA SIMPLE','CONTRIBUYENTES LOCALES SICOL','CONVENIO MULTILATERAL DJ MENSUAL - CM03']:
   self.assertEqual(detect_document_type(value),'DDJJ')
  self.assertEqual(detect_document_type('VOLANTE ELECTRONICO DE PAGO'),'VEP')
  self.assertEqual(detect_document_type('unknown invoice'),'')
  self.assertEqual(detect_document_type('IVA SIMPLE VOLANTE ELECTRONICO DE PAGO'),'')
 def test_unified_pair_one_reviewed_notice_all_pdfs(self):
  import sys
  from unittest.mock import MagicMock
  from am_hub_payment_notice import render_payment_notice
  docs=[]
  for name,raw in [('ddjj.pdf',b'%PDF-ddjj'),('vep.pdf',b'%PDF-vep')]:
   d=MagicMock();d.name=name;d.getvalue.return_value=raw;docs.append(d)
  ui=MagicMock();ui.session_state={};ui.secrets={};ui.file_uploader.return_value=docs
  ui.button.return_value=False;ui.checkbox.return_value=True
  ui.selectbox.side_effect=lambda label,options,**kw:options[kw.get('index',1)]
  ui.text_input.side_effect=lambda label,value='',**kw:value
  base=dict(impuesto='Ingresos Brutos',periodo='10/2026',monto='10,00',vencimiento='30/11/2026',cuit='30123456781',advertencias=[])
  def text(raw):return 'CONTRIBUYENTES LOCALES' if raw==b'%PDF-ddjj' else 'VOLANTE ELECTRONICO DE PAGO'
  with patch.dict(sys.modules,{'streamlit':ui}),patch('am_hub_payment_notice.pdf_text',side_effect=text),patch('am_hub_notice_extract.parse_ddjj',return_value=dict(base,resultado='Saldo a favor')),patch('am_hub_payment_notice.parse_vep',return_value=base):
   render_payment_notice('PRUEBA',{'cuit':'30123456781','email_destinatarios':'test@example.com'})
  ui.error.assert_not_called()
  body=ui.text_area.call_args.kwargs['value']
  self.assertEqual(body.count('Saldo a favor:'),1);self.assertNotIn('Saldo a pagar:',body)
  downloads=[x.kwargs.get('file_name') for x in ui.download_button.call_args_list]
  self.assertIn('102026 DDJJ IIBB.pdf',downloads);self.assertIn('VEP 102026 DDJJ IIBB.pdf',downloads)
  self.assertFalse(any(x and x.endswith('.ics') for x in downloads))
