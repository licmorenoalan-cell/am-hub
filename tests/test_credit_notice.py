import unittest
from email.parser import BytesParser
from email import policy
from am_hub_payment_notice import *
class CreditTests(unittest.TestCase):
 def setUp(self):
  self.credit=dict(impuesto='IVA',periodo='11/2026',monto='100,00',resultado='Saldo a favor',vencimiento='')
  self.pay=dict(impuesto='IIBB',periodo='11/2026',monto='2,00',vencimiento='30/11/2026')
  self.f=dict(cliente='PRUEBA',email='test@example.com',avisos=[self.credit,self.pay])
 def test_mixed(self):
  h=body_html(self.f);self.assertEqual(h.count('Agendar vencimiento'),1);self.assertIn('Saldo a favor: $ 100,00',h)
  self.assertNotIn('Saldo a pagar: $ 100,00',h)
  cs=calendar_attachments(self.f);self.assertEqual(len(cs),1);self.assertIn(b'IIBB',cs[0][1]);self.assertNotIn(b'IVA',cs[0][1])
 def test_credit_only_no_event(self):
  self.f['avisos']=[self.credit];self.assertEqual(calendar_attachments(self.f),[])
  self.assertNotIn('Agendar vencimiento',body_html(self.f))
  msg=BytesParser(policy=policy.default).parsebytes(email_draft(self.f,[('ddjj.pdf',b'%PDF-test')]))
  self.assertEqual(len(list(msg.iter_attachments())),1)
 def test_explicit_credit_only(self):
  self.assertEqual(parse_credit('Saldo a favor del contribuyente: 100,00')['monto'],'100,00')
  for text in ['Saldo a favor del fisco: 100,00','Total: 100,00','Saldo a favor del contribuyente: -100,00','Saldo a favor del contribuyente: 100,00\nSaldo a favor del contribuyente: 200,00']:
   self.assertEqual(parse_credit(text)['monto'],'')
 def test_invalid_kind_and_negative_rejected(self):
  self.credit['resultado']='algo'
  with self.assertRaises(ValueError):notice_items(self.f)
  self.credit['resultado']='Saldo a favor';self.credit['monto']='-100,00'
  with self.assertRaises(ValueError):notice_items(self.f)
 def test_credit_direct_calendar_refused(self):
  with self.assertRaises(ValueError):calendar_outputs(dict(self.credit,cliente='PRUEBA',email='test@example.com'))
