"""Pure, conservative plans for fiscal onboarding. No persistence or external calls.

Callers must preview and atomically revalidate a plan against current rows before
applying. Client names remain existing relationship keys; this module never merges
aliases or rewrites tasks, periods, permissions, or account access.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
import re
from am_hub_tax_calendar import (apply_resolution, context, encode_metadata,
                                 is_fiscal, load_calendar, metadata, resolve)

TAX_OPTIONS = {
    'IVA': ('IVA', 'MENSUAL', 'NACIONAL'),
    'Convenio Multilateral (CM03)': ('IIBB', 'CM03', 'COMARB'),
    'Ingresos Brutos local CABA (régimen general)': ('IIBB', 'MENSUAL', 'CABA'),
    'Ingresos Brutos local Buenos Aires (régimen general)': ('IIBB', 'MENSUAL', 'BUENOS AIRES'),
    'Monotributo': ('MONOTRIBUTO', 'MENSUAL', 'NACIONAL'),
    'Autónomos': ('AUTONOMOS', 'MENSUAL', 'NACIONAL'),
}


def validate_cuit(value):
    raw = str(value or '').strip()
    if not re.fullmatch(r'(?:\d{11}|\d{2}-\d{8}-\d)', raw):
        raise ValueError('Ingresá un CUIT completo de 11 dígitos, con o sin guiones.')
    normalized = raw.replace('-', '')
    if normalized == '0' * 11:
        raise ValueError('CUIT inválido.')
    check = 11 - sum(int(n) * w for n, w in zip(normalized[:10], (5,4,3,2,7,6,5,4,3,2))) % 11
    check = 0 if check == 11 else (9 if check == 10 else check)
    if int(normalized[-1]) != check:
        raise ValueError('El dígito verificador del CUIT no es válido.')
    return normalized


def _key(value):
    return ' '.join(str(value or '').split()).casefold()


def _stable(prefix, *parts):
    return prefix + '-' + hashlib.sha256('\x1f'.join(parts).encode()).hexdigest()[:24]


def _identity(meta):
    return tuple(meta.get(k) for k in ('impuesto', 'obligacion', 'jurisdiccion'))


def snapshot_fingerprint(clients=(), profiles=(), tasks=()):
    """Canonical optimistic-lock token. Use identical full table projections."""
    def scalar(value):
        if value is None or isinstance(value, float) and math.isnan(value): return ''
        if isinstance(value, float) and value.is_integer(): return str(int(value))
        return str(value)
    groups=[]
    for rows in (clients, profiles, tasks):
        records=[{str(k): scalar(v) for k,v in dict(r).items()} for r in rows]
        groups.append(sorted(records,key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False)))
    return hashlib.sha256(json.dumps(groups,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def reconciliation_inventory(clients=(), profiles=(), tasks=()):
    """Return exact-name inventory; normalized names only flag possible conflicts."""
    client_names = [str(r.get('cliente') or '') for r in clients]
    profile_names = [str(r.get('cliente') or '') for r in profiles]
    task_names = [str(r.get('cliente') or '') for r in tasks]
    names = sorted(set(client_names + profile_names + task_names) - {''}, key=str.casefold)
    result = []
    for name in names:
        cp = [p for p in profiles if p.get('cliente') == name]
        aliases = [n for n in names if n != name and _key(n) == _key(name)]
        conflicts = []
        if aliases: conflicts.append('Variantes del mismo nombre: revisar sin fusionar automáticamente')
        if client_names.count(name) > 1: conflicts.append('Clientes duplicados')
        if len(cp) > 1: conflicts.append('Más de una ficha fiscal')
        valid = False
        if len(cp) == 1:
            try:
                cuit = validate_cuit(cp[0].get('cuit')); valid = True
                if any(p.get('cliente') != name and str(p.get('cuit') or '').replace('-', '') == cuit for p in profiles):
                    conflicts.append('CUIT compartido por otra ficha: revisar identidad')
            except ValueError: pass
        status = ('conflicto' if conflicts else 'cliente_solo_en_tareas' if name not in client_names and name in task_names
                  else 'ficha_sin_cliente' if name not in client_names else 'sin_ficha_fiscal' if not cp
                  else 'ficha_incompleta' if not valid else 'identidad_fiscal_disponible')
        result.append(dict(cliente=name, estado=status, cantidad_tareas=task_names.count(name),
                           cantidad_clientes=client_names.count(name), cantidad_fichas=len(cp), conflictos=conflicts))
    return result


def plan_onboarding(cliente, cuit, taxes, period, clients=(), profiles=(), tasks=(),
                    calendar=None, responsable='AM Consultora', actor='', today=None, client_record=None):
    """Plan only explicitly selected MONTHLY registrations and a confirmed period.

    Returns profile (existing data + blank fields filled), tasks to insert,
    existing task references, conflicts (block apply), and warnings. Does not
    authorize an actual tax registration or imply complete commercial onboarding.
    """
    result = dict(profile=None, tasks=[], existing=[], conflicts=[], warnings=[],
                  cliente=str(cliente or '').strip(), cuit='', client_insert=None,
                  profile_insert=None, profile_updates=None,
                  snapshot_hash=snapshot_fingerprint(clients,profiles,tasks))
    name = str(cliente or '').strip()
    if not name:
        result['conflicts'].append('Completá el cliente.'); return result
    try: cuit = validate_cuit(cuit)
    except ValueError as exc:
        result['conflicts'].append(str(exc)); return result
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', str(period)):
        result['conflicts'].append('Confirmá el primer período fiscal en formato AAAA-MM.'); return result
    result['cuit']=cuit
    selected = list(dict.fromkeys(taxes or []))
    if not selected:
        result['conflicts'].append('Seleccioná los impuestos en que está inscripto.'); return result
    unknown = [x for x in selected if x not in TAX_OPTIONS]
    if unknown:
        result['conflicts'].append('Impuestos no soportados: ' + ', '.join(map(str, unknown))); return result
    if 'IVA' in selected and 'Monotributo' in selected:
        result['conflicts'].append('IVA y Monotributo simultáneos: revisar inscripciones antes de generar tarjetas.')
    if sum(TAX_OPTIONS[t][0] == 'IIBB' for t in selected) > 1:
        result['conflicts'].append('Más de un régimen IIBB: confirmar cuál corresponde.')
    if 'Autónomos' in selected and cuit[:2] in ('30', '33', '34'):
        result['conflicts'].append('Autónomos corresponde a la persona, no al CUIT de la sociedad.')
    names = {str(r.get('cliente') or '') for r in [*clients, *profiles, *tasks]}
    if any(n != name and _key(n) == _key(name) for n in names):
        result['conflicts'].append('Hay una variante del nombre existente. Seleccioná la identidad exacta; no se fusiona automáticamente.')
    if sum(r.get('cliente') == name for r in clients) > 1:
        result['conflicts'].append('Más de un cliente con el mismo nombre.')
    same = [p for p in profiles if p.get('cliente') == name]
    if len(same) > 1:
        result['conflicts'].append('Más de una ficha fiscal para este cliente.')
    for p in profiles:
        existing_cuit = str(p.get('cuit') or '').strip().replace('-', '')
        if p.get('cliente') != name and existing_cuit == cuit:
            result['conflicts'].append('Este CUIT figura en otra ficha. Revisar identidad sin duplicar clientes.')
    if len(same) == 1 and str(same[0].get('cuit') or '').strip():
        try: original_cuit = validate_cuit(same[0]['cuit'])
        except ValueError: original_cuit = None
        if original_cuit != cuit:
            result['conflicts'].append('El CUIT ingresado contradice la ficha existente; no se sobrescribe.')
    if result['conflicts']: return result
    profile = dict(same[0]) if same else dict(id=_stable('FCLI-ONB', name), cliente=name)
    if not str(profile.get('cuit') or '').strip(): profile['cuit'] = cuit
    # These fields reflect explicit selections, never an inferred registration.
    proposed = {}
    if 'IVA' in selected: proposed['condicion_iva'] = 'Responsable inscripto'
    if 'Monotributo' in selected: proposed['condicion_iva'] = 'Monotributo'
    for label in selected:
        tax, obligation, jurisdiction = TAX_OPTIONS[label]
        if tax == 'IIBB':
            proposed.update(iibb_regimen='Convenio Multilateral' if obligation == 'CM03' else 'Local',
                            iibb_jurisdiccion=jurisdiction)
    for field, value in proposed.items():
        if not str(profile.get(field) or '').strip(): profile[field] = value
        elif _key(profile[field]) != _key(value):
            result['conflicts'].append('La inscripción seleccionada contradice ' + field + ' existente. Revisar ficha; no se sobrescribe ni se generan tarjetas incompatibles.')
    result['profile'] = profile
    if same:
        changes={k:v for k,v in profile.items() if str(same[0].get(k) or '') != str(v or '')}
        if changes: result['profile_updates']=dict(id=same[0].get('id'),changes=changes)
        if not same[0].get('id'): result['conflicts'].append('Ficha fiscal existente sin identificador: revisar antes de actualizar.')
    else: result['profile_insert']=profile
    if not any(r.get('cliente') == name for r in clients):
        if client_record is None:
            result['conflicts'].append('Cliente ausente del maestro: confirmá sus datos mínimos para el alta, sin inferir servicios ni accesos.')
        elif str(client_record.get('cliente') or '').strip() != name:
            result['conflicts'].append('Los datos de alta corresponden a otro cliente.')
        else:
            allowed=('cliente','rubro','estado','plan','responsable_am','fecha_inicio','servicio_digital','servicio_consultoria','servicio_contabilidad','notas')
            result['client_insert']={k:v for k,v in client_record.items() if k in allowed}
            result['client_insert']['cliente']=name
    try: rows = load_calendar() if calendar is None else calendar
    except (OSError, ValueError): rows = []
    day = today.isoformat() if hasattr(today, 'isoformat') else str(today or date.today().isoformat())
    current = [t for t in tasks if t.get('cliente') == name]
    for label in selected:
        identity = TAX_OPTIONS[label]
        matches, ambiguous = [], []
        for t in current:
            meta = metadata(t)
            # Partial fiscal metadata is not proof that an older obligation is
            # different. Do not let it bypass the conservative legacy guard.
            if meta:
                incomplete_identity = not all(_identity(meta))
                invalid_period = not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', str(meta.get('periodo') or ''))
                ctx, _ = context(t, [profile], rows)
                if ((incomplete_identity and ctx.get('impuesto') == identity[0])
                        or (_identity(meta) == identity and invalid_period)):
                    ambiguous.append(t)
                    continue
            if meta and _identity(meta) == identity:
                # Any active recurrence in this obligation owns subsequent periods.
                active = str(t.get('estado') or '').casefold() not in ('finalizada','finalizado','cancelada','cancelado','anulada','anulado','archivada','archivado')
                if meta.get('periodo') == period or (active and t.get('recurrente') == 'Sí'):
                    matches.append(t)
            elif is_fiscal(t) and not meta:
                ctx, _ = context(t, [profile], rows)
                if ctx.get('impuesto') == identity[0] or (identity[0] == 'IIBB' and re.search(r'\b(?:iibb|ingresos brutos|cm03|convenio)\b', ' '.join(str(t.get(k) or '') for k in ('tarea','categoria','descripcion')), re.I)):
                    # A legacy same-tax task can be historical or recurring; don't guess.
                    ambiguous.append(t)
        if len(matches) > 1 or ambiguous:
            result['conflicts'].append(label + ': hay tarjetas previas ambiguas o duplicadas; revisar sin regenerarlas.')
            continue
        if matches:
            result['existing'].append(dict(id=matches[0].get('id'), impuesto=label, motivo='Se reutiliza tarjeta o serie existente sin modificarla.'))
            continue
        series = _stable('SER-ONB', name, cuit, *identity)
        task = dict(id=_stable('TAR-ONB', name, cuit, *identity, period), cliente=name,
                    tarea=label, categoria=('Ingresos Brutos' if identity[0] == 'IIBB' else label),
                    responsable_am=responsable, prioridad='Normal', estado='Pendiente', fecha_limite='',
                    descripcion='Inscripción seleccionada en onboarding. Período fiscal: ' + period + '. Verificar liquidación, presentación y pago según corresponda.',
                    comentarios='', fecha_carga=day, creado_por=actor, fecha_actualizacion=day, actualizado_por=actor,
                    checklist='[]', avance=0, recurrente='Sí', frecuencia='Mensual', intervalo=1,
                    serie_id=series, ocurrencia=1, proyecto='Obligaciones fiscales', origen='Onboarding fiscal',
                    id_externo=encode_metadata(dict(zip(('impuesto','obligacion','jurisdiccion'), identity), periodo=period, terminacion=int(cuit[-1]), periodo_fuente='Primer período confirmado en onboarding')),
                    unidad='AM Consultora', orden_manual='', posicion_manual='', archivos_habilitados='Sí')
        resolution = resolve(task, [profile], rows)
        task = apply_resolution(task, resolution)
        if resolution['motivo']:
            result['warnings'].append(label + ': ' + resolution['motivo'] + '. Se crea tarjeta pendiente sin fecha inventada.')
        result['tasks'].append(task)
    # All-or-nothing planner: a conflict is not permission to apply the other pieces.
    if result['conflicts']:
        result['tasks'] = []
        result['profile'] = None
        result['profile_insert'] = None
        result['profile_updates'] = None
        result['client_insert'] = None
    return result
