"""Admin-only fiscal-period setup for an existing legacy IVA reminder."""
from hashlib import sha256
import json
import re

from sqlalchemy import text

from am_hub_tasks import actualizar_estado_tarea_en_conexion, construir_siguiente_ocurrencia
from am_hub_tax_calendar import (apply_resolution, encode_metadata, metadata,
                                 pending_label, resolve, validate_completion)


def eligible(row):
    return (str(row.get('categoria') or '').strip().casefold() == 'iva'
            and row.get('estado') in {'A priorizar', 'Pendiente', 'En curso', 'En revisión'}
            and row.get('recurrente') == 'Sí' and row.get('frecuencia') == 'Mensual'
            and bool(row.get('serie_id')) and not metadata(row).get('periodo')
            and bool(row.get('cliente')))


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def _digits(value):
    return re.sub(r'\D', '', str(value or ''))


def _occurrence(row):
    value = float(row.get('ocurrencia') or 0)
    if value < 1 or not value.is_integer():
        raise ValueError('La serie de la tarjeta no es válida.')
    return int(value)


def _successors(rows, row, prepared):
    month = metadata(prepared).get('periodo')
    expected_n = _occurrence(row) + 1
    same_occurrence = [r for r in rows if r.get('serie_id') == row['serie_id'] and _occurrence(r) == expected_n]
    same_period = [r for r in rows if r['id'] != row['id'] and (
        metadata(r).get('periodo') == month or
        (not metadata(r).get('periodo') and r.get('fecha_limite') == prepared['fecha_limite']))]
    if (len(same_occurrence) > 1 or any(r not in same_occurrence for r in same_period)
        or any(metadata(r).get('periodo') != month or r.get('fecha_limite') != prepared['fecha_limite']
               or metadata(r).get('impuesto') != 'IVA'
               or metadata(r).get('obligacion') != 'MENSUAL'
               or metadata(r).get('jurisdiccion') != 'NACIONAL'
               or (bool(prepared['fecha_limite']) and bool(pending_label(r)))
               or r.get('estado') == 'Finalizada'
               or metadata(r).get('terminacion') != metadata(prepared).get('terminacion')
               or r.get('cliente') != row['cliente'] or r.get('recurrente') != 'Sí'
               or r.get('frecuencia') != 'Mensual' or float(r.get('intervalo') or 0) != 1
               for r in same_occurrence)):
        raise ValueError('Hay otra tarjeta que puede ser del próximo período. No se creó ningún duplicado.')
    return same_occurrence


def plan(row, rows, profiles, period):
    if not eligible(row) or float(row.get('intervalo') or 0) != 1:
        raise ValueError('Esta tarjeta no es una recurrencia mensual de IVA pendiente de identificar.')
    if not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', period):
        raise ValueError('Indicá el período mensual de este recordatorio (AAAA-MM).')
    cuit = _digits(profiles[0].get('cuit')) if len(profiles) == 1 else ''
    if len(cuit) != 11:
        raise ValueError('Falta una ficha fiscal única con el CUIT del cliente. No se cambió la tarjeta.')
    old = metadata(row)
    if (row.get('id_externo') and not old) or old.get('modo_fecha') or old.get('dia_control'):
        raise ValueError('La tarjeta tiene una vinculación previa que se debe revisar por separado.')
    context = dict(impuesto='IVA', obligacion='MENSUAL', jurisdiccion='NACIONAL',
                   periodo=period, terminacion=int(cuit[-1]))
    if any(old.get(k) not in (None, '', v) for k, v in context.items()):
        raise ValueError('El período o el CUIT de la ficha contradice los datos guardados de la tarjeta.')
    for related in rows:
        if related['id'] == row['id']:
            continue
        if metadata(related).get('periodo') == period or related.get('fecha_limite') == row.get('fecha_limite'):
            raise ValueError('Hay otra tarjeta para el mismo período. Revisala antes de continuar.')
        prior = metadata(related).get('periodo')
        if related.get('serie_id') == row['serie_id'] and prior and (
                (_occurrence(related) < _occurrence(row) and prior >= period) or
                (_occurrence(related) > _occurrence(row) and prior <= period)):
            raise ValueError('El período no respeta el orden de las tarjetas de esa serie.')
    context['periodo_fuente'] = 'Período del recordatorio confirmado en AM Hub'
    candidate = dict(row, id_externo=encode_metadata(context))
    fiscal = resolve(candidate, profiles)
    if fiscal['motivo'] or fiscal['fecha'] != row.get('fecha_limite'):
        raise ValueError('La fecha de la tarjeta no coincide con el calendario oficial para ese CUIT y período.')
    candidate = apply_resolution(candidate, fiscal)
    validate_completion(candidate, profiles)
    successor = construir_siguiente_ocurrencia(candidate, 'Simulación', nueva_id='DRY-RUN', perfiles=profiles)
    existing = _successors(rows, row, successor)
    ready = {key: candidate[key] for key in ('id_externo','comentarios')}
    return {
        'id': str(row['id']), 'cliente': row['cliente'], 'periodo': period,
        'fecha': fiscal['fecha'], 'proximo_periodo': metadata(successor)['periodo'],
        'proxima_fecha': successor['fecha_limite'], 'reutiliza': bool(existing),
        'revision': _digest([row, rows, profiles, period]),
    }, ready, successor


def inspect_or_apply(engine, role, user, task_id, period, revision=None):
    if role != 'admin_general' or not user:
        raise PermissionError('Solo administración general puede validar el cierre fiscal.')
    apply = revision is not None
    lock = ' FOR UPDATE' if apply else ''
    with engine.begin() as conn:
        selected = conn.execute(text('SELECT * FROM tareas WHERE id=:id' + lock),
                                {'id': str(task_id)}).mappings().one_or_none()
        if selected is None:
            raise ValueError('La tarjeta no está disponible.')
        row = dict(selected)
        targets = conn.execute(text(
            'SELECT * FROM tareas WHERE serie_id=:serie OR '
            "(lower(trim(cliente)) = lower(trim(:cliente)) AND lower(trim(categoria))='iva')"
            ' ORDER BY id' + lock), {'serie': row.get('serie_id'), 'cliente': row.get('cliente')}).mappings()
        rows = [dict(x) for x in targets]
        profiles = [dict(x) for x in conn.execute(text(
            'SELECT cliente,cuit,iibb_regimen,iibb_jurisdiccion FROM fiscal_clientes '
            'WHERE lower(trim(cliente))=lower(trim(:cliente)) ORDER BY cliente' +
            (' FOR SHARE' if apply else '')), {'cliente': row.get('cliente')}).mappings()]
        view, changes, projected = plan(row, rows, profiles, period)
        if not apply:
            return view
        if view['revision'] != revision:
            raise ValueError('La tarjeta cambió después de la revisión. Volvé a revisar antes de cerrar.')
        conn.execute(text('UPDATE tareas SET id_externo=:id_externo, comentarios=:comentarios WHERE id=:card_id'),
                     dict(changes, card_id=str(task_id)))
        result = actualizar_estado_tarea_en_conexion(conn, task_id, 'Finalizada', user)
        saved = [dict(x) for x in conn.execute(text('SELECT * FROM tareas WHERE serie_id=:serie ORDER BY id'),
                                              {'serie': row['serie_id']}).mappings()]
        current = [r for r in saved if str(r['id']) == str(task_id)]
        next_rows = _successors(saved, row, projected)
        if len(current) != 1 or current[0]['estado'] != 'Finalizada' or len(next_rows) != 1:
            raise ValueError('No se verificó el cierre o la próxima tarjeta. Se deshicieron los cambios.')
        return dict(view, siguiente_id=str(next_rows[0]['id']), nueva=bool(result['generada']))
