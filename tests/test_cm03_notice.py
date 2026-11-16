import unittest
from am_hub_notice_extract import parse_ddjj
from am_hub_payment_notice import body_html,calendar_attachments

def doc(favor='7.738,23',fisco='0,00',pay='0,00',total=None):
 return '''IMPUESTO SOBRE LOS INGRESOS BRUTOS
CONVENIO MULTILATERAL
DJ MENSUAL - CM03
CUIT: 30-12345678-1
Anticipo: 202610
Jurisdicciones incluidas
Jurisdicción Anticipo Valores Restan Valores Suman A Favor A Favor Fisco A Pagar
Contribuyente
TOTALES $ 0,00 $ 7.738,23 $ 0,00 $ %s $ %s $ %s
Total a pagar: $ %s
'''%(favor,fisco,pay,total or pay)
class CM03Tests(unittest.TestCase):
 def test_credit(self):
  d=parse_ddjj(doc());self.assertEqual(d['resultado'],'Saldo a favor');self.assertEqual(d['monto'],'7.738,23');self.assertEqual(d['periodo'],'10/2026');self.assertEqual(d['vencimiento'],'')
 def test_payment_and_mixed_jurisdictions(self):
  d=parse_ddjj(doc('50,00','100,00','100,00'));self.assertEqual(d['resultado'],'A pagar');self.assertEqual(d['monto'],'100,00');self.assertTrue(any('no se compensa' in w for w in d['advertencias']))
 def test_all_zero(self):
  d=parse_ddjj(doc('0,00','0,00','0,00'));self.assertEqual(d['resultado'],'Sin saldo')
  f=dict(d,cliente='PRUEBA',email='test@example.com');self.assertIn('Sin importe a pagar',body_html(f));self.assertEqual(calendar_attachments(f),[])
 def test_ambiguous_table_and_conflicting_total(self):
  for t in [doc(total='1,00'),doc().replace(' $ 0,00','',1),doc()+doc(),doc('0,00','10,00','0,00')]:
   d=parse_ddjj(t);self.assertEqual(d['resultado'],'');self.assertEqual(d['monto'],'')
 def test_agip_zero_requires_three_explicit_totals(self):
  text='CONTRIBUYENTES LOCALES SICOL\nTOTAL A PAGAR $ 0,00\nSUBTOTAL A FAVOR DEL CONTRIBUYENTE $ 0,00\nSUBTOTAL A FAVOR DGR $ 0,00'
  self.assertEqual(parse_ddjj(text)['resultado'],'Sin saldo')
  self.assertNotEqual(parse_ddjj(text.replace('SUBTOTAL A FAVOR DGR $ 0,00',''))['resultado'],'Sin saldo')
