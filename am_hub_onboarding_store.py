"""Transactional, additive persistence for reviewed fiscal-onboarding plans.

No credentials, users, permissions, existing tasks or whole-table replacement.
Call snapshot_onboarding for a preview, then apply_plan with its fingerprint.
"""
import hashlib
import json
import re
import unicodedata
from sqlalchemy import text

TABLES = {'clients': 'clientes', 'profiles': 'fiscal_clientes', 'tasks': 'tareas'}
CLIENT_FIELDS = set('cliente rubro estado plan responsable_am fecha_inicio servicio_digital servicio_consultoria servicio_contabilidad notas'.split())
PROFILE_FIELDS = set('id cliente cuit razon_social condicion_iva iibb_regimen iibb_jurisdiccion iibb_inscripcion actividad_principal actividades alicuota_iibb email_destinatarios mes_cierre_ejercicio observaciones fecha_actualizacion actualizado_por'.split())
TASK_FIELDS = set('id unidad proyecto cliente tarea descripcion responsable_am prioridad estado fecha_limite checklist avance recurrente frecuencia intervalo serie_id ocurrencia comentarios origen id_externo categoria fecha_carga creado_por fecha_actualizacion actualizado_por archivos_habilitados posicion_manual orden_manual'.split())
ALLOWED = {'clientes': CLIENT_FIELDS, 'fiscal_clientes': PROFILE_FIELDS, 'tareas': TASK_FIELDS}
STAMP_FIELDS = {'fecha_actualizacion', 'actualizado_por'}

class OnboardingConflict(ValueError):
    pass


def _value(value):
    return '' if value is None else str(value)


def _name(value):
    return ' '.join(unicodedata.normalize('NFKC', _value(value)).strip().casefold().split())


def _cuit(value):
    return re.sub(r'\D', '', _value(value))


def _valid_cuit(value):
    # Use the same strict format/check-digit rule as the reviewed planner.
    from am_hub_fiscal_onboarding import validate_cuit
    try:
        validate_cuit(value)
        return True
    except (TypeError, ValueError):
        return False


def snapshot_fingerprint(snapshot):
    data = {}
    for key in TABLES:
        rows = [{k: _value(v) for k,v in r.items()} for r in snapshot.get(key, [])]
        data[key] = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _read_snapshot(conn):
    snapshot = {key: [dict(r) for r in conn.execute(text('SELECT * FROM "'+table+'"')).mappings()] for key,table in TABLES.items()}
    snapshot['fingerprint'] = snapshot_fingerprint(snapshot)
    return snapshot


def snapshot_onboarding(engine):
    """Read only. Does not bootstrap schemas or write caches."""
    with engine.connect() as conn:
        if engine.dialect.name == 'postgresql':
            conn.execute(text('SET TRANSACTION READ ONLY'))
            conn.execute(text('SET LOCAL statement_timeout = 15000'))
        return _read_snapshot(conn)


def _clean(record, table):
    if not isinstance(record, dict) or set(record) - ALLOWED[table]:
        raise OnboardingConflict('El plan contiene campos no permitidos para '+table+'.')
    return {key: value for key,value in record.items() if value is not None}


def _matches(record, requested):
    return all(_value(record.get(k)) == _value(v) for k,v in requested.items())


def _validated(plan, client_insert):
    if plan.get('conflicts'):
        raise OnboardingConflict('Resolvé los conflictos de la vista previa antes de aplicar.')
    profile = _clean(plan.get('profile') or {}, 'fiscal_clientes')
    client = _value(profile.get('cliente')).strip()
    if not client or not profile.get('id') or not _valid_cuit(profile.get('cuit')):
        raise OnboardingConflict('El plan requiere cliente, ID de ficha y CUIT válido verificados.')
    profile['cuit'] = _cuit(profile['cuit'])
    tasks = [_clean(t, 'tareas') for t in plan.get('tasks', [])]
    if any(t.get('cliente') != client or not t.get('id') for t in tasks):
        raise OnboardingConflict('Todas las tarjetas deben pertenecer al mismo cliente y tener ID.')
    if len({t['id'] for t in tasks}) != len(tasks):
        raise OnboardingConflict('El plan contiene tarjetas duplicadas.')
    proposed_client = _clean(client_insert, 'clientes') if client_insert is not None else None
    if proposed_client is not None and proposed_client.get('cliente') != client:
        raise OnboardingConflict('La ficha y el alta comercial no corresponden al mismo cliente.')
    return client, profile, tasks, proposed_client


def _changes(snapshot, profile, tasks, client_insert):
    """Validate identities first; return only additive, per-row mutations."""
    client = profile['cliente']
    normalized = _name(client)
    masters = [r for r in snapshot['clients'] if _name(r.get('cliente')) == normalized]
    if len(masters) > 1 or any(r.get('cliente') != client for r in masters):
        raise OnboardingConflict('Nombre existente ambiguo o con otra escritura; no se renombra ni fusiona.')
    profiles = [r for r in snapshot['profiles'] if _name(r.get('cliente')) == normalized]
    if len(profiles) > 1 or any(r.get('cliente') != client for r in profiles):
        raise OnboardingConflict('Hay fichas fiscales duplicadas o con otra escritura.')
    if any(_cuit(r.get('cuit')) == profile['cuit'] and r.get('cliente') != client for r in snapshot['profiles']):
        raise OnboardingConflict('El CUIT ya figura en otro cliente; requiere conciliación explícita.')
    if any(r.get('id') == profile['id'] and r.get('cliente') != client for r in snapshot['profiles']):
        raise OnboardingConflict('El ID de ficha pertenece a otro cliente.')
    changes = []
    if not masters:
        if client_insert is None:
            raise OnboardingConflict('El cliente no existe; falta aprobar sus datos mínimos de alta.')
        changes.append(('insert', 'clientes', client, dict(client_insert), {}))
    elif client_insert is not None and not _matches(masters[0], client_insert):
        raise OnboardingConflict('El cliente existente no coincide con el alta propuesta; no se sobrescribe.')
    if not profiles:
        changes.append(('insert', 'fiscal_clientes', profile['id'], profile, {}))
    else:
        previous = profiles[0]
        if previous.get('id') != profile['id']:
            raise OnboardingConflict('Cambió la identidad de la ficha fiscal; repetí la vista previa.')
        updates = {}
        for field,value in profile.items():
            if field in ('id', 'cliente') or field in STAMP_FIELDS or not _value(value).strip():
                continue
            old = previous.get(field)
            equal = _cuit(old) == _cuit(value) if field == 'cuit' else _value(old) == _value(value)
            if _value(old).strip() and not equal:
                raise OnboardingConflict('La ficha ya tiene un valor distinto en '+field+'; no se sobrescribe.')
            if not _value(old).strip():
                updates[field] = value
        if updates:
            updates.update({k:profile[k] for k in STAMP_FIELDS if k in profile})
            changes.append(('update', 'fiscal_clientes', previous['id'], updates, {k:previous.get(k) for k in updates}))
    for task in tasks:
        existing = [r for r in snapshot['tasks'] if r.get('id') == task['id']]
        if len(existing) > 1 or (existing and not _matches(existing[0], task)):
            raise OnboardingConflict('ID de tarjeta existente con otros datos; no se modifica.')
        if not existing:
            changes.append(('insert', 'tareas', task['id'], task, {}))
    return changes


def _apply_locked(conn, plan, expected_fingerprint, client_insert=None):
    _, profile, tasks, client_insert = _validated(plan, client_insert)
    snapshot = _read_snapshot(conn)
    changes = _changes(snapshot, profile, tasks, client_insert)
    # Exact replay is a no-op, even after this operation changed the snapshot.
    if not changes:
        return {'changed': False, 'changes': [], 'fingerprint': snapshot['fingerprint']}
    if not expected_fingerprint or expected_fingerprint != snapshot['fingerprint']:
        raise OnboardingConflict('La base cambió desde la vista previa. Revisá el plan actualizado antes de aplicar.')
    audit = []
    for operation,table,key,values,before in changes:
        columns = list(values)
        if operation == 'insert':
            sql = 'INSERT INTO "'+table+'" ('+', '.join('"'+c+'"' for c in columns)+') VALUES ('+', '.join(':'+c for c in columns)+')'
            conn.execute(text(sql), values)
        else:
            sql = 'UPDATE "'+table+'" SET '+', '.join('"'+c+'" = :'+c for c in columns)+' WHERE "id" = :_key'
            result = conn.execute(text(sql), dict(values, _key=key))
            if result.rowcount != 1:
                raise OnboardingConflict('La ficha cambió durante el guardado; se anuló toda la operación.')
        audit.append({'operation': operation, 'table': table, 'key': key, 'before': before, 'after': dict(values)})
    return {'changed': True, 'changes': audit, 'fingerprint': _read_snapshot(conn)['fingerprint']}


def apply_plan(engine, plan, expected_fingerprint, client_insert=None):
    """Atomically apply an approved preview. PostgreSQL only; never modify tasks.

    Table locks also serialize against older app writers not using advisory locks.
    Existing rows are only filled where blank; no deletes, renames or access changes.
    Any error rolls back all inserts/updates. Returned before/after is the audit.
    """
    if engine.dialect.name != 'postgresql':
        raise OnboardingConflict('La conciliación segura requiere PostgreSQL; no se escribieron archivos locales.')
    # A calendar deployment can change while the database snapshot stays identical.
    # Re-resolve every newly proposed card before inserting an obsolete deadline.
    from am_hub_tax_calendar import resolve, metadata
    profile = plan.get('profile') or {}
    for task in plan.get('tasks', []):
        result = resolve(task, [profile])
        if (_value(task.get('fecha_limite')) != _value(result.get('fecha'))
                or metadata(task).get('estado') != result.get('contexto', {}).get('estado')
                or metadata(task).get('fuente') != result.get('contexto', {}).get('fuente')):
            raise OnboardingConflict('Cambió el calendario fiscal desde la vista previa; revisá nuevamente las fechas.')
    with engine.begin() as conn:
        conn.execute(text('SET LOCAL lock_timeout = 5000'))
        conn.execute(text('SET LOCAL statement_timeout = 15000'))
        conn.execute(text('LOCK TABLE "clientes", "fiscal_clientes", "tareas" IN SHARE ROW EXCLUSIVE MODE'))
        return _apply_locked(conn, plan, expected_fingerprint, client_insert)


def _task_identity(task):
    """Use explicit fiscal metadata; return None rather than guess a period."""
    raw = _value(task.get('id_externo'))
    try:
        meta = json.loads(raw[len('fiscal:v1:'):]) if raw.startswith('fiscal:v1:') else {}
    except (TypeError, ValueError):
        return None
    if not isinstance(meta, dict):
        return None
    fields = ('impuesto', 'obligacion', 'jurisdiccion', 'periodo')
    return tuple(meta.get(k) for k in fields) if all(meta.get(k) for k in fields) else None


def _link_locked(conn, source_client, target_client, cuit, expected_fingerprint,
                 evidence, actor, task_ids, razon_social):
    source_client, target_client = _value(source_client).strip(), _value(target_client).strip()
    raw_cuit = cuit
    cuit = _cuit(cuit)
    if not source_client or not target_client or _name(source_client) == _name(target_client):
        raise OnboardingConflict('La vinculación requiere alias y cliente distintos explícitos.')
    if not _valid_cuit(raw_cuit) or not _value(evidence).strip() or not _value(actor).strip() or not _value(razon_social).strip():
        raise OnboardingConflict('Faltan CUIT válido, razón social, evidencia o responsable de la vinculación.')
    if not isinstance(task_ids, (list,tuple)) or not task_ids or len(set(task_ids)) != len(task_ids) or any(not _value(i) for i in task_ids):
        raise OnboardingConflict('Indicá los IDs únicos de todas las tarjetas a vincular.')
    snapshot = _read_snapshot(conn)
    if any(_name(r.get('cliente')) == _name(source_client) for r in snapshot['clients']):
        raise OnboardingConflict('El alias ya es un cliente comercial; no se fusionan entidades.')
    masters = [r for r in snapshot['clients'] if _name(r.get('cliente')) == _name(target_client)]
    profiles = [r for r in snapshot['profiles'] if _name(r.get('cliente')) == _name(target_client)]
    if len(masters) != 1 or masters[0].get('cliente') != target_client or len(profiles) != 1 or profiles[0].get('cliente') != target_client:
        raise OnboardingConflict('El destino requiere cliente y ficha fiscal únicos, con nombre exacto.')
    profile = profiles[0]
    if _value(profile.get('cuit')).strip() and _cuit(profile['cuit']) != cuit:
        raise OnboardingConflict('El CUIT de destino contradice la evidencia.')
    if any(r.get('id') != profile.get('id') and _cuit(r.get('cuit')) == cuit for r in snapshot['profiles']):
        raise OnboardingConflict('El CUIT está vinculado a otra ficha fiscal.')
    if any(_name(r.get('cliente')) == _name(source_client) for r in snapshot['profiles']):
        raise OnboardingConflict('El alias tiene ficha fiscal propia; requiere conciliación manual.')
    selected = [r for r in snapshot['tasks'] if r.get('id') in task_ids]
    if len(selected) != len(task_ids) or any(r.get('cliente') not in (source_client,target_client) for r in selected):
        raise OnboardingConflict('Alguna tarjeta no existe o pertenece a otro cliente.')
    remaining_source = [r for r in snapshot['tasks'] if r.get('cliente') == source_client and r.get('id') not in task_ids]
    if remaining_source:
        raise OnboardingConflict('Hay tarjetas adicionales del alias fuera de la vista previa; revisá el alcance.')
    targets = [r for r in snapshot['tasks'] if r.get('cliente') == target_client and r.get('id') not in task_ids]
    for source in selected:
        identity = _task_identity(source)
        for target in targets:
            target_identity = _task_identity(target)
            if identity and identity == target_identity:
                raise OnboardingConflict('Ya existe una tarjeta destino de la misma obligación y período.')
            # Incomplete metadata cannot demonstrate a safe merge of parallel task sets.
            if identity is None or target_identity is None:
                raise OnboardingConflict('Hay tarjetas destino sin identidad fiscal comparable; revisá posibles duplicados.')
    changes = []
    fields = {}
    if not _value(profile.get('cuit')).strip(): fields['cuit'] = cuit
    if not _value(profile.get('razon_social')).strip(): fields['razon_social'] = razon_social
    elif _name(profile['razon_social']) != _name(razon_social):
        raise OnboardingConflict('La razón social existente difiere del documento; no se sobrescribe.')
    if fields:
        changes.append(('fiscal_clientes', profile['id'], fields, {k:profile.get(k) for k in fields}))
    changes += [('tareas', r['id'], {'cliente':target_client}, {'cliente':source_client}) for r in selected if r.get('cliente') == source_client]
    if not changes:
        return {'changed':False,'changes':[], 'fingerprint':snapshot['fingerprint'], 'evidence':evidence,'actor':actor}
    if not expected_fingerprint or snapshot['fingerprint'] != expected_fingerprint:
        raise OnboardingConflict('La base cambió desde la revisión de la vinculación; no se aplicó ningún cambio.')
    audit=[]
    for table,key,values,before in changes:
        sql = 'UPDATE "'+table+'" SET '+', '.join('"'+k+'" = :'+k for k in values)+' WHERE "id" = :_key'
        result=conn.execute(text(sql),dict(values,_key=key))
        if result.rowcount != 1:
            raise OnboardingConflict('Cambió una fila durante la vinculación; operación anulada.')
        audit.append({'operation':'update','table':table,'key':key,'before':before,'after':dict(values)})
    return {'changed':True,'changes':audit,'fingerprint':_read_snapshot(conn)['fingerprint'],'evidence':evidence,'actor':actor}


def apply_verified_link(engine, source_client, target_client, cuit, expected_fingerprint,
                        evidence, actor, task_ids, razon_social):
    """Apply one explicitly verified alias linkage; never infer relationships.

    Caller must retain returned audit with evidence for reversal. Only profile blank
    CUIT/name and selected task.cliente change. No roles, dates or recurrence changes.
    """
    if engine.dialect.name != 'postgresql':
        raise OnboardingConflict('La vinculación segura requiere PostgreSQL; no se escribieron archivos locales.')
    with engine.begin() as conn:
        conn.execute(text('SET LOCAL lock_timeout = 5000'))
        conn.execute(text('SET LOCAL statement_timeout = 15000'))
        conn.execute(text('LOCK TABLE "clientes", "fiscal_clientes", "tareas" IN SHARE ROW EXCLUSIVE MODE'))
        return _link_locked(conn,source_client,target_client,cuit,expected_fingerprint,
                            evidence,actor,task_ids,razon_social)
