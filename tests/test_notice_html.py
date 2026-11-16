import unittest
from html.parser import HTMLParser
from urllib.parse import urlparse,parse_qs
from am_hub_payment_notice import body,body_html
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[];self.text=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a': self.links.append(dict(attrs)['href'])
 def handle_data(self,data):self.text.append(data)
class HtmlTests(unittest.TestCase):
 def setUp(self):
  self.f=dict(cliente='PRUEBA',email='test@example.com',avisos=[dict(impuesto='IVA',periodo='11/2026',monto='1,00',vencimiento='20/11/2026'),dict(impuesto='IIBB',periodo='11/2026',monto='2,00',vencimiento='30/11/2026')])
 def test_two(self):
  h=body_html(self.f);self.assertIn('Adjuntamos la documentación de IVA e INGRESOS BRUTOS del periodo de referencia.',h)
  self.assertIn('<strong>IVA</strong>',h);self.assertIn('<strong>Ingresos brutos</strong>',h)
  p=Links();p.feed(h);self.assertEqual(len(p.links),2);self.assertNotIn('https://',''.join(p.text))
  self.assertEqual(parse_qs(urlparse(p.links[0]).query)['dates'],['20261120/20261121'])
  self.assertEqual(parse_qs(urlparse(p.links[1]).query)['dates'],['20261130/20261201'])
 def test_single_no_invented_tax(self):
  self.f['avisos']=self.f['avisos'][:1];h=body_html(self.f)
  self.assertNotIn('INGRESOS BRUTOS',h);self.assertIn('documentación de IVA del periodo',h)
  self.assertTrue(body(self.f).startswith('Buenos días!\n\n'))
 def test_escape_unknown_tax(self):
  self.f['avisos'][0]['impuesto']='<img src=x>'
  h=body_html(self.f);self.assertNotIn('<img',h);self.assertIn('&lt;img',h)
