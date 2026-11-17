import unittest,json
from am_hub_notice_extract import parse_ddjj,card_deadline
class ExtractTests(unittest.TestCase):
 def test_agip_layout(self):
  d=parse_ddjj('CONTRIBUYENTES LOCALES SICOL\nPeríodo: 10 - 2026   Fecha venc: 13/11/2026 Fecha pago: 14/11/2026\nRazón Social: PRUEBA CUIT: 30-12345678-5\nSUBTOTAL A FAVOR DEL CONTRIBUYENTE: $ 315,20\nTOTAL A PAGAR $ 0,00')
  self.assertEqual((d['resultado'],d['monto'],d['vencimiento'],d['periodo']),('Saldo a favor','315,20','13/11/2026','10/2026'))
 def test_zero_not_invented(self):
  d=parse_ddjj('CONTRIBUYENTES LOCALES SICOL\nTOTAL A PAGAR $ 0,00');self.assertEqual(d['monto'],'')
 def test_iva_current_not_prior_or_free(self):
  d=parse_ddjj('F.2051\nVista Previa | 10/2026\nCUIT Denominación\n30-12345678-5 PRUEBA\nSaldo técnico a favor del contribuyente del período anterior $ 999,00\nSaldo técnico a favor del contribuyente $ 100,00\nSaldo técnico a favor de ARCA $ 0,00\nSaldo de libre disponibilidad a favor del contribuyente del período $ 50,00')
  self.assertEqual((d['monto'],d['vencimiento'],d['cuit']),('50,00','','30-12345678-5'))
 def test_arca_warns(self):
  d=parse_ddjj('F.2051\nSaldo técnico a favor de ARCA $ 10,00');self.assertEqual(d['monto'],'10,00');self.assertIn('no equivale',d['nota_saldo'])
