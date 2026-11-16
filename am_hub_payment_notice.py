"""Human-reviewed payment notices. No email sending or external PDF processing."""
import hashlib
import html
import io
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from email import policy
from urllib.parse import urlencode

MAX_BYTES = 15 * 1024 * 1024

def pdf_text(data):
    from pypdf import PdfReader
    if len(data) > MAX_BYTES or not data.startswith(b'%PDF-'):
        raise ValueError('PDF inválido o mayor a 15 MB.')
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError('El PDF está protegido. Usá una copia sin contraseña.')
    if len(reader.pages) > 40:
        raise ValueError('El PDF supera 40 páginas.')
    return '\n'.join(p.extract_text() or '' for p in reader.pages)

def parse_vep(text):
    """Only explicit labelled values; ambiguous or absent values stay blank."""
    patterns = {
        'impuesto': r'(?im)^\s*Impuesto\s*[:\-]?\s*([^\n]+)',
        'periodo': r'(?im)^\s*Per[ií]odo(?:\s+fiscal)?\s*[:\-]?\s*(\d{4}[-/]\d{2}|\d{2}[-/]\d{4})\b',
        'monto': r'(?im)^\s*(?:Importe\s+total|Total\s+a\s+pagar|Importe\s+a\s+pagar)\s*[:\-]?\s*\$?\s*([\d.,]+)',
        'vencimiento': r'(?im)^\s*(?:Fecha\s+de\s+expiraci[oó]n|Fecha\s+de\s+vencimiento|Vencimiento)\s*[:\-]?\s*(\d{2}[/\-]\d{2}[/\-]\d{4})\b',
        'cuit': r'(?im)^\s*CUIT(?:\s+del\s+contribuyente)?\s*[:\-]?\s*(\d{2}-?\d{8}-?\d)\b',
    }
    result = {}; warnings = []
    for field, pattern in patterns.items():
        vals = list(dict.fromkeys(v.strip() for v in re.findall(pattern, text)))
        result[field] = vals[0] if len(vals) == 1 else ''
        if len(vals) != 1: warnings.append(f'{field}: no identificado de forma única; completar/revisar.')
    result['advertencias'] = warnings
    return result

def amount(value):
    s = value.strip().replace('$','').replace(' ','')
    # Argentine notation only; dot decimals without comma are ambiguous.
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?', s):
        raise ValueError('Ingresá el monto en pesos: 123456,78 o 123.456,78.')
    n = Decimal(s.replace('.','').replace(',','.'))
    if n <= 0: raise ValueError('El monto debe ser mayor a cero.')
    return n.quantize(Decimal('.01'))

def validate(fields):
    if not fields.get('cliente','').strip() or not fields.get('impuesto','').strip():
        raise ValueError('Completá cliente e impuesto.')
    if not re.fullmatch(r'(?:\d{4}[-/](?:0[1-9]|1[0-2])|(?:0[1-9]|1[0-2])[-/]\d{4})',fields.get('periodo','')):
        raise ValueError('Período inválido: usá AAAA-MM o MM/AAAA.')
    amount(fields.get('monto',''))
    try: datetime.strptime(fields.get('vencimiento','').replace('-','/'),'%d/%m/%Y')
    except ValueError: raise ValueError('Vencimiento inválido: usá DD/MM/AAAA.')
    emails = [x.strip() for x in fields.get('email','').split(',') if x.strip()]
    if not emails or any(not re.fullmatch(r'[^\s@,<>]+@[^\s@,<>]+\.[^\s@,<>]+',x) for x in emails):
        raise ValueError('Completá destinatarios válidos separados por coma.')
    if any('\n' in str(v) or '\r' in str(v) for v in fields.values()):
        raise ValueError('Los campos no deben contener saltos de línea.')
    return fields

def notice_items(fields):
    items = fields.get('avisos')
    if items is None:
        return [validate(fields)]
    if not isinstance(items, list) or not 1 <= len(items) <= 10:
        raise ValueError('Cargá entre 1 y 10 VEP por correo.')
    return [validate(dict(item, cliente=fields['cliente'], email=fields['email'])) for item in items]

def notice_subject(fields):
    items = notice_items(fields)
    if len(items) == 1:
        return f"{fields['cliente']} | {items[0]['impuesto']} | {items[0]['periodo']}"
    return f"{fields['cliente']} | Avisos de pago ({len(items)} VEP)"

def unique_pdfs(attachments):
    seen=set(); result=[]; names=set()
    for name,data in attachments:
        digest=hashlib.sha256(data).hexdigest()
        if digest in seen: continue
        seen.add(digest)
        name=name.split('/')[-1].split('\\')[-1]
        if name in names: name=digest[:8]+'_'+name
        names.add(name); result.append((name,data))
    return result

def calendar_attachments(fields):
    items=notice_items(fields)
    return [('vencimiento.ics' if len(items)==1 else f'vencimiento_{i+1:02d}.ics', calendar_outputs(item)[1]) for i,item in enumerate(items)]

def tax_label(value):
    # Only normalize recognized names, never infer another tax from a document.
    normalized=re.sub(r'^\d+\s*[-:]\s*','',value.strip()).upper()
    if normalized in ('IVA','IMPUESTO AL VALOR AGREGADO'): return 'IVA'
    if normalized in ('IIBB','INGRESOS BRUTOS','INGRESOS BRUTOS LOCAL','INGRESOS BRUTOS AGIP','INGRESOS BRUTOS CONVENIO MULTILATERAL'):
        return 'Ingresos brutos'
    return value.strip()

def notice_opening(items):
    labels=list(dict.fromkeys(tax_label(x['impuesto']).upper() for x in items))
    # Conventional order for the requested IVA / IIBB combination.
    if set(labels)=={'IVA','INGRESOS BRUTOS'}: names='IVA e INGRESOS BRUTOS'
    elif len(labels)==1: names=labels[0]
    else:
        conjunction=' e ' if labels[-1].startswith(('I','HI')) else ' y '
        names=', '.join(labels[:-1])+conjunction+labels[-1]
    return 'Adjuntamos la documentación de '+names+' del periodo de referencia.'

def body(fields):
    items=notice_items(fields)
    sections=[]
    for item in items:
        url,_=calendar_outputs(item)
        sections.append(f"{tax_label(item['impuesto'])}\n- Saldo a pagar: $ {item['monto']}\n- Vencimiento: {item['vencimiento']} (Agendar vencimiento: {url})")
    return ('Buenos días!\n\n'+notice_opening(items)+'\n\n'+'\n\n'.join(sections)+
            '\n\nCualquier duda, quedamos a disposición\n\nSaludos!')

def body_html(fields):
    items=notice_items(fields)
    parts=['<p>Buenos días!</p>','<p>'+html.escape(notice_opening(items))+'</p>']
    for item in items:
        url,_=calendar_outputs(item)
        parts.append('<p><strong>'+html.escape(tax_label(item['impuesto']))+'</strong><br>'+
                     '- Saldo a pagar: $ '+html.escape(item['monto'])+'<br>'+
                     '- Vencimiento: '+html.escape(item['vencimiento'])+
                     ' (<a href="'+html.escape(url,quote=True)+'">Agendar vencimiento</a>)</p>')
    parts+=['<p>Cualquier duda, quedamos a disposición</p>','<p>Saludos!</p>']
    return ''.join(parts)

def calendar_outputs(fields):
    validate(fields)
    day = datetime.strptime(fields['vencimiento'].replace('-','/'),'%d/%m/%Y').date()
    end = day + timedelta(days=1)
    title = f"Pago {fields['impuesto']} — {fields['cliente']} — {fields['periodo']}"
    details = f"Importe: $ {fields['monto']}. Vencimiento indicado en VEP; verificar vigencia antes del pago."
    url='https://calendar.google.com/calendar/render?'+urlencode(dict(action='TEMPLATE',text=title,dates=f'{day:%Y%m%d}/{end:%Y%m%d}',details=details))
    def escape(s): return s.replace('\\','\\\\').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
    uid=hashlib.sha256((title+str(day)).encode()).hexdigest()+'@am-hub'
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//AM Hub//Aviso de pago//ES','BEGIN:VEVENT',
           'UID:'+uid,'DTSTAMP:'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
           f'DTSTART;VALUE=DATE:{day:%Y%m%d}',f'DTEND;VALUE=DATE:{end:%Y%m%d}',
           'SUMMARY:'+escape(title),'DESCRIPTION:'+escape(details),
           'BEGIN:VALARM','ACTION:DISPLAY','TRIGGER:-P1D',
           'DESCRIPTION:'+escape('Recordatorio: '+title),'END:VALARM','END:VEVENT','END:VCALENDAR']
    # Fold UTF-8 lines without splitting a codepoint (RFC 5545).
    folded=[]
    for line in lines:
        chunk=''
        for ch in line:
            if len((chunk+ch).encode())>74:
                folded.append(chunk);chunk=' '+ch
            else: chunk+=ch
        folded.append(chunk)
    return url, ('\r\n'.join(folded)+'\r\n').encode()

def email_draft(fields, attachments):
    notice_items(fields)
    msg=EmailMessage(policy=policy.SMTP)
    msg['To']=fields['email'];msg['Subject']=notice_subject(fields)
    msg['X-Unsent']='1';msg.set_content(body(fields))
    msg.add_alternative(body_html(fields),subtype='html')
    for name,data in unique_pdfs(attachments):
        if not data.startswith(b'%PDF-') or len(data)>MAX_BYTES: raise ValueError('Adjunto PDF inválido.')
        msg.add_attachment(data,maintype='application',subtype='pdf',filename=name.split('/')[-1].split('\\')[-1])
    for name,ics in calendar_attachments(fields):
        msg.add_attachment(ics, maintype='text', subtype='calendar', filename=name)
    return msg.as_bytes()

def render_payment_notice(cliente, perfil):
    import streamlit as st
    with st.expander('Preparar aviso de pago · DDJJ / VEP',expanded=False):
        st.caption('Borrador asistido. Los PDF se procesan en AM Hub, sin enviarse a servicios de IA. No se envían correos ni se crean eventos automáticamente.')
        base='aviso_'+hashlib.sha256(cliente.encode()).hexdigest()[:12]
        veps=st.file_uploader('VEP (PDF, uno o varios)',type=['pdf'],accept_multiple_files=True,key=base+'_veps')
        ddjj=st.file_uploader('DDJJ y respaldos (PDF)',type=['pdf'],accept_multiple_files=True,key=base+'_ddjj')
        if not veps: return
        vep_files=unique_pdfs([(x.name,x.getvalue()) for x in veps])
        files=unique_pdfs(vep_files+[(x.name,x.getvalue()) for x in ddjj])
        if len(files)>10 or sum(len(x[1]) for x in files)>25*1024*1024:
            st.error('Máximo 10 PDF y 25 MB por correo.');return
        digest=hashlib.sha256(b''.join(x[1] for x in files)).hexdigest()[:16]
        key=base+'_'+digest
        notices=[]
        for i,(filename,raw) in enumerate(vep_files):
            subkey=key+'_'+str(i)
            st.markdown('**VEP '+str(i+1)+' · '+filename+'**')
            try:
                if subkey+'_parsed' not in st.session_state:
                    text=pdf_text(raw);st.session_state[subkey+'_parsed']=(text,parse_vep(text))
                text,data=st.session_state[subkey+'_parsed']
            except Exception:
                st.error('No se pudo leer este VEP. Usá PDF legible sin contraseña, hasta 15 MB / 40 páginas.');return
            if not text.strip(): st.warning('PDF sin texto: completá este VEP manualmente contrastando el documento.')
            if st.checkbox('Mostrar evidencia VEP '+str(i+1),key=subkey+'_evidence'): st.text(text[:30000])
            for warn in data['advertencias']: st.caption(warn)
            detected=re.sub(r'\D','',data['cuit']);expected=re.sub(r'\D','',str(perfil.get('cuit','')))
            if detected and expected and detected!=expected:
                st.error('El CUIT de este VEP no coincide con el cliente.');return
            if not detected or not expected: st.warning('Revisá CUIT de este VEP y ficha del cliente: contraste automático no disponible.')
            item={}
            for name,label in [('impuesto','Impuesto'),('periodo','Período fiscal'),('monto','Importe total en pesos'),('vencimiento','Vencimiento / expiración del VEP (DD/MM/AAAA)')]:
                item[name]=st.text_input(label,value=data[name],key=subkey+'_'+name)
            reviewkey=subkey+hashlib.sha256(repr(sorted(item.items())).encode()).hexdigest()[:12]
            if not st.checkbox('Verifiqué los datos y vencimiento del VEP '+str(i+1),key=reviewkey):
                st.caption('Revisá este VEP antes de preparar el correo.')
                notices.append(dict(item,_unreviewed=True))
            else: notices.append(item)
        fields={'cliente':cliente,'avisos':notices}
        fields['email']=st.text_input('Destinatarios (coma para separar)',value=str(perfil.get('email_destinatarios','') or ''),key=key+'_email')
        if any(x.get('_unreviewed') for x in notices): return
        approval_key=key+hashlib.sha256(repr(sorted(fields.items())).encode()).hexdigest()[:12]
        reviewed=st.checkbox('Verifiqué cliente/CUIT, destinatarios, importes, período, fecha y todos los adjuntos contra los PDF.',key=approval_key)
        if not reviewed: return
        try:
            notice_items(fields);eml=email_draft(fields,files)
        except ValueError as exc: st.error(str(exc));return
        st.markdown(body_html(fields), unsafe_allow_html=True)
        st.caption('Calendario: usar el enlace o importar el ICS (no ambos). El ICS solicita aviso un día antes; el cliente debe revisar notificaciones, fecha y zona horaria. En Google debe guardar el evento y configurar el aviso.')
        st.text_area('Texto listo para copiar',value=body(fields),height=230,disabled=True,key=approval_key+'_body')
        for index,(name,content) in enumerate(files):
            st.download_button('Descargar '+name,content,file_name=name,mime='application/pdf',key=key+'_pdf_'+str(index))
        # OAuth secrets are deployment-only, never user inputs or repository data.
        zoho_settings = st.secrets.get('zoho_drafts', {})
        if zoho_settings:
            from am_hub_zoho_drafts import ZohoConfig, ZohoDraftClient, ZohoDraftError
            draft_state = approval_key + '_zoho_result'
            result = st.session_state.get(draft_state)
            st.caption('Guardar en Zoho transfiere estos campos y PDF a la cuenta AM Consultora. Se crea sólo un borrador: el envío se realiza manualmente en Zoho.')
            if result:
                if result.get('message_id'):
                    st.success('Borrador guardado en Zoho con los PDF. No enviado.')
                else:
                    st.warning('El resultado de este intento no pudo confirmarse. Revisá Borradores antes de crear otro aviso para evitar duplicados.')
                st.link_button('Abrir Borradores de Zoho', 'https://mail.zoho.com/zm/#mail/folder/drafts')
            elif st.button('Guardar borrador en Zoho (no enviar)', key=approval_key+'_zoho'):
                # Mark before networking; reruns/double clicks never repeat an uncertain POST.
                st.session_state[draft_state] = {'uncertain': True}
                try:
                    config = ZohoConfig(**dict(zoho_settings))
                    st.session_state[draft_state] = ZohoDraftClient(config).create_draft(fields, files)
                    st.rerun()
                except (ZohoDraftError, ValueError) as exc:
                    st.error(str(exc))
                except Exception:
                    st.error('No se pudo confirmar el borrador. Revisá Zoho antes de reintentar.')
        else:
            st.warning('La conexión Zoho aún no está configurada en este servidor. El .eml NO guarda un borrador en Zoho; podés copiar el texto y adjuntar los PDF manualmente.')
        st.download_button('Descargar correo preparado (.eml con PDF)',eml,file_name='aviso_pago.eml',mime='message/rfc822',key=key+'_eml')
        for i,item in enumerate(notice_items(fields)):
            url,ics=calendar_outputs(item)
            st.download_button('Descargar recordatorio VEP '+str(i+1),ics,file_name=f'vencimiento_{i+1:02d}.ics',mime='text/calendar',key=key+'_ics_'+str(i))
            st.link_button('Google Calendar · VEP '+str(i+1),url,help='Requiere guardar y configurar el aviso en Google.')
