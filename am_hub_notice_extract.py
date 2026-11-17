"""Conservative labeled DDJJ extraction; never derive payable amounts from sign."""
import re,json
EXTRACTOR_REVISION = "iva-simple-cm03-v4"
from datetime import datetime

def _one(values):
    vals=list(dict.fromkeys(v.strip() for v in values))
    return vals[0] if len(vals)==1 else ''

def _money(text,label):
    return _one(re.findall(r'(?im)^\s*'+label+r'\s*:?\s*\$\s*([\d.,]+)\s*$',text))

def _number(s):
    return float(s.replace('.','').replace(',','.')) if s else None

def parse_ddjj(text):
    from am_hub_payment_notice import parse_vep
    d=parse_vep(text);d.update(resultado='',fuente_fecha='',nota_saldo='')
    # Layout text preserves AGIP's labels and columns. CUIT of signatory is excluded.
    cuits=re.findall(r'(?im)^\s*(?:Raz[oó]n Social:[^\n]*?\s+)?CUIT\s*:?\s*(\d{2}-?\d{8}-?\d)\b',text)
    if not cuits: cuits=re.findall(r'(?im)Raz[oó]n Social:[^\n]*?\bCUIT:\s*(\d{2}-?\d{8}-?\d)',text)
    cuits += re.findall(r'(?im)^\s*CUIT[^\n]*\n\s*(\d{2}-?\d{8}-?\d)\b',text)
    d['cuit']=_one(cuits)
    periods=re.findall(r'(?im)Per[ií]odo\s*:?\s*(\d{2})\s*-\s*(\d{4})',text)
    periods += [(m,y) for y,m in re.findall(r'(?im)Per[ií]odo\s*:?\s*(\d{4})(\d{2})\b',text)]
    periods += re.findall(r'(?im)(?:Vista Previa|Determinaci[oó]n del impuesto)\s*\|\s*(\d{2})/(\d{4})',text)
    if periods:d['periodo']=_one([m+'/'+y for m,y in periods])
    if 'CONTRIBUYENTES LOCALES' in text.upper() and ('SICOL' in text.upper() or 'AGIP' in text.upper()):
        d['impuesto']='Ingresos Brutos';d['monto']='';d['vencimiento']=''
        total=_one(re.findall(r'(?im)\b(?:SALDO A PAGAR|TOTAL A PAGAR)\s*:?\s*\$\s*([\d.,]+)\s*$',text))
        favor=_money(text,r'SUBTOTAL A FAVOR DEL CONTRIBUYENTE')
        fisco=_money(text,r'SUBTOTAL A FAVOR DGR')
        d['vencimiento']=_one(re.findall(r'(?i)Fecha venc\s*:\s*(\d{2}/\d{2}/\d{4})',text))
        if d['vencimiento']:d['fuente_fecha']='Fecha venc de DDJJ AGIP local'
        if total and _number(total)>0:
            d.update(resultado='A pagar',monto=total)
            if favor and _number(favor)>0:d['advertencias'].append('AGIP informa saldo a pagar y favor positivos: revisar inconsistencia antes de continuar.')
        elif total and _number(total)==0 and favor and _number(favor)==0 and fisco and _number(fisco)==0:
            d.update(resultado='Sin saldo',monto='0,00')
        elif total and _number(total)==0:
            d['resultado']='Saldo a favor'
            d['monto']=favor if favor and _number(favor)>0 else ''
            if not d['monto']:d['advertencias'].append('Total a pagar cero no identifica el importe del saldo a favor. Completalo desde evidencia explícita; no se inventa.')
        d['advertencias'].append('Confirmar saldo y Fecha venc contra la DDJJ AGIP.')
    elif 'CONVENIO MULTILATERAL' in text.upper() and re.search(r'\bCM03\b',text,re.I):
        d.update(impuesto='Ingresos Brutos',monto='',vencimiento='',resultado='')
        periods=re.findall(r'(?im)^\s*Anticipo\s*:\s*(\d{4})(\d{2})\b',text)
        d['periodo']=_one([m+'/'+y for y,m in periods])
        total=_one(re.findall(r'(?im)Total a pagar\s*:\s*\$\s*([\d.,]+)\s*$',text))
        rows=re.findall(r'(?im)^\s*TOTALES\s+([^\n]+)$',text)
        values=re.findall(r'\$\s*([\d.,]+)',rows[0]) if len(rows)==1 else []
        headers=all(re.search(label,text,re.I) for label in ('Jurisdicciones incluidas','Valores Restan','Valores Suman','A Favor Fisco','Contribuyente','A Pagar'))
        if headers and len(values)==6 and total and _number(values[5])==_number(total):
            favor,fisco,pagar=map(_number,values[3:6])
            if pagar>0:
                d.update(resultado='A pagar',monto=total)
                if favor>0:d['advertencias'].append('CM03 también muestra saldo a favor en otras jurisdicciones; no se compensa automáticamente con el total a pagar.')
            elif pagar==0 and favor>0 and fisco==0:
                d.update(resultado='Saldo a favor',monto=values[3])
            elif pagar==0 and favor==0 and fisco==0:
                d.update(resultado='Sin saldo',monto='0,00')
            else:d['advertencias'].append('Totales CM03 no concluyentes: revisar saldo a favor del fisco y pagos antes de seleccionar resultado.')
        else:
            d['advertencias'].append('No se pudo validar la fila TOTALES y sus seis columnas contra Total a pagar; revisar manualmente.')
        d['advertencias'].append('CM03: confirmar columnas de la fila TOTALES. Fecha de presentación no es vencimiento; verificar fecha manualmente si hay pago.')
    elif re.search(r'IMPUESTO AL VALOR\s+AGREGADO|F\.2051|\bIVA SIMPLE\b',text,re.I):
        d.update(impuesto='IVA',monto='',vencimiento='')
        favor=_money(text,r'Saldo de libre disponibilidad a favor del contribuyente del per[ií]odo')
        arca=_money(text,r'Saldo t[eé]cnico a favor de ARCA')
        if favor and _number(favor)>0 and (not arca or _number(arca)==0):
            d.update(resultado='Saldo a favor',monto=favor,nota_saldo='Saldo de libre disponibilidad a favor del contribuyente del período. No incluye ni suma el saldo técnico.')
        elif arca and _number(arca)>0 and (not favor or _number(favor)==0):
            d.update(resultado='A pagar',monto=arca,nota_saldo='Importe técnico a favor ARCA: confirmar saldo final a pagar tras percepciones/compensaciones; no equivale necesariamente al pago.')
        else:d['advertencias'].append('Saldo de libre disponibilidad del período no identificado de forma inequívoca; revisar manualmente. No usar saldo técnico ni saldo del período anterior.')
        d['advertencias'].append('Vencimiento IVA únicamente desde tarjeta verificada del mismo cliente/CUIT, impuesto y período; no se usa fecha de presentación ni vencimiento del VEP.')
    d['advertencias']=[w for w in d['advertencias'] if not any(d.get(k) and w==k+': no identificado de forma única; completar/revisar.' for k in ('cuit','impuesto','periodo','monto','vencimiento'))]
    return d

def card_deadline(cliente,profile_cuit,document_cuit,period,tasks,impuesto='IVA',calendar=None):
    """Read one current, verified task. Never substitute a different taxpayer/date."""
    from am_hub_tax_calendar import load_calendar, valid_entry
    norm=lambda x: re.sub(r'\D','',str(x or ''))
    cuit=norm(profile_cuit)
    if len(cuit)!=11 or cuit!=norm(document_cuit):
        return '', 'CUIT de documento y ficha no verificados. Completá/verificá el CUIT en Ficha cliente para tomar la fecha de Tareas; mientras tanto, ingresala manualmente.'
    m=re.fullmatch(r'(\d{2})/(\d{4})',period)
    period=m[2]+'-'+m[1] if m else period
    tax=str(impuesto).strip().casefold()
    identity=('IVA','MENSUAL','NACIONAL') if tax=='iva' else (('IIBB','CM03','COMARB') if tax in ('iibb','ingresos brutos','convenio multilateral') else None)
    if not identity:return '', 'Impuesto sin correspondencia inequívoca con Tareas: completar manualmente.'
    try: rows=load_calendar() if calendar is None else calendar
    except (OSError, ValueError): rows=[]
    dates={r['vencimiento'] for r in rows if valid_entry(r) and (r.get('impuesto'),r.get('obligacion'),r.get('jurisdiccion'))==identity and r.get('periodo')==period and int(cuit[-1]) in r.get('terminaciones',[])}
    if len(dates)>1:return '', 'Calendario vigente ambiguo para este impuesto/CUIT/período: completar manualmente.'
    found=[]
    for t in tasks:
        if str(t.get('cliente','')).strip().casefold()!=cliente.strip().casefold():continue
        if str(t.get('estado','')).strip().casefold() in ('cancelada','cancelado','anulada','anulado','archivada','archivado'):continue
        raw=str(t.get('id_externo',''))
        try: meta=json.loads(raw[len('fiscal:v1:'):]) if raw.startswith('fiscal:v1:') else {}
        except (ValueError,TypeError):continue
        if not isinstance(meta,dict):continue
        if (meta.get('impuesto'),meta.get('obligacion'),meta.get('jurisdiccion'))!=identity or meta.get('periodo')!=period or meta.get('estado')!='verificado' or meta.get('motivo') or meta.get('modo_fecha'):continue
        if str(meta.get('terminacion'))!=cuit[-1] or not str(meta.get('fuente','')).startswith('https://'):continue
        if meta.get('cuit') and norm(meta['cuit'])!=cuit:continue
        due=str(t.get('fecha_limite',''))
        if dates and due not in dates:continue
        try: day=datetime.strptime(due,'%Y-%m-%d').strftime('%d/%m/%Y')
        except ValueError:continue
        found.append((day,str(t.get('id','')),meta['fuente']))
    if len(found)!=1 or not found[0][1]:return '', 'Sin tarjeta única verificada para este cliente/CUIT, impuesto y período: completar vencimiento manualmente.'
    day,task_id,source=found[0]
    status='Fecha propuesta desde Tareas; requiere revisión, sin verificación independiente del calendario vigente. ' if not dates else 'Fecha de tarjeta contrastada con calendario vigente. '
    return day, status+'Tarjeta '+task_id+' · '+identity[0]+'/'+identity[1]+' · período '+period+' · vencimiento '+day+' · fuente: '+source
