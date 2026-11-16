"""Zoho adapter deliberately restricted to drafts. Secrets never enter logs/UI."""
from dataclasses import dataclass, field
import re
import requests

class ZohoDraftError(RuntimeError):
    pass

@dataclass(frozen=True)
class ZohoConfig:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    refresh_token: str = field(repr=False)
    account_id: str
    from_address: str
    accounts_url: str = 'https://accounts.zoho.com'
    mail_url: str = 'https://mail.zoho.com'

    def __post_init__(self):
        if self.accounts_url != 'https://accounts.zoho.com' or self.mail_url != 'https://mail.zoho.com':
            raise ValueError('Región Zoho no habilitada.')
        if not re.fullmatch(r'\d+',self.account_id) or not all((self.client_id,self.client_secret,self.refresh_token)):
            raise ValueError('Configuración Zoho incompleta.')
        if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',self.from_address):
            raise ValueError('Remitente Zoho inválido.')

class ZohoDraftClient:
    def __init__(self,config,session=None):
        self.config=config
        self.session=session or requests.Session()

    def _request(self,method,url,**kwargs):
        # Never retry POST: a timeout can mean the draft already exists.
        try:
            response=self.session.request(method,url,timeout=(10,45),allow_redirects=False,**kwargs)
            if not 200 <= response.status_code < 300:
                raise ZohoDraftError(f'Zoho rechazó la operación (HTTP {response.status_code}).')
            result=response.json()
            if not isinstance(result,dict): raise ValueError()
            status=result.get('status',{})
            if status and int(status.get('code',200)) >= 300:
                raise ZohoDraftError('Zoho no confirmó la operación.')
            return result
        except ZohoDraftError: raise
        except Exception:
            raise ZohoDraftError('No se pudo confirmar la operación. Revisá Borradores en Zoho antes de reintentar.') from None

    def create_draft(self,fields,attachments):
        from am_hub_payment_notice import notice_items,notice_subject,unique_pdfs,body,MAX_BYTES,calendar_attachments
        notice_items(fields)
        attachments=unique_pdfs(attachments)
        if not 1<=len(attachments)<=10 or sum(len(d) for _,d in attachments)>25*1024*1024:
            raise ValueError('Cantidad o tamaño de adjuntos inválidos.')
        prepared=[]
        for name,data in attachments:
            name=name.split('/')[-1].split('\\')[-1]
            if not name or '\n' in name or '\r' in name or not data.startswith(b'%PDF-') or len(data)>MAX_BYTES:
                raise ValueError('Adjunto PDF inválido.')
            prepared.append((name,data,'application/pdf'))
        for name,ics in calendar_attachments(fields):
            prepared.append((name,ics,'text/calendar'))
        token=self._request('POST',self.config.accounts_url+'/oauth/v2/token',data={
            'grant_type':'refresh_token','client_id':self.config.client_id,
            'client_secret':self.config.client_secret,'refresh_token':self.config.refresh_token})
        access=token.get('access_token')
        if not access: raise ZohoDraftError('No se pudo renovar el acceso a Zoho.')
        headers={'Authorization':'Zoho-oauthtoken '+access}
        base=self.config.mail_url+'/api/accounts/'+self.config.account_id+'/messages'
        refs=[]
        for name,data,mimetype in prepared:
            uploaded=self._request('POST',base+'/attachments',headers=headers,
                params={'uploadType':'multipart','isInline':'false'},files={'attach':(name,data,mimetype)})
            entries=uploaded.get('data',[])
            if isinstance(entries,dict): entries=[entries]
            if len(entries)!=1 or not all(entries[0].get(k) for k in ('attachmentName','attachmentPath','storeName')):
                raise ZohoDraftError('Zoho no confirmó el adjunto. No se creó el borrador.')
            refs.append({k:entries[0][k] for k in ('attachmentName','attachmentPath','storeName')})
        result=self._request('POST',base,headers=headers,json={
            'fromAddress':self.config.from_address,'toAddress':fields['email'],
            'subject':notice_subject(fields),
            'content':body(fields),'mailFormat':'plaintext','mode':'draft','attachments':refs})
        data=result.get('data',{})
        if not isinstance(data,dict) or not data.get('messageId'):
            raise ZohoDraftError('Respuesta sin identificador. Revisá Borradores antes de reintentar.')
        return {'message_id':str(data['messageId']),'attachments':len(refs)}
