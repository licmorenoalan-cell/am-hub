import unittest
from email import policy
from email.parser import BytesParser
from am_hub_payment_notice import body,calendar_attachments,email_draft,notice_items,unique_pdfs
class MultiTests(unittest.TestCase):
    def setUp(self):
        self.f=dict(cliente='PRUEBA',email='test@example.com',avisos=[dict(impuesto='IVA',periodo='11/2026',monto='100,00',vencimiento='20/11/2026'),dict(impuesto='IIBB',periodo='11/2026',monto='200,00',vencimiento='30/11/2026')])
    def test_links_dates_alarm(self):
        text=body(self.f);self.assertEqual(text.count('https://calendar.google.com/'),2)
        calendars=calendar_attachments(self.f);self.assertEqual(len(calendars),2)
        self.assertIn(b'20261120',calendars[0][1]);self.assertIn(b'20261130',calendars[1][1]);self.assertNotEqual(calendars[0][0],calendars[1][0])
        self.assertTrue(all(b'TRIGGER:-P1D' in c for _,c in calendars))
    def test_email_dedup(self):
        msg=BytesParser(policy=policy.default).parsebytes(email_draft(self.f,[('v1.pdf',b'%PDF-1'),('v2.pdf',b'%PDF-2'),('ddjj.pdf',b'%PDF-3'),('duplicate.pdf',b'%PDF-3')]))
        parts=list(msg.iter_attachments());self.assertEqual(len(parts),5)
        self.assertEqual(sum(p.get_content_type()=='text/calendar' for p in parts),2)
    def test_invalid_one_blocks_all(self):
        self.f['avisos'][1]['vencimiento']='31/02/2026'
        with self.assertRaises(ValueError): notice_items(self.f)
    def test_filename_collision(self):
        files=unique_pdfs([('same.pdf',b'%PDF-1'),('same.pdf',b'%PDF-2')]);self.assertNotEqual(files[0][0],files[1][0])
