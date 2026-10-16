"""Shared fleet sandbox, isolated from accounting tables and scoped by AMHub login."""
import calendar
import datetime as dt
import json
import math
from pathlib import Path
from sqlalchemy import text

CLIENT = 'SMPA / KM146'
ASSETS = Path(__file__).parent / 'components' / 'somos_compa'


def authorized(session, allowed):
    if not session.get('logged_in') or not session.get('username'):
        return False
    role = session.get('role')
    return (role in ('admin', 'admin_general') or
            role == 'cliente' and session.get('cliente') == CLIENT or
            role == 'equipo' and CLIENT in allowed and session.get('cliente_equipo_activo') == CLIENT)


def validate(payload):
    raw = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    if len(raw.encode()) > 5_000_000 or not isinstance(payload, dict) or payload.get('version') != 2:
        raise ValueError('Base incompatible o demasiado grande (máximo 5 MB).')
    def date(value, optional=False):
        if optional and value == '':
            return
        if not isinstance(value, str) or dt.date.fromisoformat(value).isoformat() != value:
            raise ValueError('Fecha inválida.')
    def number(value, minimum=0):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum or abs(value) > 1e15:
            raise ValueError('Importe o cantidad inválida.')
    def strings(record):
        if not isinstance(record, dict) or any(not isinstance(v, (str, int, float)) or isinstance(v, bool) for v in record.values()):
            raise ValueError('Registro inválido.')
        if any(len(v) > 5000 for v in record.values() if isinstance(v, str)):
            raise ValueError('Texto demasiado extenso.')
    for key in ('vehicles', 'movements', 'activity', 'events'):
        rows = payload[key]
        if not isinstance(rows, list) or len(rows) > 15000:
            raise ValueError('Demasiados registros.')
        ids = set()
        for r in rows:
            strings(r)
            if not isinstance(r.get('id'), str) or not r['id'] or r['id'] in ids:
                raise ValueError('Identificador duplicado o inválido.')
            ids.add(r['id'])
    companies = ('SMPA SAS', 'KM146 SAS')
    vehicles = {v['id'] for v in payload['vehicles']}
    plates = set()
    for v in payload['vehicles']:
        plate = v['plate'].strip().lower()
        if not plate or plate in plates or not v['model'] or v['owner'] not in companies:
            raise ValueError('Vehículo inválido o duplicado.')
        plates.add(plate)
        number(v['rent'])
    for m in payload['movements']:
        date(m['date']); date(m['due'], True); date(m['paidDate'], True)
        number(m['amount']); number(m['paid'])
        if (m['amount'] <= 0 or m['paid'] > m['amount'] or m['paid'] and not m['paidDate'] or
                m['company'] not in companies or m['type'] not in ('income','expense','deposit','refund','funding','repayment','transfer') or
                m['vehicle'] and m['vehicle'] not in vehicles or not m['description'].strip()):
            raise ValueError('Movimiento inválido.')
        if m['type'] == 'transfer' and (m['target'] not in companies or m['target'] == m['company']):
            raise ValueError('Destino de transferencia inválido.')
    periods = set()
    for a in payload['activity']:
        date(a['month'] + '-01')
        for k in ('days','down','km','trips','hours'):
            number(a[k])
        pair = (a['vehicle'], a['month'])
        if pair in periods or a['vehicle'] not in vehicles or a['days'] + a['down'] > calendar.monthrange(*map(int, a['month'].split('-')))[1]:
            raise ValueError('Actividad mensual inválida o duplicada.')
        periods.add(pair)
    for e in payload['events']:
        date(e['date']); date(e['next'], True); number(e['estimate'])
        if e['vehicle'] not in vehicles:
            raise ValueError('Vehículo de incidencia inválido.')
    date(payload['opening']['date'])
    for k in ('smpa','km','guarantee'):
        number(payload['opening'][k], -1e15 if k != 'guarantee' else 0)
    return raw


def initialize(engine):
    seed = json.loads((ASSETS / 'seed.json').read_text())
    raw = validate(seed)
    with engine.begin() as c:
        c.execute(text('CREATE TABLE IF NOT EXISTS fleet_sandbox (client TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL, updated TEXT NOT NULL, actor TEXT NOT NULL)'))
        c.execute(text('CREATE TABLE IF NOT EXISTS fleet_sandbox_history (client TEXT NOT NULL, revision INTEGER NOT NULL, request TEXT NOT NULL, payload TEXT NOT NULL, updated TEXT NOT NULL, actor TEXT NOT NULL, PRIMARY KEY(client, revision), UNIQUE(client, request))'))
        c.execute(text('INSERT INTO fleet_sandbox (client,revision,payload,updated,actor) VALUES (:client,0,:payload,:updated,:actor) ON CONFLICT(client) DO NOTHING'), dict(client=CLIENT,payload=raw,updated=dt.datetime.now(dt.timezone.utc).isoformat(),actor='initial-demo'))


def load(engine):
    with engine.connect() as c:
        row = dict(c.execute(text('SELECT * FROM fleet_sandbox WHERE client=:client'), {'client': CLIENT}).mappings().one())
    row['payload'] = json.loads(row['payload'])
    return row


def save(engine, session, allowed, request):
    if not authorized(session, allowed):
        raise PermissionError('Acceso no autorizado.')
    rid = request.get('request')
    revision = request.get('revision')
    if not isinstance(rid, str) or not 1 <= len(rid) <= 100 or type(revision) is not int or revision < 0:
        raise ValueError('Solicitud inválida.')
    raw = validate(request['payload'])
    params = dict(client=CLIENT, revision=revision, payload=raw, actor=str(session['username']), updated=dt.datetime.now(dt.timezone.utc).isoformat(), request=rid)
    with engine.begin() as c:
        if c.execute(text('SELECT 1 FROM fleet_sandbox_history WHERE client=:client AND request=:request'),params).first():
            return
        result = c.execute(text('UPDATE fleet_sandbox SET revision=revision+1,payload=:payload,actor=:actor,updated=:updated WHERE client=:client AND revision=:revision'), params)
        if result.rowcount != 1:
            raise ValueError('Otra persona guardó cambios. Descargá tu propuesta y cargá la última versión antes de volver a editar.')
        params['revision'] += 1
        c.execute(text('INSERT INTO fleet_sandbox_history (client,revision,request,payload,updated,actor) VALUES (:client,:revision,:request,:payload,:updated,:actor)'), params)


def render_fleet(engine, session, allowed):
    import streamlit as st
    import streamlit.components.v1 as components
    if not authorized(session, allowed):
        st.error('No tenés acceso al tablero de este cliente.')
        return
    if engine is None:
        st.error('El tablero compartido requiere la base de datos de AMHub.')
        return
    st.title('Tablero gerencial · Somos Compa')
    st.caption('SMPA / KM146 · Entorno de pruebas compartido. Las cargas no modifican la contabilidad de AMHub.')
    try:
        initialize(engine)
        if st.button('Actualizar datos compartidos'):
            session['fleet_frame'] = session.get('fleet_frame', 0) + 1
            session.pop('fleet_ack', None)
        row = load(engine)
        st.caption(f"Versión {row['revision']} · Último guardado: {row['updated'][:19].replace('T',' ')} UTC · {row['actor']}")
        component = components.declare_component('somos_compa_shared', path=str(ASSETS))
        request = component(payload=row['payload'], revision=row['revision'], ack=session.get('fleet_ack'), key='fleet_' + str(session.get('fleet_frame', 0)), default=None)
        if request and request.get('request') != (session.get('fleet_ack') or {}).get('request'):
            ack = {'request': request.get('request')}
            try:
                save(engine, session, allowed, request)
            except (ValueError, KeyError, TypeError, PermissionError):
                ack['error'] = 'No se pudo guardar: datos inválidos o versión desactualizada. Descargá tus cambios y cargá la última versión compartida.'
            except Exception:
                ack['error'] = 'No se pudo confirmar el guardado. Conservá una copia de tus cambios y volvé a cargar la versión compartida.'
            session['fleet_ack'] = ack
            st.rerun()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error('Fleet render failed: %s', type(exc).__name__)
        st.error('No se pudo conectar con el tablero compartido. Tus datos anteriores se conservan; intentá nuevamente.')
