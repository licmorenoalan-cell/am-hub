"""Fiscal deadlines: explicit periods and official sources, never date arithmetic.

Metadata lives in the existing id_externo field (fiscal:v1:) so deployment needs
no schema migration. Other external IDs are preserved and require manual review.
Only the last CUIT digit is persisted; existing fiscal profiles are read internally.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
import hashlib
import subprocess
import json
import re
from pathlib import Path

PREFIX = 'fiscal:v1:'
PENDING = 'Vencimiento fiscal pendiente'
NORMATIVE_NOTE = 'Vencimiento calculado según normativa vigente; sujeto a futuras prórrogas o días inhábiles'
EVIDENCE_FIELDS = ('semester_end', 'evalwindow', 'evidence_type', 'verificado_el')


def metadata(task):
    value = str(task.get('id_externo') or '')
    if not value.startswith(PREFIX):
        return {}
    try:
        result = json.loads(value[len(PREFIX):])
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def encode_metadata(values):
    allowed = ('impuesto', 'obligacion', 'jurisdiccion', 'periodo', 'terminacion',
               'estado', 'motivo', 'fuente', 'periodo_fuente') + EVIDENCE_FIELDS
    return PREFIX + json.dumps({k: values[k] for k in allowed if k in values}, ensure_ascii=False, sort_keys=True)


def is_fiscal(task):
    words = ' '.join(str(task.get(k) or '') for k in ('categoria', 'tarea', 'descripcion')).casefold()
    return bool(metadata(task) or re.search(
        r'\b(iva|iibb|ingresos brutos|convenio multilateral|cm03|cm05|monotributo|'
        r'recategorizaci[oó]n|aut[oó]nomos?|anticipos?|ganancias|bienes personales|'
        r'tasas? municipales?|impuestos?|fiscal(?:es)?|suss|sicore|sircar|sifere)\b', words))


def load_calendar():
    return json.loads(Path(__file__).with_name('data').joinpath('fiscal_calendar.json').read_text())


def _digit(value):
    value = str(value if value is not None else '')
    return int(value) if re.fullmatch(r'[0-9]', value) else None


def context(task, profiles=(), calendar=None):
    """Resolve explicit metadata first; do not infer a period from an arbitrary due date."""
    result = metadata(task).copy()
    words = ' '.join(str(task.get(k) or '') for k in ('categoria', 'tarea', 'descripcion')).casefold()
    matching = [p for p in profiles if str(p.get('cliente') or '').strip().casefold()
                == str(task.get('cliente') or '').strip().casefold() and task.get('cliente')]
    profile = matching[0] if len(matching) == 1 else {}
    if len(matching) > 1:
        return {}, 'Más de una ficha fiscal para el cliente'
    digits = set()
    if result.get('terminacion') is not None:
        d = _digit(result['terminacion'])
        if d is None:
            return result, 'Terminación de CUIT inválida'
        digits.add(d)
    cuit = re.sub(r'\D', '', str(profile.get('cuit') or ''))
    if len(cuit) == 11:
        digits.add(int(cuit[-1]))
    # Legacy text is only a fallback; no complete identifier is persisted in metadata.
    for cuit in re.findall(r'\b(?:20|23|24|27|30|33)-?\d{8}-?\d\b', words):
        digits.add(int(cuit[-1]))
    if len(digits) > 1:
        return result, 'Terminaciones de CUIT contradictorias'
    if digits:
        result['terminacion'] = digits.pop()
    # A client's IIBB profile must never reclassify their IVA/Monotributo task.
    is_iibb = bool(re.search(r'\b(iibb|ingresos brutos|convenio multilateral|cm03|cm05)\b', words))
    regime = (words + ' ' + (str(profile.get('iibb_regimen') or '') if is_iibb else '')).casefold()
    jurisdiction = str(profile.get('iibb_jurisdiccion') or '').casefold() if is_iibb else ''
    general_local = bool(re.search(r'r[eé]gimen\s+general|local\s+general', regime))
    if not result.get('impuesto'):
        if re.search(r'\b(cm05|anual)\b', words) and ('convenio' in regime or 'cm05' in words):
            result.update(impuesto='IIBB', obligacion='CM05', jurisdiccion='COMARB')
        elif 'convenio multilateral' in regime or re.search(r'\bcm(?:03)?\b', words):
            result.update(impuesto='IIBB', obligacion='CM03', jurisdiccion='COMARB')
        elif is_iibb and ('arba' in regime or 'arba' in jurisdiction):
            result.update(impuesto='IIBB', obligacion='SIMPLIFICADO' if ('simplificado' in regime or 'unificado' in regime) else ('MENSUAL' if general_local else ''), jurisdiccion='BUENOS AIRES')
        elif is_iibb and ('agip' in regime or 'agip' in jurisdiction):
            result.update(impuesto='IIBB', obligacion='SIMPLIFICADO' if ('simplificado' in regime or 'unificado' in regime) else ('MENSUAL' if general_local else ''), jurisdiccion='CABA')
        elif 'recategoriz' in words:
            result.update(impuesto='MONOTRIBUTO', obligacion='RECATEGORIZACION', jurisdiccion='NACIONAL')
        elif re.search(r'\banticipos?\b', words):
            result.update(impuesto='ANTICIPOS', obligacion='', jurisdiccion='NACIONAL')
        else:
            for pattern, tax in ((r'\biva\b', 'IVA'), (r'\baut[oó]nomos?\b', 'AUTONOMOS'),
                                 (r'\bmonotributo\b', 'MONOTRIBUTO')):
                if re.search(pattern, words):
                    result.update(impuesto=tax, obligacion='MENSUAL', jurisdiccion='NACIONAL')
                    break
    if result.get('periodo'):
        result.setdefault('periodo_fuente', 'Configuración fiscal explícita')
    else:
        # Legacy descriptions were copied unchanged by the old recurrence engine.
        # Only first occurrences can establish a period; later ones need reviewed metadata.
        try:
            first_occurrence = int(float(task.get('ocurrencia') or 1)) == 1 and not metadata(task)
        except (ValueError, TypeError):
            first_occurrence = False
        if first_occurrence:
            months = {'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,
                      'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12}
            periods = set(re.findall(r'per[ií]odo(?: fiscal)?\s*[:=]?\s*(\d{4}-\d{2})\b', words))
            for month, year in re.findall(r'per[ií]odo(?: fiscal)?\s*[:=]?\s*([a-z]+)\s+(?:de\s+)?(\d{4})', words):
                if month in months:
                    periods.add(f'{year}-{months[month]:02d}')
            for month, year in re.findall(r'per[ií]odo(?: fiscal)?\s*[:=]?\s*(\d{2})/(\d{4})', words):
                if 1 <= int(month) <= 12:
                    periods.add(f'{year}-{month}')
            if len(periods) == 1:
                result['periodo'] = periods.pop()
                result['periodo_fuente'] = 'Descripción explícita de primera ocurrencia'
            elif len(periods) > 1:
                return result, 'Períodos fiscales contradictorios'
    return result, ''


def _matches(ctx, entry, period=True):
    fields = ['impuesto', 'obligacion', 'jurisdiccion'] + (['periodo'] if period else [])
    return all(ctx.get(k) == entry.get(k) for k in fields) and (ctx.get('terminacion') in entry.get('terminaciones', [])
        or (ctx.get('terminacion') is None and set(entry.get('terminaciones', [])) == set(range(10))))


def valid_entry(entry):
    try:
        date.fromisoformat(entry['vencimiento'])
        return (entry.get('verificado') is True and str(entry.get('fuente', '')).startswith('https://')
                and bool(entry.get('norma')) and bool(entry.get('verificado_el')))
    except (KeyError, TypeError, ValueError):
        return False


def shift_period(period, months):
    if re.fullmatch(r'\d{4}-H[12]', str(period)):
        if months % 6:
            raise ValueError('Un semestre requiere intervalos de seis meses')
        year, half = int(period[:4]), int(period[-1])
        total = year * 2 + half - 1 + months // 6
        return f'{total // 2:04d}-H{total % 2 + 1}'
    if re.fullmatch(r'\d{4}', str(period)) and months % 12 == 0:
        return str(int(period) + months // 12)
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', str(period)):
        raise ValueError('Período mensual inválido')
    year, month = map(int, period.split('-'))
    total = year * 12 + month - 1 + months
    return f'{total // 12:04d}-{total % 12 + 1:02d}'


def resolve(task, profiles=(), calendar=None, next_period=False):
    rows = load_calendar() if calendar is None else calendar
    ctx, reason = context(task, profiles, rows)
    if not reason:
        missing = [k for k in ('impuesto', 'obligacion', 'jurisdiccion', 'periodo') if not ctx.get(k)]
        if ctx.get('terminacion') is None and ctx.get('impuesto') != 'MONOTRIBUTO':
            missing.append('terminación de CUIT')
        if missing:
            reason = 'Falta ' + ', '.join(missing)
    if next_period and ctx.get('periodo'):
        frequency = str(task.get('frecuencia') or '')
        try:
            raw_interval = float(task.get('intervalo') or 1)
            if raw_interval < 1 or not raw_interval.is_integer():
                raise ValueError()
            months = {'Mensual': 1, 'Semestral': 6, 'Anual': 12}[frequency] * int(raw_interval)
            previous_period = ctx['periodo']
            ctx['periodo'] = shift_period(previous_period, months)
            ctx['periodo_fuente'] = 'Siguiente período de ' + previous_period
        except (ValueError, TypeError, KeyError, OverflowError):
            reason = 'Frecuencia o período fiscal no configurado para esta obligación'
    matches = [r for r in rows if _matches(ctx, r) and valid_entry(r)] if not reason else []
    if len(matches) != 1 and not reason:
        reason = 'Calendario oficial no disponible' if not matches else 'Calendario oficial ambiguo'
    # Evidence belongs to one exact period; never inherit a prior semester's window.
    for field in EVIDENCE_FIELDS:
        ctx.pop(field, None)
    if not reason:
        ctx.update({k: matches[0][k] for k in EVIDENCE_FIELDS if k in matches[0]})
    ctx.update(estado='pendiente' if reason else 'verificado', motivo=reason,
               fuente='' if reason else matches[0]['fuente'])
    return {'fecha': '' if reason else matches[0]['vencimiento'], 'contexto': ctx, 'motivo': reason}


def apply_resolution(task, result, preserve_legacy_date=False):
    task = dict(task)
    external = str(task.get('id_externo') or '')
    if external and not external.startswith(PREFIX):
        result = dict(result, fecha='', motivo='Identificador externo existente: requiere configuración fiscal')
    else:
        task['id_externo'] = encode_metadata(result['contexto'])
    task['fecha_limite'] = task.get('fecha_limite', '') if preserve_legacy_date and result['motivo'] else result['fecha']
    task['comentarios'] = '\n'.join(line for line in str(task.get('comentarios') or '').splitlines()
                                    if not line.startswith(PENDING))
    if result['motivo']:
        task['comentarios'] = (task['comentarios'] + '\n' + PENDING + ': ' + result['motivo']).strip()
    return task


def pending_label(task):
    fiscal = metadata(task)
    if ((task.get('recurrente') == 'Sí' or fiscal) and is_fiscal(task)
            and (not task.get('fecha_limite') or fiscal.get('estado') == 'pendiente'
                 or PENDING in str(task.get('comentarios') or ''))):
        previous = str(task.get('fecha_limite') or '')
        reason = str(fiscal.get('motivo') or '')
        if not reason:
            notes = [line for line in str(task.get('comentarios') or '').splitlines()
                     if line.startswith(PENDING + ': ')]
            reason = notes[-1][len(PENDING) + 2:] if notes else ''
        if reason.startswith('Calendario'):
            label = 'Calendario fiscal pendiente: ' + reason
        elif reason:
            label = 'Datos fiscales por revisar: ' + reason
        else:
            label = PENDING
        return label + (f' · fecha previa sin verificar: {previous}' if previous else '')
    return ''


def fiscal_period_label(task):
    fiscal = metadata(task)
    period = fiscal.get('periodo')
    label = f'Período fiscal: {period}' if period else ''
    if fiscal.get('evidence_type') == 'norma_vigente_fecha_derivada':
        label += ' · ' + NORMATIVE_NOTE
        label += ' · Revisar categoría; presentar solo si corresponde'
    return label


def suggested_period(task, profiles=(), calendar=None):
    """A date match is a suggestion, never confirmation of historical intent."""
    ctx, _ = context(task, profiles)
    rows = load_calendar() if calendar is None else calendar
    candidates = {r['periodo'] for r in rows if _matches(ctx, r, period=False)
                  and r.get('vencimiento') == task.get('fecha_limite') and valid_entry(r)}
    return next(iter(candidates)) if len(candidates) == 1 else ''


def validate_completion(task, profiles=()):
    if not (metadata(task) or (is_fiscal(task) and task.get('recurrente') == 'Sí')):
        return
    current = resolve(task, profiles)
    if current['motivo'] or current['fecha'] != task.get('fecha_limite'):
        raise ValueError('Vencimiento fiscal pendiente: fecha no validada contra el calendario oficial.')


@lru_cache(maxsize=2)
def announce_release(entrypoint):
    """Public code provenance in deployment logs; never reads configuration or data."""
    root = Path(__file__).resolve().parent
    try:
        revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root,
                                  capture_output=True, text=True, timeout=3, check=True).stdout.strip()
        if not re.fullmatch(r'[a-f0-9]{40}', revision):
            revision = 'unknown'
    except (OSError, subprocess.SubprocessError):
        revision = 'unknown'
    digest = hashlib.sha256()
    for name in ('am_hub_tax_calendar.py', 'am_hub_tasks.py', 'data/fiscal_calendar.json', entrypoint):
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    result = {'entrypoint': entrypoint, 'revision': revision,
              'engine': 'fiscal-v1', 'fingerprint': digest.hexdigest(),
              'calendar_entries': len(load_calendar())}
    print('AM_HUB_FISCAL_RELEASE ' + json.dumps(result, sort_keys=True), flush=True)
    return result
