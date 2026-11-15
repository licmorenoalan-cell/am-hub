import unittest
from email.parser import BytesParser
from email import policy
from urllib.parse import parse_qs,urlparse
from am_hub_payment_notice import *
class PaymentNoticeTests(unittest.TestCase):
 def setUp(self):
  self.f=dict(cliente='Prueba SRL',impuesto='IVA',periodo='2026-10',monto='123.456,78',vencimiento='20/11/2026',email='test@example.com')
 def test_explicit_fields(self):
  p=parse_vep('Impuesto: 030 - IVA\nPeriodo fiscal: 2026-10\nImporte total: $123.456,78\nFecha de expiración: 20/11/2026\nCUIT: 30-12345678-9')
  self.assertEqual(p['monto'],'123.456,78');self.assertEqual(p['vencimiento'],'20/11/2026');self.assertFalse(p['advertencias'])
 def test_conflicting_dates_and_totals_not_guessed(self):
  p=parse_vep('Vencimiento: 20/11/2026\nFecha de expiración: 21/11/2026\nImporte total: 10,00\nImporte total: 20,00')
  self.assertEqual(p['vencimiento'],'');self.assertEqual(p['monto'],'')
 def test_no_pdf_text_no_guess(self): self.assertTrue(parse_vep('')['advertencias'])
 def test_argentine_amount(self):
  self.assertEqual(amount('123.456,78'),Decimal('123456.78'))
  for x in ['123.45','0','-3','nan','1e9']: 
   with self.assertRaises(ValueError): amount(x)
 def test_invalid_fields(self):
  for k,v in [('periodo','2026-19'),('vencimiento','31/02/2026'),('email','bad'),('impuesto','IVA\nBcc:evil@example.com')]:
   with self.assertRaises(ValueError): validate(dict(self.f,**{k:v}))
 def test_ics_and_url_same_all_day(self):
  url,ics=calendar_outputs(self.f);p=parse_qs(urlparse(url).query)
  self.assertEqual(p['dates'],['20261120/20261121'])
  self.assertIn(b'DTSTART;VALUE=DATE:20261120',ics)
  self.assertIn(b'DTEND;VALUE=DATE:20261121',ics)
  self.assertLessEqual(max(map(len,ics.split(b'\r\n'))),75)
 def test_draft_contains_pdf_not_sent(self):
  raw=email_draft(self.f,[('vep.pdf',b'%PDF-test')]);msg=BytesParser(policy=policy.default).parsebytes(raw)
  self.assertEqual(msg['X-Unsent'],'1');self.assertEqual(msg['To'],'test@example.com')
  parts=list(msg.iter_attachments());self.assertEqual(parts[0].get_payload(decode=True),b'%PDF-test')
 def test_invalid_pdf_and_oversized(self):
  for data in [b'not PDF',b'%PDF-'+b'x'*MAX_BYTES]:
   with self.assertRaises(ValueError): pdf_text(data)
 def test_client_label_ics_escaped(self):
  _,ics=calendar_outputs(dict(self.f,cliente='Prueba, SRL;'))
  self.assertIn(b'Prueba\\, SRL\\;',ics)
 def test_real_synthetic_pdf_and_empty_ui(self):
  from pypdf import PdfWriter
  writer=PdfWriter();writer.add_blank_page(width=200,height=200);buf=io.BytesIO();writer.write(buf)
  self.assertEqual(pdf_text(buf.getvalue()).strip(),'')
  from streamlit.testing.v1 import AppTest
  app=AppTest.from_string("from am_hub_payment_notice import render_payment_notice\nrender_payment_notice('Cliente de prueba',{})").run()
  self.assertFalse(app.exception)
