"""WSGI ingress: signature verified on original bytes before JSON decoding."""
import hmac
import json
import threading
from pathlib import Path
from urllib.parse import parse_qs
from .settings import Settings
from .engine import Engine,validate_rule
from .events import verify_signature

class Application:
    def __init__(self,engine):self.engine=engine;self.dispatch_lock=threading.Lock();self.telegram_lock=threading.Lock()

    def __call__(self,environ,start_response):
        status=200;result={};plain=False
        try:
            path=environ.get('PATH_INFO','');method=environ.get('REQUEST_METHOD','GET');s=self.engine.s
            if path=='/health' and method=='GET':result={'ok':True,'service':'pcl-assistant'}
            elif path=='/webhooks/meta' and method=='GET':
                q=parse_qs(environ.get('QUERY_STRING',''))
                token=q.get('hub.verify_token',[''])[0];challenge=q.get('hub.challenge',[''])[0]
                if s.verify_token and q.get('hub.mode',[''])[0]=='subscribe' and hmac.compare_digest(token,s.verify_token) and challenge:
                    result=challenge;plain=True
                else:status=403;result={'error':'verification_failed'}
            else:
                if method not in ('POST','GET'):status=405;result={'error':'method_not_allowed'}
                else:
                    try:length=int(environ.get('CONTENT_LENGTH') or '0')
                    except ValueError:raise ValueError('invalid_length')
                    if length<0 or length>1048576:
                        status=413;result={'error':'body_too_large'}
                    elif path=='/webhooks/meta' and method=='POST':
                        body=environ['wsgi.input'].read(length)
                        if not verify_signature(body,environ.get('HTTP_X_HUB_SIGNATURE_256'),s.meta_secret):
                            status=401;result={'error':'invalid_signature'}
                        else:result=self.engine.ingest(json.loads(body))
                    elif path=='/webhooks/telegram' and method=='POST':
                        token=environ.get('HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN','')
                        if not s.telegram_secret or not hmac.compare_digest(token,s.telegram_secret):
                            status=401;result={'error':'invalid_telegram_secret'}
                        else:result=self.engine.receive_telegram(json.loads(environ['wsgi.input'].read(length)))
                    elif path.startswith('/internal/'):
                        auth=environ.get('HTTP_AUTHORIZATION','')
                        if not s.internal_token or not hmac.compare_digest(auth,'Bearer '+s.internal_token):
                            status=401;result={'error':'unauthorized'}
                        else:
                            data=json.loads(environ['wsgi.input'].read(length)) if length else {}
                            if not isinstance(data,dict):raise ValueError('invalid_object')
                            result=self.internal(path,method,data)
                            if result.get('error')=='not_found':status=404
                    else:status=404;result={'error':'not_found'}
        except (ValueError,KeyError,TypeError,AttributeError):status=400;result={'error':'invalid_request'}
        except Exception:
            # No traceback, headers, provider body or credentials in public logs.
            status=500;result={'error':'internal_error'}
        body=(result if plain else json.dumps(result,ensure_ascii=False)).encode()
        start_response(f'{status} '+{200:'OK',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',413:'Payload Too Large',500:'Internal Server Error'}[status],
                       [('Content-Type','text/plain; charset=utf-8' if plain else 'application/json; charset=utf-8'),('Content-Length',str(len(body))),('Cache-Control','no-store')])
        return [body]

    def internal(self,path,method,data):
        e=self.engine
        if method=='POST' and path=='/internal/jobs/claim':return e.claim()
        if method=='POST' and path=='/internal/events/process':return e.process(data['event_id'],data['lease'])
        if method=='POST' and path=='/internal/telegram/process':
            with self.telegram_lock:return e.telegram_process()
        if method=='POST' and path=='/internal/outbox/dispatch':
            with self.dispatch_lock:return e.dispatch()
        if method=='POST' and path=='/internal/maintenance':return e.maintenance()
        if method=='GET' and path=='/internal/rules':return {'rules':e.store.rows('SELECT * FROM rules ORDER BY id')}
        if method=='POST' and path=='/internal/rules':
            r=validate_rule(data)
            with e.store.transaction() as db:e.upsert_rule(db,r)
            return {'saved':r['id']}
        if method=='POST' and path=='/internal/alerts':
            # Caller supplies an ID only; arbitrary upstream exception content is discarded.
            with e.store.transaction() as db:e.alert(db,'workflow_failed',str(data.get('execution_id','unknown'))[:64])
            return {'ok':True}
        return {'error':'not_found'}

_instance=None
_instance_lock=threading.Lock()
def application(environ,start_response):
    global _instance
    with _instance_lock:
        if _instance is None:
            root=Path(__file__).resolve().parents[1]
            knowledge=json.loads((root/'config/knowledge.json').read_text())
            engine=Engine(Settings.from_env(),knowledge=knowledge)
            rules=json.loads((root/'config/rules.example.json').read_text())
            with engine.store.transaction() as db:
                for rule in rules:
                    r=validate_rule(rule)
                    if not db.execute('SELECT 1 FROM rules WHERE id=?',(r['id'],)).fetchone():engine.upsert_rule(db,r)
            _instance=Application(engine)
    return _instance(environ,start_response)
