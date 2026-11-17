"""Explicit, preview-first fiscal onboarding; no accounts or outbound notices."""
import hashlib
import json
from datetime import date


def render_fiscal_onboarding(st, engine, actor='', on_saved=None):
    from am_hub_fiscal_onboarding import TAX_OPTIONS, plan_onboarding, reconciliation_inventory
    from am_hub_onboarding_store import snapshot_onboarding, apply_plan
    st.caption('Versión onboarding fiscal 2026.11.17-1 · reutiliza fichas y tarjetas existentes; no crea usuarios ni envía avisos.')
    try:
        snapshot = snapshot_onboarding(engine)
    except Exception:
        st.error('No se pudo consultar la base actual. No se guardó ningún cambio. Reintentá cuando vuelva la conexión.')
        return
    clients, profiles, tasks = (snapshot[k] for k in ('clients', 'profiles', 'tasks'))
    with st.expander('Revisar clientes recuperados de Tareas', expanded=False):
        st.caption('Inventario sin cambios. Los alias y las identidades dudosas requieren revisión; no se fusionan ni se renombran clientes.')
        inventory = reconciliation_inventory(clients, profiles, tasks)
        if inventory: st.dataframe(inventory, hide_index=True, use_container_width=True)
        else: st.info('No hay clientes ni tareas para revisar.')
    names = sorted({str(r.get('cliente') or '') for r in clients if r.get('cliente')})
    mode = st.radio('Qué querés hacer', ['Completar cliente existente', 'Crear cliente contable'], key='fiscal_onboarding_mode')
    if mode == 'Completar cliente existente':
        if not names:
            st.info('No hay clientes registrados. Elegí Crear cliente contable.')
            return
        cliente = st.selectbox('Cliente a completar', names, key='fiscal_onboarding_client')
    else:
        task_only = sorted({str(t.get('cliente') or '') for t in tasks if t.get('cliente') and str(t.get('cliente')) not in names})
        source_name = st.selectbox('Recuperar nombre ya cargado en Tareas', ['Ingresar un nombre nuevo'] + task_only, key='fiscal_onboarding_source_name')
        if source_name == 'Ingresar un nombre nuevo':
            cliente = st.text_input('Nombre del nuevo cliente / razón social', key='fiscal_onboarding_new_client').strip()
        else:
            cliente = source_name
            st.warning('Revisá si este nombre es un alias de un cliente existente antes de crear otro. No se fusionan identidades automáticamente.')
    if mode == 'Crear cliente contable' and cliente in names:
        st.error('Este cliente ya existe. Elegí Completar cliente existente para reutilizarlo sin repetir el alta.')
        return
    same = [p for p in profiles if p.get('cliente') == cliente]
    profile = same[0] if len(same) == 1 else {}
    prefix = 'fiscal_onboarding_' + hashlib.sha256((mode+'|'+cliente).encode()).hexdigest()[:16]
    st.markdown('#### Datos fiscales confirmados')
    cuit = st.text_input('CUIT', value=str(profile.get('cuit') or ''), key=prefix+'_cuit', placeholder='11 dígitos, según constancia o DDJJ verificada')
    taxes = st.multiselect('Impuestos en los que está inscripto', list(TAX_OPTIONS), key=prefix+'_taxes')
    st.caption('Seleccioná sólo inscripciones confirmadas. No se infieren por actividad o nombre. Las obligaciones sin calendario oficial quedarán pendientes, sin fecha inventada.')
    st.caption('Esta primera configuración cubre obligaciones mensuales de las opciones listadas. Ganancias, Bienes Personales, empleadores/SUSS, SICORE, CM05 anual y otros regímenes o provincias requieren configuración específica; no se consideran cubiertos por esta alta.')
    period = st.text_input('Primer período fiscal a organizar (AAAA-MM)', value=date.today().strftime('%Y-%m'), key=prefix+'_period')
    responsable = st.text_input('Responsable de las tarjetas nuevas', value=actor or 'AM Consultora', key=prefix+'_responsable')
    evidence = st.text_input('Referencia de la constancia / evidencia revisada', key=prefix+'_evidence', placeholder='Ej.: constancia ARCA vigente y alta IIBB revisadas')
    verified = st.checkbox('Verifiqué el CUIT, las inscripciones y el primer período contra sus antecedentes', key=prefix+'_verified')
    request = dict(cliente=cliente, cuit=cuit, taxes=taxes, period=period, responsable=responsable)
    signature = hashlib.sha256(json.dumps(dict(request,evidence=evidence,verified=verified),sort_keys=True).encode()).hexdigest()
    if st.button('Revisar ficha y tarjetas antes de guardar', key=prefix+'_preview'):
        st.session_state.pop(prefix+'_plan',None)
        if not verified or not evidence.strip():
            st.error('Confirmá los datos e indicá la evidencia revisada antes de generar la propuesta.')
        else:
            try:
                client_record = None
                if mode == 'Crear cliente contable':
                    client_record = {'cliente':cliente,'rubro':'','estado':'Activo','plan':'','responsable_am':responsable,'fecha_inicio':'','servicio_digital':'No','servicio_consultoria':'No','servicio_contabilidad':'Sí','notas':'Alta contable desde onboarding fiscal; evidencia: '+evidence.strip()}
                plan = plan_onboarding(**request, clients=clients, profiles=profiles, tasks=tasks, actor=actor, client_record=client_record)
                st.session_state[prefix+'_plan'] = {'plan':plan,'fingerprint':snapshot['fingerprint'],'signature':signature,'evidence':evidence.strip()}
            except ValueError as exc:
                st.error(str(exc))
    saved = st.session_state.get(prefix+'_plan')
    if not saved: return
    if saved['signature'] != signature:
        st.info('Cambiaste los datos. Revisá nuevamente la propuesta antes de guardar.')
        return
    plan = saved['plan']
    for message in plan.get('conflicts',[]): st.error(str(message))
    for message in plan.get('warnings',[]): st.warning(str(message))
    st.markdown('#### Propuesta')
    st.write('Ficha fiscal:', plan.get('profile',{}))
    if plan.get('existing'):
        st.write('Tarjetas existentes que se conservan:',plan['existing'])
    if plan.get('tasks'):
        st.dataframe([{k:t.get(k,'') for k in ('tarea','fecha_limite','recurrente','frecuencia','responsable_am')} for t in plan['tasks']], hide_index=True, use_container_width=True)
    else: st.caption('No se crearán tarjetas nuevas.')
    st.caption('Conserva comentarios, historial, estados, fechas y accesos existentes. El CUIT no da de alta impuestos en ARCA. El onboarding comercial y la documentación pueden seguir pendientes.')
    if plan.get('conflicts'): return
    if st.button('Guardar ficha y tarjetas propuestas', key=prefix+'_apply'):
        try:
            client_insert = None
            if mode == 'Crear cliente contable':
                client_insert = {'cliente':cliente,'rubro':'','estado':'Activo','plan':'','responsable_am':responsable,'fecha_inicio':'','servicio_digital':'No','servicio_consultoria':'No','servicio_contabilidad':'Sí','notas':'Alta contable desde onboarding fiscal; evidencia: '+evidence.strip()}
            result = apply_plan(engine,plan,saved['fingerprint'],client_insert=client_insert)
        except Exception as exc:
            st.error('No se aplicó la propuesta: '+str(exc))
            return
        result = dict(result, evidence=saved['evidence'], actor=actor, requested_taxes=taxes, first_period=period)
        st.session_state.pop(prefix+'_plan',None)
        if on_saved: on_saved(result)
        st.success('Ficha y tarjetas guardadas. No se crearon accesos ni se enviaron avisos.')
        st.write(result)
