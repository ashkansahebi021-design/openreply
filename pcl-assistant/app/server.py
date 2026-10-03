"""WSGI ingress: signature verified on original bytes before JSON decoding."""
import hmac
import json
import threading
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from .settings import Settings
from .engine import Engine,validate_rule
from .events import verify_signature
from .clients import APIError

class Application:
    def __init__(self,engine):self.engine=engine;self.dispatch_lock=threading.Lock();self.telegram_lock=threading.Lock();self.ai_check_lock=threading.Lock()

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
            try:
                with self.engine.store.transaction() as db:
                    self.engine.alert(db,'internal_error',str(int(self.engine.clock()//60)))
            except Exception:pass
        body=(result if plain else json.dumps(result,ensure_ascii=False)).encode()
        start_response(f'{status} '+{200:'OK',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',413:'Payload Too Large',500:'Internal Server Error'}[status],
                       [('Content-Type','text/plain; charset=utf-8' if plain else 'application/json; charset=utf-8'),('Content-Length',str(len(body))),('Cache-Control','no-store')])
        return [body]

    def internal(self,path,method,data):
        e=self.engine
        if method=='GET' and path=='/internal/status':
            counts={}
            for table in ('events','telegram_updates'):
                counts[table]={r['status']:r['count'] for r in e.store.rows(f'SELECT status,COUNT(*) AS count FROM {table} GROUP BY status')}
            counts['outbox']=e.store.rows('SELECT channel,status,COUNT(*) AS count FROM outbox GROUP BY channel,status')
            return {'queues':counts,'scheduler':{r['key'].removeprefix('scheduler:'):float(r['value']) for r in
                e.store.rows("SELECT key,value FROM controls WHERE key LIKE 'scheduler:%'")},
                'integrations_configured':{'telegram':bool(e.s.telegram_token),'openai':bool(e.s.openai_key),'meta':bool(e.s.meta_token)},
                'public_telegram_enabled':e.s.public_telegram_enabled,'ai_daily_call_limit':e.s.ai_daily_limit,
                'dry_run':e.s.dry_run,'instagram_outbound_enabled':e.s.outbound_enabled,'meta_verified':e.s.meta_verified}
        if method=='POST' and path=='/internal/openai/check':
            # Fixed synthetic input, no conversation/outbox side effects or secret exposure.
            if not e.s.openai_key:return {'ok':False,'error':'openai_not_configured'}
            day=datetime.fromtimestamp(e.clock(),timezone.utc).date().isoformat()
            key='openai-check:'+day+':'+e.s.model
            with self.ai_check_lock:
                with e.store.transaction() as db:
                    old=db.execute('SELECT value FROM controls WHERE key=?',(key,)).fetchone()
                    if old:
                        previous=json.loads(old['value'])
                        if previous.get('ok') or previous.get('error')=='check_pending_or_interrupted' or previous.get('retry_at',0)>e.clock():return previous
                    db.execute('INSERT OR IGNORE INTO usage(day) VALUES(?)',(day,))
                    if db.execute('SELECT calls FROM usage WHERE day=?',(day,)).fetchone()['calls']>=e.s.ai_daily_limit:
                        return {'ok':False,'error':'ai_budget_exhausted'}
                    db.execute('UPDATE usage SET calls=calls+1 WHERE day=?',(day,))
                    # Reserve before network I/O: a crash must not cause blind repeat spending.
                    db.execute('INSERT INTO controls(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps({'ok':False,'error':'check_pending_or_interrupted'})))
                try:
                    decision=e.clients.ai({'text':'Persian Creative Lab چه کاری انجام می‌دهد؟','kind':'dm'},[],e.knowledge)
                    result={'ok':True,'model':e.s.model,'category':decision['category'],'reply':decision['reply']}
                except APIError as error:
                    result={'ok':False,'error':error.kind,'model':e.s.model,'retry_at':e.clock()+max(60,error.retry_after)}
                with e.store.transaction() as db:
                    db.execute('UPDATE controls SET value=? WHERE key=?',(json.dumps(result,ensure_ascii=False),key))
                    # Keep only the most recent commissioning check, including across model changes.
                    db.execute("DELETE FROM controls WHERE key LIKE 'openai-check:%' AND key<>?",(key,))
                return result
        if method=='POST' and path in ('/internal/jobs/claim','/internal/telegram/process','/internal/outbox/dispatch','/internal/maintenance'):
            # Bounded heartbeat state, not one growing audit row per five-second poll.
            with e.store.transaction() as db:
                db.execute('INSERT INTO controls(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                    ('scheduler:'+path.removeprefix('/internal/'),str(e.clock())))
        if method=='POST' and path=='/internal/telegram/commission':
            # Runtime uses its own secret; the engineering client never reads the bot token.
            url=e.s.public_base_url.rstrip('/');parts=urlsplit(url)
            expected=data.get('expected_username','')
            if (parts.scheme!='https' or not parts.hostname or parts.username or parts.password
                or parts.port not in (None,443) or parts.path or parts.query or parts.fragment
                or not e.s.telegram_secret or not e.s.owner_id or not expected):
                raise ValueError('invalid_commission_configuration')
            bot=e.clients.telegram('getMe',{})
            if bot.get('username')!=expected or not bot.get('is_bot'):
                raise ValueError('unexpected_bot')
            e.clients.telegram('setWebhook',{'url':url+'/webhooks/telegram',
                'secret_token':e.s.telegram_secret,'allowed_updates':['message','callback_query'],
                'drop_pending_updates':False})
            with e.store.transaction() as db:
                e.queue(db,'telegram-commission:'+str(bot['id']),'telegram',{'method':'sendMessage','body':{
                    'chat_id':e.s.owner_id,'text':'اشکان، اتصال آزمایشی تلگرام PCL آماده است. برای بررسی وضعیت /status را بفرست. اتصال اینستاگرام هنوز فعال نشده است.'}})
            return {'ok':True,'bot_username':bot['username']}
        if method=='POST' and path=='/internal/jobs/claim':return e.claim()
        if method=='POST' and path=='/internal/events/process':return e.process(data['event_id'],data['lease'])
        if method=='POST' and path=='/internal/telegram/process':
            with self.telegram_lock:return e.telegram_process()
        if method=='POST' and path=='/internal/outbox/dispatch':
            with self.dispatch_lock:return e.dispatch()
        if method=='POST' and path=='/internal/maintenance':return e.maintenance()
        if method=='POST' and path=='/internal/prompts':
            with e.store.transaction() as db:saved=e.public.catalog.save(db,data)
            return {'saved':saved}
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
