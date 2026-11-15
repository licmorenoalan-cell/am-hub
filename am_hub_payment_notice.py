"""Human-reviewed payment notices. No email sending or external PDF processing."""
import hashlib
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

def body(fields):
    return (f"Hola,\n\nAdjuntamos la documentación de {fields['cliente']} correspondiente a "
            f"{fields['impuesto']}, período {fields['periodo']}.\n"
            f"Importe a pagar: $ {fields['monto']}.\n"
            f"Vencimiento indicado en el VEP: {fields['vencimiento']}.\n\n"
            "Por favor, enviános el comprobante una vez realizado el pago.\n\nAM Consultora")

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
           'SUMMARY:'+escape(title),'DESCRIPTION:'+escape(details),'END:VEVENT','END:VCALENDAR']
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
    validate(fields)
    msg=EmailMessage(policy=policy.SMTP)
    msg['To']=fields['email'];msg['Subject']=f"{fields['cliente']} | {fields['impuesto']} | {fields['periodo']}"
    msg['X-Unsent']='1';msg.set_content(body(fields))
    for name,data in attachments:
        if not data.startswith(b'%PDF-') or len(data)>MAX_BYTES: raise ValueError('Adjunto PDF inválido.')
        msg.add_attachment(data,maintype='application',subtype='pdf',filename=name.split('/')[-1].split('\\')[-1])
    return msg.as_bytes()

def render_payment_notice(cliente, perfil):
    import streamlit as st
    with st.expander('Preparar aviso de pago · DDJJ / VEP',expanded=False):
        st.caption('Borrador asistido. Los PDF se procesan en AM Hub, sin enviarse a servicios de IA. No se envían correos ni se crean eventos automáticamente.')
        base='aviso_'+hashlib.sha256(cliente.encode()).hexdigest()[:12]
        vep=st.file_uploader('VEP (PDF, uno por aviso)',type=['pdf'],key=base+'_vep')
        ddjj=st.file_uploader('DDJJ y respaldos (PDF)',type=['pdf'],accept_multiple_files=True,key=base+'_ddjj')
        if not vep: return
        files=[(vep.name,vep.getvalue())]+[(x.name,x.getvalue()) for x in ddjj]
        if len(files)>10 or sum(len(x[1]) for x in files)>25*1024*1024:
            st.error('Máximo 10 PDF y 25 MB por aviso.');return
        digest=hashlib.sha256(b''.join(x[1] for x in files)).hexdigest()[:16]
        key=base+'_'+digest
        try:
            if key+'_parsed' not in st.session_state:
                text=pdf_text(files[0][1]);st.session_state[key+'_parsed']=(text,parse_vep(text))
            text,data=st.session_state[key+'_parsed']
        except Exception:
            st.error('No se pudo leer el VEP. Usá un PDF legible, sin contraseña y de hasta 15 MB / 40 páginas.');return
        if not text.strip(): st.warning('PDF sin texto: completá todos los campos manualmente contrastando el documento.')
        with st.expander('Texto extraído del VEP (evidencia)'): st.text(text[:30000])
        for warn in data['advertencias']: st.caption(warn)
        detected=re.sub(r'\D','',data['cuit']);expected=re.sub(r'\D','',str(perfil.get('cuit','')))
        if detected and expected and detected!=expected:
            st.error('El CUIT del VEP no coincide con el cliente. Cambiá el cliente o el archivo.');return
        if not detected or not expected: st.warning('No se pudo contrastar el CUIT automáticamente: revisalo en el PDF y la ficha del cliente.')
        fields={'cliente':cliente}
        for name,label in [('impuesto','Impuesto'),('periodo','Período fiscal'),('monto','Importe total en pesos'),('vencimiento','Vencimiento / expiración del VEP (DD/MM/AAAA)')]:
            fields[name]=st.text_input(label,value=data[name],key=key+'_'+name)
        fields['email']=st.text_input('Destinatarios (coma para separar)',value=str(perfil.get('email_destinatarios','') or ''),key=key+'_email')
        approval_key=key+hashlib.sha256(repr(sorted(fields.items())).encode()).hexdigest()[:12]
        reviewed=st.checkbox('Verifiqué cliente/CUIT, destinatarios, importes, período, fecha y todos los adjuntos contra los PDF.',key=approval_key)
        if not reviewed: return
        try:
            validate(fields);url,ics=calendar_outputs(fields);eml=email_draft(fields,files)
        except ValueError as exc: st.error(str(exc));return
        st.text_area('Texto listo para copiar',value=body(fields),height=230,key=approval_key+'_body')
        for index,(name,content) in enumerate(files):
            st.download_button('Descargar '+name,content,file_name=name,mime='application/pdf',key=key+'_pdf_'+str(index))
        st.warning('Zoho no está integrado por API: esta descarga NO guarda un borrador en Zoho. Podés copiar el texto y adjuntar los PDF, o abrir el .eml en un cliente compatible.')
        st.download_button('Descargar correo preparado (.eml con PDF)',eml,file_name='aviso_pago.eml',mime='message/rfc822',key=key+'_eml')
        st.download_button('Descargar recordatorio (.ics)',ics,file_name='vencimiento.ics',mime='text/calendar',key=key+'_ics')
        st.link_button('Abrir evento en Google Calendar',url,help='El enlace contiene cliente, impuesto e importe. Sólo se envían a Google cuando lo abrís; el evento requiere guardar.')
