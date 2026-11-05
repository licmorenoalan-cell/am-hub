import unittest
from am_hub_tax_calendar import (encode_metadata, metadata, resolve, apply_resolution,
    next_ganancias_ph_period, ganancias_ph_period, fiscal_period_label, validate_completion)
from am_hub_tasks import construir_siguiente_ocurrencia


def advance(period='2026-12', digit=5):
    return dict(id='test-advance', cliente='Example', tarea='Anticipo de Ganancias',
                recurrente='Sí', frecuencia='Mensual', intervalo=2, fecha_limite='',
                id_externo=encode_metadata(dict(impuesto='GANANCIAS', obligacion='ANTICIPO_PH',
                    jurisdiccion='NACIONAL', periodo=period, terminacion=digit)))


class AdvanceCycleTests(unittest.TestCase):
    def test_five_advances_per_exercise_and_september_exception(self):
        period='2025-08'; observed={}
        for _ in range(60):
            year,number=ganancias_ph_period(period)
            observed.setdefault(year,[]).append(number)
            self.assertNotIn(period[-2:], ['01','03','05','06','07','11'])
            if period[-2:]=='09':self.assertEqual(period,'2026-09')
            period=next_ganancias_ph_period(period)
        self.assertTrue(all(numbers==[1,2,3,4,5] for numbers in observed.values()))
        self.assertEqual(next_ganancias_ph_period('2026-04'),'2026-09')
        self.assertEqual(next_ganancias_ph_period('2026-09'),'2026-10')
        self.assertEqual(next_ganancias_ph_period('2027-04'),'2027-08')

    def test_fourth_fifth_groups_and_unpublished_following_year(self):
        for digit in range(10):
            group=0 if digit<4 else 1 if digit<7 else 2
            fourth=construir_siguiente_ocurrencia(advance(digit=digit),'test')
            self.assertEqual(fourth['fecha_limite'],f'2027-02-{15+group}')
            fifth=construir_siguiente_ocurrencia(fourth,'test')
            self.assertEqual(fifth['fecha_limite'],f'2027-04-{13+group}')
            first=construir_siguiente_ocurrencia(fifth,'test')
            self.assertEqual(metadata(first)['periodo'],'2027-08')
            self.assertEqual(first['fecha_limite'],'')
            self.assertEqual(metadata(first)['estado'],'pendiente')

    def test_december_official_agenda_groups_and_wrong_manual_date(self):
        for digit in range(10):
            expected=f'2026-12-{14 if digit<4 else 15 if digit<7 else 16}'
            t=apply_resolution(advance(digit=digit),resolve(advance(digit=digit)))
            self.assertEqual(t['fecha_limite'],expected)
            self.assertEqual(metadata(t)['fuente'],'https://seti.afip.gob.ar/av/')
            validate_completion(t)
            t['fecha_limite']='2026-12-13'
            with self.assertRaises(ValueError):validate_completion(t)

    def test_missing_agenda_still_blocks_manual_dates(self):
        from unittest.mock import patch
        from am_hub_tax_calendar import load_calendar
        rows=[r for r in load_calendar() if not (r['impuesto']=='GANANCIAS' and r['periodo']=='2026-12')]
        with patch('am_hub_tax_calendar.load_calendar',return_value=rows):
            for date in ['','2026-12-14','2026-12-15','2026-12-16']:
                t=advance();t['fecha_limite']=date
                self.assertEqual(resolve(t)['fecha'],'')
                with self.assertRaises(ValueError):validate_completion(t)

    def test_company_profile_never_supplies_personal_digit(self):
        t=advance();profile=[dict(cliente='Example',cuit='30000000006')]
        self.assertEqual(resolve(t,profile,next_period=True)['fecha'],'2027-02-16')
        ctx=metadata(t);ctx.pop('terminacion');t['id_externo']=encode_metadata(ctx)
        self.assertEqual(resolve(t,profile,next_period=True)['fecha'],'')
        self.assertNotIn('terminacion',resolve(t,profile)['contexto'])

    def test_invalid_months_and_cadence_fail_closed(self):
        for period in ['2026-08','2027-09','2027-06','2026','2027-00']:
            self.assertEqual(resolve(advance(period),next_period=True)['fecha'],'')
            with self.assertRaises(ValueError):construir_siguiente_ocurrencia(advance(period),'test')
        for changes in [dict(intervalo=1),dict(intervalo=3),dict(frecuencia='Anual')]:
            with self.assertRaises(ValueError):construir_siguiente_ocurrencia(dict(advance(),**changes),'test')

    def test_resolution_idempotent_and_label_distinguishes_fiscal_year(self):
        t=advance('2027-02');a=apply_resolution(t,resolve(t));b=apply_resolution(a,resolve(a))
        self.assertEqual(a,b)
        label=fiscal_period_label(a)
        self.assertIn('ejercicio 2026',label);self.assertIn('anticipo 4/5',label)
        self.assertIn('normativa vigente',label);self.assertNotIn('Revisar categoría',label)

if __name__=='__main__':unittest.main()
