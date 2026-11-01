import copy
import json
import unittest
from am_hub_tax_calendar import (resolve, encode_metadata, metadata, is_fiscal,
                                 apply_resolution, load_calendar, context)
from am_hub_tasks import construir_siguiente_ocurrencia


def task(digit=8, period='2026-11'):
    return {'id': 'test', 'tarea': 'Convenio Multilateral', 'categoria': 'Ingresos Brutos',
            'frecuencia': 'Mensual', 'intervalo': 1, 'fecha_limite': '2026-12-18',
            'id_externo': encode_metadata(dict(impuesto='IIBB', obligacion='CM03',
                 jurisdiccion='COMARB', periodo=period, terminacion=digit))}


class FiscalCalendarTests(unittest.TestCase):
    def test_groups_and_year_boundary(self):
        for digit, day in ((0,15),(2,15),(3,18),(5,18),(6,19),(7,19),(8,20),(9,20)):
            result = resolve(task(digit), next_period=True)
            self.assertEqual(result['fecha'], f'2027-01-{day}')
            self.assertEqual(result['contexto']['periodo'], '2026-12')

    def test_unknown_next_calendar_never_reuses_day(self):
        previous = task(period='2026-12')
        previous['fecha_limite'] = '2027-01-20'
        result = construir_siguiente_ocurrencia(previous, 'tester')
        self.assertEqual(result['fecha_limite'], '')
        self.assertEqual(metadata(result)['periodo'], '2027-01')
        self.assertIn('Vencimiento fiscal pendiente', result['comentarios'])
        self.assertEqual(result['recurrente'], 'Sí')

    def test_untrusted_or_duplicate_calendar_is_blocked(self):
        rows = load_calendar()
        self.assertEqual(resolve(task(), calendar=rows+rows)['fecha'], '')
        for r in rows:
            r['verificado'] = False
        self.assertEqual(resolve(task(), calendar=rows)['fecha'], '')

    def test_missing_data_never_inferred_from_arbitrary_due_date(self):
        t = task(); t['id_externo'] = ''; t['fecha_limite'] = '2026-11-30'
        self.assertEqual(resolve(t, next_period=True)['fecha'], '')
        self.assertIn('periodo', resolve(t)['motivo'])
        self.assertIn('terminación', resolve(t)['motivo'])

    def test_profile_resolves_digit_without_copying_identifier(self):
        t = task();t['cliente']='Example'; m=metadata(t);m.pop('terminacion');t['id_externo']=encode_metadata(m)
        profiles=[dict(cliente='Example',cuit='30000000008',iibb_regimen='Convenio Multilateral')]
        result=construir_siguiente_ocurrencia(t,'tester',perfiles=profiles)
        self.assertEqual(result['fecha_limite'],'2027-01-20')
        self.assertNotIn('30000000008',json.dumps(result))

    def test_conflicting_identifiers_and_duplicate_profiles_block(self):
        t=task();t['cliente']='Example'
        profiles=[dict(cliente='Example',cuit='30000000007')]
        self.assertIn('contradictorias',resolve(t,profiles)['motivo'])
        self.assertIn('Más de una',resolve(t,profiles*2)['motivo'])

    def test_iva_never_inherits_client_iibb_classification(self):
        t=dict(tarea='IVA',categoria='IVA',cliente='Example')
        ctx,_=context(t,[dict(cliente='Example',iibb_regimen='Convenio Multilateral',iibb_jurisdiccion='AGIP - CABA')])
        self.assertEqual(ctx['impuesto'],'IVA')
        self.assertEqual(ctx['jurisdiccion'],'NACIONAL')

    def test_reclassification_and_jurisdiction_are_explicit(self):
        for title,profile,jurisdiction in [('IIBB',{'iibb_regimen':'Local','iibb_jurisdiccion':'AGIP - CABA'},'CABA'),('IIBB',{'iibb_regimen':'Local','iibb_jurisdiccion':'ARBA - Buenos Aires'},'BUENOS AIRES')]:
            ctx,_=context(dict(tarea=title,cliente='Example'),[dict(profile,cliente='Example')])
            self.assertEqual(ctx['jurisdiccion'],jurisdiction)
        ctx,_=context(dict(tarea='Monotributo: recategorización'))
        self.assertEqual(ctx['obligacion'],'RECATEGORIZACION')

    def test_other_taxes_fail_closed(self):
        for title in ['Autónomos','Monotributo','Recategorización','Anticipos','Ganancias','Tasas municipales','Impuestos','SUSS','CM05']:
            t=dict(tarea=title,fecha_limite='2026-12-31',frecuencia='Mensual')
            self.assertTrue(is_fiscal(t))
            with self.assertRaisesRegex(ValueError,'falta período'):
                construir_siguiente_ocurrencia(t,'test')

    def test_non_fiscal_still_monthly_with_end_of_month(self):
        t=dict(tarea='Reporte comercial',fecha_limite='2026-01-31',frecuencia='Mensual')
        self.assertEqual(construir_siguiente_ocurrencia(t,'test')['fecha_limite'],'2026-02-28')

    def test_unknown_external_id_preserved_and_blocked(self):
        t=task();t['id_externo']='external:123'
        updated=apply_resolution(t,resolve(task()))
        self.assertEqual(updated['id_externo'],'external:123')
        self.assertEqual(updated['fecha_limite'],'')

    def test_metadata_keeps_only_allowlisted_fields(self):
        value=encode_metadata(dict(cuit='30000000008',terminacion=8,periodo='2026-12'))
        self.assertNotIn('30000000008',value)

    def test_invalid_frequency_and_interval_fail_closed(self):
        for changes in ({'frecuencia':'Semanal'},{'intervalo':-1},{'intervalo':1.5}):
            self.assertEqual(resolve(dict(task(),**changes),next_period=True)['fecha'],'')

    def test_historical_input_is_not_modified(self):
        t=task();before=copy.deepcopy(t)
        construir_siguiente_ocurrencia(t,'test')
        self.assertEqual(t,before)

    def test_invalid_metadata_does_not_crash(self):
        self.assertEqual(metadata({'id_externo':'fiscal:v1:[]'}),{})
        self.assertEqual(metadata({'id_externo':'fiscal:v1:bad'}),{})

    def test_missing_digit_does_not_keep_previous_period(self):
        t=task();m=metadata(t);m.pop('terminacion');t['id_externo']=encode_metadata(m)
        r=resolve(t,next_period=True)
        self.assertEqual(r['fecha'],'')
        self.assertEqual(r['contexto']['periodo'],'2026-12')

    def test_annual_period_is_not_treated_as_a_month(self):
        t=task();t['frecuencia']='Anual';m=metadata(t);m.update(periodo='2025',obligacion='CM05');t['id_externo']=encode_metadata(m)
        entry=dict(impuesto='IIBB',obligacion='CM05',jurisdiccion='COMARB',periodo='2026',terminaciones=[8],vencimiento='2027-06-30',fuente='https://example.invalid/test-only',norma='TEST FIXTURE',verificado=True,verificado_el='2026-11-01')
        result=resolve(t,calendar=[entry],next_period=True)
        self.assertEqual(result['contexto']['periodo'],'2026')
        self.assertEqual(result['fecha'],'2027-06-30')

    def test_jurisdiction_mismatch_cannot_use_another_calendar(self):
        t=task();m=metadata(t);m['jurisdiccion']='CABA';t['id_externo']=encode_metadata(m)
        self.assertEqual(resolve(t,next_period=True)['fecha'],'')

    def test_arba_general_verified_dates_and_simplificado_excluded(self):
        for period,expected in [('2026-10','2026-11-30'),('2026-11','2026-12-29'),('2026-12','2027-01-22')]:
            t=task(8,period);m=metadata(t);m.update(jurisdiccion='BUENOS AIRES',obligacion='MENSUAL');t['id_externo']=encode_metadata(m)
            self.assertEqual(resolve(t)['fecha'],expected)
        ctx,_=context({'tarea':'IIBB ARBA local simplificado'})
        self.assertEqual(ctx['obligacion'],'SIMPLIFICADO')
        self.assertEqual(resolve({'tarea':'IIBB ARBA local simplificado'})['fecha'],'')

    def test_explicit_spanish_period_first_occurrence_only(self):
        t={'tarea':'IVA','descripcion':'Período: octubre 2026','ocurrencia':1}
        self.assertEqual(context(t)[0]['periodo'],'2026-10')
        t['ocurrencia']=2
        self.assertNotIn('periodo',context(t)[0])

    def test_exact_due_date_does_not_confirm_legacy_period(self):
        t={'tarea':'IVA','fecha_limite':'2026-11-25','descripcion':'CUIT: 30000000008'}
        self.assertNotIn('periodo',context(t)[0])
        self.assertEqual(resolve(t)['fecha'],'')

    def test_local_regime_is_not_assumed_general(self):
        for label in ['IIBB ARBA local','IIBB AGIP local']:
            self.assertEqual(context({'tarea':label})[0]['obligacion'],'')
        self.assertEqual(context({'tarea':'IIBB ARBA local régimen general'})[0]['obligacion'],'MENSUAL')

    def test_official_national_and_agip_groups(self):
        cases=[('IVA','2026-10',7,'2026-11-24'),('IVA','2026-11',4,'2026-12-22'),
               ('AUTONOMOS','2026-09',8,'2026-10-07'),('AUTONOMOS','2026-10',6,'2026-11-11'),
               ('AUTONOMOS','2026-11',8,'2026-12-11'),('MONOTRIBUTO','2026-12',None,'2026-12-21')]
        for tax,period,digit,due in cases:
            t={'tarea':tax,'id_externo':encode_metadata(dict(impuesto=tax,obligacion='MENSUAL',jurisdiccion='NACIONAL',periodo=period,terminacion=digit))}
            if digit is None:
                m=metadata(t);m.pop('terminacion');t['id_externo']=encode_metadata(m)
            self.assertEqual(resolve(t)['fecha'],due)
        for digit in [4,5]:
            t={'tarea':'IIBB','id_externo':encode_metadata(dict(impuesto='IIBB',obligacion='MENSUAL',jurisdiccion='CABA',periodo='2026-10',terminacion=digit))}
            self.assertEqual(resolve(t)['fecha'],'2026-11-13')
        t['id_externo']=encode_metadata(dict(impuesto='IIBB',obligacion='MENSUAL',jurisdiccion='CABA',periodo='2026-10',terminacion=0))
        self.assertEqual(resolve(t)['fecha'],'')

    def test_recategorization_normative_candidate_is_not_official_entry(self):
        t={'tarea':'Recategorización monotributo','id_externo':encode_metadata(dict(impuesto='MONOTRIBUTO',obligacion='RECATEGORIZACION',jurisdiccion='NACIONAL',periodo='2027-02'))}
        self.assertEqual(resolve(t)['fecha'],'')
        self.assertEqual(resolve(t)['motivo'],'Calendario oficial no disponible')

    def test_new_fiscal_recurrence_cannot_start_on_arbitrary_date(self):
        from am_hub_tasks import preparar_nueva_tarea_fiscal
        t={'tarea':'IVA','recurrente':'Sí','fecha_limite':'2026-11-01'}
        prepared=preparar_nueva_tarea_fiscal(t)
        self.assertEqual(prepared['fecha_limite'],'')
        self.assertIn('Vencimiento fiscal pendiente',prepared['comentarios'])

    def test_calendar_has_no_overlapping_verified_entries(self):
        seen=set()
        for r in load_calendar():
            for digit in r['terminaciones']:
                key=tuple(r[k] for k in ('impuesto','obligacion','jurisdiccion','periodo'))+(digit,)
                self.assertNotIn(key,seen)
                seen.add(key)

    def test_unverified_metadata_cannot_retrust_inherited_description(self):
        t={'tarea':'IVA','ocurrencia':2,'descripcion':'Período: septiembre 2026', 'recurrente':'Sí'}
        prepared=apply_resolution(t,resolve(t),preserve_legacy_date=True)
        prepared['ocurrencia']=1  # A user-made duplicate must not resurrect stale period text.
        self.assertNotIn('periodo',context(prepared)[0])

    def test_board_label_distinguishes_data_from_calendar_without_official_claim(self):
        from am_hub_tax_calendar import pending_label
        legacy={'tarea':'IVA','recurrente':'Sí','fecha_limite':'2026-11-25'}
        data=apply_resolution(legacy,resolve(legacy),preserve_legacy_date=True)
        self.assertIn('Datos fiscales por revisar',pending_label(data))
        self.assertIn('fecha previa sin verificar: 2026-11-25',pending_label(data))
        future=task(period='2027-01');future['recurrente']='Sí'
        calendar=apply_resolution(future,resolve(future))
        self.assertIn('Calendario fiscal pendiente',pending_label(calendar))
        self.assertNotIn('2026-12-18',pending_label(calendar))
        known=apply_resolution(task(),resolve(task()))
        self.assertEqual(pending_label(known),'')

    def test_comarb_october_exception_uses_own_groups_and_source(self):
        for digit,day in [(0,17),(1,17),(2,17),(3,18),(4,18),(5,18),(6,19),(7,19),(8,20),(9,20)]:
            result=resolve(task(digit,'2026-10'))
            self.assertEqual(result['fecha'],f'2026-11-{day}')
            self.assertEqual(result['contexto']['fuente'],'https://www.ca.gob.ar/descargas/sifere/vencimientos/2026-11.pdf')
        entries=[r for r in load_calendar() if r['jurisdiccion']=='COMARB' and r['periodo']=='2026-10']
        self.assertEqual(len(entries),4)
        self.assertTrue(all('20/2025' in r['reemplaza'] and '11/2026' in r['norma'] for r in entries))

    def test_release_diagnostic_contains_only_public_code_provenance(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from types import SimpleNamespace
        from am_hub_tax_calendar import announce_release
        announce_release.cache_clear()
        with patch('am_hub_tax_calendar.subprocess.run',return_value=SimpleNamespace(stdout='a'*40+'\n')):
            with redirect_stdout(io.StringIO()) as output:
                result=announce_release('app.py')
        self.assertEqual(result['revision'],'a'*40)
        self.assertEqual(result['calendar_entries'],68)
        self.assertEqual(len(result['fingerprint']),64)
        self.assertNotIn('DATABASE',output.getvalue())
        announce_release.cache_clear()
