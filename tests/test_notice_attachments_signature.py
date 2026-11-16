import unittest,hashlib
from email import policy
from email.parser import BytesParser
from am_hub_payment_notice import named_attachments,email_draft
from am_hub_zoho_drafts import select_accounting_signature,ZohoDraftError
class NamingSignatureTests(unittest.TestCase):
 def setUp(self):
  self.f=dict(cliente='PRUEBA',email='test@example.com',impuesto='IVA',periodo='10/2026',monto='1',vencimiento='30/11/2026')
 def test_four_names(self):
  files=[];mapping={}
  for i,(kind,tax) in enumerate([('DDJJ','IVA'),('DDJJ','IIBB'),('VEP','IVA'),('VEP','IIBB')]):
   data=('%PDF-'+str(i)).encode();files.append(('original'+str(i)+'.pdf',data));mapping[hashlib.sha256(data).hexdigest()]=dict(tipo=kind,impuesto=tax,periodo='2026-10')
  self.f['documentos']=mapping
  want=['102026 DDJJ IVA.pdf','102026 DDJJ IIBB.pdf','VEP 102026 DDJJ IVA.pdf','VEP 102026 DDJJ IIBB.pdf']
  self.assertEqual([n for n,d in named_attachments(self.f,files)],want)
  msg=BytesParser(policy=policy.default).parsebytes(email_draft(self.f,files))
  self.assertEqual([p.get_filename() for p in msg.iter_attachments()][:4],want)
 def test_unknown_preserved_collision_dedup(self):
  files=[('one.pdf',b'%PDF-1'),('two.pdf',b'%PDF-2'),('repeat.pdf',b'%PDF-1'),('backup.pdf',b'%PDF-3')]
  self.f['documentos']={hashlib.sha256(d).hexdigest():dict(tipo='DDJJ',impuesto='IVA',periodo='10/2026') for _,d in files[:2]}
  self.assertEqual([n for n,d in named_attachments(self.f,files)],['102026 DDJJ IVA.pdf','102026 DDJJ IVA (2).pdf','backup.pdf'])
 def test_ambiguous_blocks(self):
  self.f['documentos']={hashlib.sha256(b'%PDF-1').hexdigest():dict(tipo='DDJJ',impuesto='?',periodo='10/2026')}
  with self.assertRaises(ValueError):named_attachments(self.f,[('one.pdf',b'%PDF-1')])
 def test_signature_exact_existing_html(self):
  html='<table><img src="/zm/ImageSignature?a=1">Depto. Contable</table>'
  self.assertEqual(select_accounting_signature({'data':[{'name':'Alan','content':'other'},{'name':'Contable','content':html}]}),html)
  for entries in [[],[{'name':'Alan','content':html}],[{'name':'Contable','content':'wrong'}],[{'name':'Contable','content':html}]*2]:
   with self.assertRaises(ZohoDraftError):select_accounting_signature({'data':entries})
