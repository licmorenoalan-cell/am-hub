#!/usr/bin/env python3
"""Read-only by default. Review the report; apply ONLY after both apps deploy fiscal-v1.

Uses the existing local configuration helper. Never prints credentials/CUITs or
client names. --apply requires an explicit deployed-engine acknowledgement.
"""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from am_hub_tax_calendar import is_fiscal, resolve, apply_resolution, encode_metadata, suggested_period, context, load_calendar, PENDING
from sqlalchemy import create_engine, text
from rebuild_tax_recurring_tasks import database_url

def proposed(task, profiles, overrides=None, activations=None):
    if task.get('estado') == 'Finalizada':
        return None
    supplied = (overrides or {}).get(task.get('id'))
    external = str(task.get('id_externo') or '')
    if supplied and (not external or external.startswith('fiscal:v1:')):
        task = dict(task, id_externo=encode_metadata(supplied))
    activation = (activations or {}).get(task.get('id'))
    if activation:
        task = dict(task, **activation, recurrente='Sí', frecuencia='Mensual', intervalo=1,
                    serie_id='SER-' + task['id'], ocurrencia=1)
    elif task.get('recurrente') != 'Sí' or not is_fiscal(task):
        return None
    resolved = resolve(task, profiles)
    result = apply_resolution(task, resolved, preserve_legacy_date=True)
    return {k: result.get(k) for k in ('tarea','descripcion','fecha_limite','id_externo','comentarios',
                                     'recurrente','frecuencia','intervalo','serie_id','ocurrencia')}


def audit(connection, apply=False, overrides=None, activations=None):
    rows = connection.execute(text('SELECT * FROM tareas' + (' FOR UPDATE' if apply else ''))).mappings().all()
    profiles = connection.execute(text('SELECT cliente,cuit,iibb_regimen,iibb_jurisdiccion FROM fiscal_clientes')).mappings().all()
    report=[]
    for row in rows:
        changes=proposed(dict(row), profiles, overrides, activations)
        if changes is None:
            continue
        changes={k:v for k,v in changes.items() if row.get(k) != v}
        if not changes:
            continue
        updated=dict(row, **changes)
        reason=resolve(updated,profiles)['motivo']
        warnings=[line for line in str(updated.get('comentarios') or '').splitlines() if line.startswith(PENDING + ': ')]
        if warnings:
            reason=warnings[-1][len(PENDING)+2:]
        ctx,_=context(updated,profiles)
        relevant=[entry for entry in load_calendar() if all(entry.get(k)==ctx.get(k) for k in ('impuesto','obligacion','jurisdiccion'))]
        calendar_status=('Obligación o jurisdicción sin identificar' if not ctx.get('obligacion') or not ctx.get('jurisdiccion') else
            'Sin tabla oficial cargada para esta obligación' if not relevant else
            'Tablas disponibles; período por confirmar' if not ctx.get('periodo') else
            'Entrada de período/grupo pendiente' if reason=='Calendario oficial no disponible' else
            'Tabla oficial disponible para el período')
        report.append({'id':row['id'],'fecha_anterior':row.get('fecha_limite'),
                       'fecha_propuesta':changes.get('fecha_limite',row.get('fecha_limite')),
                       'motivo':reason or 'Calendario oficial verificado',
                       'cobertura_calendario':calendar_status,
                       'impuesto':ctx.get('impuesto'), 'obligacion':ctx.get('obligacion'),
                       'jurisdiccion':ctx.get('jurisdiccion'), 'periodo':ctx.get('periodo'),
                       'periodo_fuente':ctx.get('periodo_fuente'),
                       'periodo_sugerido_no_confirmado':suggested_period(dict(row),profiles),
                       'campos':list(changes)})
        if apply:
            connection.execute(text('UPDATE tareas SET '+','.join(f'"{k}"=:{k}' for k in changes)+
                ', fecha_actualizacion=:today, actualizado_por=:author WHERE id=:task_id'),
                dict(changes, today=date.today().isoformat(),author='Revisión calendario fiscal',task_id=row['id']))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--activate',type=Path,help='JSON por ID con título/descripción revisados; habilita recurrencia mensual solo en esas tarjetas.')
    parser.add_argument('--config',type=Path,help='JSON por ID: impuesto, obligacion, jurisdiccion, periodo, terminacion. Sin CUIT completos.')
    parser.add_argument('--deployed-engine',choices=['fiscal-v1'])
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    if args.apply and args.deployed_engine != 'fiscal-v1':
        parser.error('Aplicar requiere confirmar el despliegue de AM Hub y Pocket con --deployed-engine fiscal-v1')
    overrides=json.loads(args.config.read_text()) if args.config else {}
    allowed={'impuesto','obligacion','jurisdiccion','periodo','terminacion','periodo_fuente'}
    if not isinstance(overrides,dict) or any(not isinstance(v,dict) or set(v)-allowed for v in overrides.values()):
        parser.error('Configuración inválida: solo se admiten los campos fiscales documentados')
    activations=json.loads(args.activate.read_text()) if args.activate else {}
    if not isinstance(activations,dict) or any(not isinstance(v,dict) or set(v)-{'tarea','descripcion'} for v in activations.values()):
        parser.error('Activaciones inválidas: solo tarea y descripcion')
    if set(activations)-set(overrides):
        parser.error('Cada activación necesita una configuración fiscal explícita')
    engine=create_engine(database_url(),connect_args={'connect_timeout':10,'prepare_threshold':None})
    with engine.begin() as connection:
        result=audit(connection,args.apply,overrides,activations)
    if args.apply:
        with engine.connect() as connection:
            remaining=audit(connection,False,overrides,activations)
        changed_ids={r['id'] for r in result}
        if any(r['id'] in changed_ids for r in remaining):
            raise RuntimeError('La verificación posterior al commit requiere revisión')
    report={'aplicado':args.apply,'cantidad':len(result),'motivos':dict(Counter(r['motivo'] for r in result)), 'tarjetas':result}
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='tarjetas'},ensure_ascii=False))


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        # Database exceptions can contain credentials or identifiers. Do not print them.
        print('No se completó la operación:',type(exc).__name__,file=sys.stderr)
        raise SystemExit(1)
