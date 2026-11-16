import unittest
from am_hub_payment_notice import validate,body,body_html,calendar_attachments,email_draft
from email.parser import BytesParser
from email import policy
class ZeroNoticeTests(unittest.TestCase):
 def setUp(self):
  self.f=dict(cliente='PRUEBA',email='test@example.com',impuesto='IVA',periodo='10/2026',resultado='Sin saldo',monto='0',vencimiento='')
 def test_zero_omits_balance_and_calendar(self):
  validate(self.f)
  for content in [body(self.f),body_html(self.f)]:
   self.assertIn('Sin importe a pagar',content);self.assertNotIn('Saldo',content);self.assertNotIn('Vencimiento',content);self.assertNotIn('calendar.google',content)
  self.assertEqual(calendar_attachments(self.f),[])
  msg=BytesParser(policy=policy.default).parsebytes(email_draft(self.f,[('DDJJ.pdf',b'%PDF-test')]))
  self.assertEqual(len(list(msg.iter_attachments())),1)
 def test_zero_both_and_mixed(self):
  other=dict(self.f,impuesto='Ingresos Brutos')
  both=dict(cliente=self.f['cliente'],email=self.f['email'],avisos=[self.f,other])
  self.assertIn('IVA e INGRESOS BRUTOS',body(both));self.assertNotIn('Saldo',body(both))
  other.update(resultado='A pagar',monto='100',vencimiento='30/11/2026')
  self.assertEqual(len(calendar_attachments(both)),1);self.assertEqual(body_html(both).count('Saldo a pagar'),1)
 def test_contradictions_blocked(self):
  for patch in [dict(monto='1'),dict(monto='-1'),dict(monto=''),dict(resultado='A pagar'),dict(resultado='Saldo a favor')]:
   with self.assertRaises(ValueError):validate(dict(self.f,**patch))
