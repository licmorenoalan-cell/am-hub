import unittest
from email import policy
from email.parser import BytesParser
from am_hub_payment_notice import notice_subject,email_draft
class SubjectTests(unittest.TestCase):
 def setUp(self):
  a=dict(impuesto='IVA',periodo='2026-10',monto='1,00',vencimiento='20/11/2026')
  b=dict(a,impuesto='IIBB',periodo='10/2026')
  self.f=dict(cliente='CLIENTE EJEMPLO',email='test@example.com',avisos=[a,b])
 def test_same_period(self):
  self.assertEqual(notice_subject(self.f),'DDJJ IVA e INGRESOS BRUTOS 10/2026 - CLIENTE EJEMPLO')
 def test_one_and_credit(self):
  self.f['avisos']=[dict(self.f['avisos'][1],resultado='Saldo a favor',vencimiento='')]
  self.assertEqual(notice_subject(self.f),'DDJJ INGRESOS BRUTOS 10/2026 - CLIENTE EJEMPLO')
 def test_mixed_periods_explicit(self):
  self.f['avisos'][1]['periodo']='11/2026'
  self.assertEqual(notice_subject(self.f),'DDJJ IVA 10/2026; INGRESOS BRUTOS 11/2026 - CLIENTE EJEMPLO')
 def test_eml_shared_subject(self):
  msg=BytesParser(policy=policy.default).parsebytes(email_draft(self.f,[('x.pdf',b'%PDF-test')]))
  self.assertEqual(str(msg['Subject']),notice_subject(self.f))
 def test_dedup_labels(self):
  self.f['avisos'].append(self.f['avisos'][0].copy())
  self.assertEqual(notice_subject(self.f).count('IVA'),1)
