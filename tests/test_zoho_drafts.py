import unittest
from am_hub_zoho_drafts import ZohoConfig,ZohoDraftClient,ZohoDraftError

class Response:
    def __init__(self,body,status=200): self.body=body;self.status_code=status
    def json(self): return self.body
class Session:
    def __init__(self,replies): self.replies=list(replies);self.calls=[]
    def request(self,*args,**kwargs):
        self.calls.append((args,kwargs));reply=self.replies.pop(0)
        if isinstance(reply,Exception): raise reply
        return reply
class DraftTests(unittest.TestCase):
    def setUp(self):
        self.config=ZohoConfig('id','secret','refresh','123','test@example.com')
        self.fields=dict(cliente='PRUEBA',impuesto='IVA',periodo='11/2026',monto='10,00',vencimiento='30/11/2026',email='test@example.com')
        self.files=[('vep.pdf',b'%PDF-test')]
    def replies(self): return [Response({'access_token':'token'}),Response({'data':[dict(attachmentName='vep.pdf',attachmentPath='path',storeName='store')]}),Response({'data':[dict(attachmentName='vencimiento.ics',attachmentPath='ics',storeName='ics')]}),Response({'data':{'messageId':'456'}})]
    def test_draft_only(self):
        s=Session(self.replies());r=ZohoDraftClient(self.config,s).create_draft(self.fields,self.files)
        self.assertEqual(r['message_id'],'456');self.assertEqual(s.calls[-1][1]['json']['mode'],'draft')
        self.assertEqual(len(s.calls[-1][1]['json']['attachments']),2)
        self.assertTrue(all(not kw['allow_redirects'] for _,kw in s.calls))
        self.assertEqual(len(s.calls),4)
        self.assertIn('calendar.google.com/calendar/render?',s.calls[-1][1]['json']['content'])
        self.assertEqual(s.calls[2][1]['files']['attach'][2],'text/calendar')
        self.assertIn(b'BEGIN:VALARM',s.calls[2][1]['files']['attach'][1])
        self.assertIn(b'TRIGGER:-P1D',s.calls[2][1]['files']['attach'][1])
    def test_no_retry_timeout(self):
        replies=self.replies();replies[-1]=TimeoutError('secret');s=Session(replies)
        with self.assertRaises(ZohoDraftError) as e: ZohoDraftClient(self.config,s).create_draft(self.fields,self.files)
        self.assertNotIn('secret',str(e.exception));self.assertEqual(len(s.calls),4)
    def test_bad_attachment_no_network(self):
        s=Session([])
        with self.assertRaises(ValueError): ZohoDraftClient(self.config,s).create_draft(self.fields,[('x',b'bad')])
        self.assertFalse(s.calls)
    def test_bad_upload_no_draft(self):
        s=Session([self.replies()[0],Response({'data':[]})])
        with self.assertRaises(ZohoDraftError): ZohoDraftClient(self.config,s).create_draft(self.fields,self.files)
        self.assertEqual(len(s.calls),2)
    def test_token_error_sanitized(self):
        s=Session([Response({'error':'secret'},401)])
        with self.assertRaises(ZohoDraftError) as e: ZohoDraftClient(self.config,s).create_draft(self.fields,self.files)
        self.assertNotIn('secret',str(e.exception))
    def test_config_secret_repr_and_hosts(self):
        self.assertNotIn('secret',repr(self.config));self.assertNotIn('refresh',repr(self.config))
        with self.assertRaises(ValueError): ZohoConfig('a','b','c','1','a@b.com',mail_url='https://evil.com')
if __name__=='__main__': unittest.main()
