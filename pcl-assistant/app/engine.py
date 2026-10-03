import json
import re
import time
import uuid
from datetime import datetime,timezone
from .clients import APIError,Clients
from .events import normalize,normalize_text,keyword_matches,valid_id
from .store import Store

SENSITIVE={
 'pricing':['قیمت','هزینه','نرخ','تعرفه','چند تومن','چند تومان','چقدر','price','cost','rate'],
 'discount':['تخفیف','discount'],
 'negotiation':['قرارداد','مذاکره','پرداخت','بودجه','budget','payment'],
 'collaboration':['همکاری','اسپانسر','شراکت','تبلیغات','collab','partnership','sponsor'],
 'project_inquiry':['سفارش','پروژه','تیزر','برام بساز','برای من بساز','project','proposal'],
 'complaint':['شکایت','ناراضی','کلاهبردار','افتضاح','complaint','refund','بازگشت وجه']}
RISKY_REPLY=re.compile(r'(تومان|تومن|ریال|دلار|درصد|تضمین|تضمینی|قول می|تحویل|آماده می|\$|\d+\s*(روز|ساعت|هفته))')
FALLBACK='برای اینکه دقیق راهنمایی‌ات کنیم، این پیام نیاز به بررسی تیم Persian Creative Lab دارد.'

class Engine:
    def __init__(self,settings,store=None,clients=None,clock=time.time,knowledge=None):
        self.s=settings;self.store=store or Store(settings.db_path);self.clients=clients or Clients(settings)
        self.clock=clock;self.knowledge=knowledge or {}
        # A process crash after a provider send is ambiguous, never replay the send automatically.
        with self.store.transaction() as db:
            stale=list(db.execute("SELECT id,event_id FROM outbox WHERE status='sending'"))
            db.execute("UPDATE outbox SET status='unknown_delivery',error='restart_during_send' WHERE status='sending'")
            for row in stale:self.alert(db,'restart_during_send',row['id'])

    def queue(self,db,key,channel,payload,event=None,approval=None):
        db.execute('INSERT OR IGNORE INTO outbox(id,channel,event_id,approval_id,payload) VALUES(?,?,?,?,?)',
                   (key,channel,event,approval,json.dumps(payload,ensure_ascii=False)))

    def alert(self,db,kind,ref):
        self.queue(db,'alert:'+kind+':'+ref,'telegram',{'method':'sendMessage','body':{
            'chat_id':self.s.owner_id,'text':f'PCL: {kind}\nشناسه: {ref}\nارسال مجدد نیاز به بررسی دارد.'}})

    def ingest(self,payload):
        now=self.clock();events=normalize(payload,self.s.account_id,now);count=0
        with self.store.transaction() as db:
            for e in events:
                cols=list(e);cur=db.execute(f"INSERT OR IGNORE INTO events({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",tuple(e.values()))
                if not cur.rowcount:continue
                count+=1
                db.execute('INSERT OR IGNORE INTO conversations(user_id) VALUES(?)',(e['user_id'],))
                db.execute('UPDATE conversations SET version=version+1,username=CASE WHEN ? != \'\' THEN ? ELSE username END,last_interaction=MAX(last_interaction,?),last_inbound=MAX(last_inbound,?) WHERE user_id=?',
                           (e['username'],e['username'],e['timestamp'],e['timestamp'] if e['kind']!='comment' else 0,e['user_id']))
                version=db.execute('SELECT version FROM conversations WHERE user_id=?',(e['user_id'],)).fetchone()['version']
                db.execute('UPDATE events SET conversation_version=? WHERE id=?',(version,e['id']))
                db.execute('INSERT INTO messages(event_id,user_id,role,text,timestamp) VALUES(?,?,?,?,?)',(e['id'],e['user_id'],'user',e['text'],e['timestamp']))
                Store.audit(db,now,e['id'],'event_received',{'kind':e['kind']})
        return {'accepted':count}

    def claim(self):
        now=self.clock();jobs=[]
        with self.store.transaction() as db:
            rows=list(db.execute("SELECT id FROM events WHERE (status='pending' OR (status='processing' AND lease_until<?)) AND attempts<3 ORDER BY created,rowid LIMIT 3",(now,)))
            for row in rows:
                lease=uuid.uuid4().hex
                db.execute("UPDATE events SET status='processing',lease=?,lease_until=?,attempts=attempts+1 WHERE id=?",(lease,now+120,row['id']))
                jobs.append({'event_id':row['id'],'lease':lease})
        return {'jobs':jobs}

    def context(self,user):
        rows=self.store.rows('SELECT role,text FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?',(user,self.s.context_limit))
        return list(reversed(rows))

    def decision(self,e):
        text=normalize_text(e['text']);context=self.context(e['user_id'])
        for category,words in SENSITIVE.items():
            if any(keyword_matches(text,w) for w in words):
                return category,1.,FALLBACK,True
        # Prior sensitive discussion / pending handoff keeps follow-ups with the owner.
        conv=self.store.one('SELECT * FROM conversations WHERE user_id=?',(e['user_id'],))
        if conv['pending']:return conv['intent'] or 'unknown',1.,FALLBACK,True
        if e['kind']=='unsupported':return 'unknown',0.,FALLBACK,True
        rules=self.store.rows('SELECT * FROM rules WHERE active=1 AND trigger=? AND media_id IN (?,\'*\') ORDER BY (media_id=?) DESC,priority DESC,id',
                              (e['kind'],e['media_id'],e['media_id']))
        for r in rules:
            if keyword_matches(text,r['keyword']):
                with self.store.transaction() as db:Store.audit(db,self.clock(),e['id'],'rule_matched',{'rule_id':r['id']})
                return 'prompt',1.,r['response'],bool(r['approval']) or bool(RISKY_REPLY.search(r['response']))
        if e['kind']=='comment':return 'ignored',1.,'',False
        if text in ('سلام','سلام خوبی','hi','hello','درود'):
            return 'greeting',1.,'سلام 👋 من دستیار هوشمند Persian Creative Lab هستم. دربارهٔ آموزش AI، پرامپت یا تولید محتوا چطور می‌تونم کمکت کنم؟',False
        if len(e['text'])>1500:return 'unknown',0.,FALLBACK,True
        day=datetime.fromtimestamp(self.clock(),timezone.utc).strftime('%Y-%m-%d')
        with self.store.transaction() as db:
            db.execute('INSERT OR IGNORE INTO usage(day) VALUES(?)',(day,))
            if db.execute('SELECT calls FROM usage WHERE day=?',(day,)).fetchone()['calls']>=self.s.ai_daily_limit:return 'unknown',0.,FALLBACK,True
            db.execute('UPDATE usage SET calls=calls+1 WHERE day=?',(day,))
        try:d=self.clients.ai(e,context,self.knowledge)
        except APIError:
            with self.store.transaction() as db:Store.audit(db,self.clock(),e['id'],'ai_unavailable')
            return 'unknown',0.,FALLBACK,True
        facts=d['fact_ids'];supported=bool(facts) and all(f in self.knowledge for f in facts)
        approval=(d['needs_approval'] or d['missing_information'] or d['category'] in SENSITIVE
                  or d['category']=='unknown' or d['confidence']<self.s.confidence or not supported
                  or bool(RISKY_REPLY.search(d['reply'])))
        # Returned URLs must occur verbatim in trusted knowledge, never generated from the user's text.
        known=json.dumps(self.knowledge,ensure_ascii=False)
        if any(url not in known for url in re.findall(r'https?://[^\s<>]+',d['reply'])):approval=True
        with self.store.transaction() as db:Store.audit(db,self.clock(),e['id'],'ai_generated',{'category':d['category'],'confidence':d['confidence']})
        return d['category'],d['confidence'],d['reply'],approval

    def process(self,event_id,lease):
        e=self.store.one("SELECT * FROM events WHERE id=? AND status='processing' AND lease=?",(event_id,lease))
        if not e:return {'status':'not_claimed'}
        if e['kind']=='comment' and not e['timestamp'] and self.s.meta_token:
            try:
                ts=self.clients.comment_time(e)
                if not 0<ts<=self.clock()+60:raise APIError('invalid_timestamp')
                e['timestamp']=ts
                with self.store.transaction() as db:db.execute('UPDATE events SET timestamp=? WHERE id=?',(ts,e['id']))
            except APIError:pass
        conv=self.store.one('SELECT * FROM conversations WHERE user_id=?',(e['user_id'],));cv=conv['version']
        if e['kind']!='comment' and e['conversation_version']!=cv:
            with self.store.transaction() as db:
                db.execute("UPDATE events SET status='superseded' WHERE id=?",(event_id,))
            return {'status':'superseded'}
        category,confidence,reply,approval=self.decision(e)
        now=self.clock()
        if e['kind']=='comment' and not e['timestamp'] and category!='ignored':approval=True
        with self.store.transaction() as db:
            row=db.execute("SELECT status,lease FROM events WHERE id=?",(event_id,)).fetchone()
            if row['status']!='processing' or row['lease']!=lease:return {'status':'lease_changed'}
            current=db.execute('SELECT version FROM conversations WHERE user_id=?',(e['user_id'],)).fetchone()['version']
            if current!=cv:
                db.execute("UPDATE events SET status='pending',attempts=0 WHERE id=?",(event_id,));return {'status':'context_changed'}
            state={'project_inquiry':'project inquiry','service':'interested','pricing':'warm lead','collaboration':'warm lead'}.get(category,'new')
            if category=='ignored':
                db.execute("UPDATE events SET status='ignored' WHERE id=?",(event_id,));return {'status':'ignored'}
            if not reply.strip() or len(reply.encode())>1000:reply=FALLBACK;approval=True
            db.execute('UPDATE events SET category=?,confidence=?,draft=?,status=? WHERE id=?',(category,confidence,reply,'awaiting_approval' if approval else 'decided',event_id))
            db.execute('UPDATE conversations SET intent=?,lead_state=CASE WHEN lead_state IN (\'customer\',\'closed\') THEN lead_state ELSE ? END,pending=? WHERE user_id=?',
                       (category,'awaiting approval' if approval else state,int(approval),e['user_id']))
            Store.audit(db,now,event_id,'intent_detected',{'category':category,'confidence':confidence})
            if approval:
                # New context supersedes any older draft, including a previously approved but unsent reply.
                db.execute("UPDATE approvals SET status='superseded' WHERE user_id=? AND status IN ('pending','editing','approved')",(e['user_id'],))
                aid=uuid.uuid4().hex[:20]
                db.execute('INSERT INTO approvals(id,event_id,user_id,draft,category,confidence,conversation_version,expires) VALUES(?,?,?,?,?,?,?,?)',
                           (aid,event_id,e['user_id'],reply,category,confidence,cv,now+self.s.approval_ttl))
                self.approval_notice(db,aid)
                Store.audit(db,now,event_id,'approval_requested',{'approval_id':aid})
            else:self.queue(db,'ig:'+event_id,'instagram',{'text':reply,'conversation_version':cv},event_id)
        return {'status':'awaiting_approval' if approval else 'queued'}

    def approval_notice(self,db,aid):
        a=dict(db.execute('SELECT * FROM approvals WHERE id=?',(aid,)).fetchone())
        e=dict(db.execute('SELECT * FROM events WHERE id=?',(a['event_id'],)).fetchone())
        context=self.context(e['user_id'])[-5:]
        text=(f"PCL | @{e['username'] or '(نام کاربری موجود نیست)'} | ID {e['user_id']}\n"
              f"دسته: {a['category']} | اطمینان: {a['confidence']:.0%}\n"
              f"پیام: {e['text'][:800]}\n\nپیشنهاد:\n{a['draft']}\n\n"
              +'زمینه:\n'+'\n'.join(f"{m['role']}: {m['text'][:220]}" for m in context))[:3900]
        buttons=[[{'text':label,'callback_data':f'{action}:{aid}:{a["version"]}'} for action,label in [('approve','تأیید'),('edit','ویرایش'),('reject','رد')]],
                 [{'text':'پاسخ دلخواه','callback_data':f'custom:{aid}:{a["version"]}'}]]
        self.queue(db,f'tg:approval:{aid}:{a["version"]}','telegram',{'method':'sendMessage','body':{'chat_id':self.s.owner_id,'text':text,'reply_markup':{'inline_keyboard':buttons}},'save_as':'approval'},a['event_id'],aid)

    def receive_telegram(self,update):
        if not isinstance(update,dict) or type(update.get('update_id')) is not int:raise ValueError('Invalid update')
        with self.store.transaction() as db:db.execute('INSERT OR IGNORE INTO telegram_updates(id,payload) VALUES(?,?)',(update['update_id'],json.dumps(update,ensure_ascii=False)))
        return {'accepted':True}

    def telegram_process(self):
        count=0
        with self.store.transaction() as db:
            for row in list(db.execute("SELECT * FROM telegram_updates WHERE status='pending' ORDER BY id LIMIT 20")):
                u=json.loads(row['payload']);cq=u.get('callback_query') or {};m=cq.get('message') or u.get('message') or {};frm=cq.get('from') or m.get('from') or {}
                if (not self.s.owner_id or str(frm.get('id'))!=self.s.owner_id or str(m.get('chat',{}).get('id'))!=self.s.owner_id
                    or m.get('chat',{}).get('type')!='private' or frm.get('is_bot')):
                    db.execute("UPDATE telegram_updates SET status='unauthorized' WHERE id=?",(row['id'],));continue
                if cq:
                    self.queue(db,'tg:callback:'+str(row['id']),'telegram',{'method':'answerCallbackQuery','body':{'callback_query_id':cq['id']}})
                    self.callback(db,cq,m)
                elif isinstance(m.get('text'),str):self.owner_message(db,m,row['id'])
                db.execute("UPDATE telegram_updates SET status='done' WHERE id=?",(row['id'],));count+=1
        return {'processed':count}

    def callback(self,db,cq,m):
        match=re.fullmatch(r'(approve|reject|edit|custom):([a-f0-9]{20}):([1-9]\d{0,5})',cq.get('data',''))
        if not match:return
        action,aid,version=match.groups();a=db.execute('SELECT * FROM approvals WHERE id=?',(aid,)).fetchone()
        if not a or a['status']!='pending' or a['version']!=int(version) or a['telegram_message_id']!=m.get('message_id'):return
        now=self.clock();conv=db.execute('SELECT * FROM conversations WHERE user_id=?',(a['user_id'],)).fetchone()
        if a['expires']<=now or conv['version']!=a['conversation_version']:
            db.execute("UPDATE approvals SET status='expired' WHERE id=?",(aid,));self.refresh_pending(db,a['user_id']);return
        if action=='reject':
            db.execute("UPDATE approvals SET status='rejected' WHERE id=?",(aid,))
            db.execute("UPDATE events SET status='rejected' WHERE id=?",(a['event_id'],))
            self.refresh_pending(db,a['user_id'])
        elif action=='approve':
            db.execute("UPDATE approvals SET status='approved' WHERE id=?",(aid,))
            self.queue(db,'ig:'+a['event_id'],'instagram',{'text':a['draft'],'conversation_version':conv['version']},a['event_id'],aid)
        else:
            db.execute("UPDATE approvals SET status='editing' WHERE id=?",(aid,))
            self.queue(db,f'tg:edit:{aid}:{version}','telegram',{'method':'sendMessage','body':{
                'chat_id':self.s.owner_id,'text':'پاسخ جدید را با Reply به همین پیام بفرست؛ بعد پیش‌نمایش را تأیید کن.',
                'reply_markup':{'force_reply':True}},'save_as':'edit'},a['event_id'],aid)
        Store.audit(db,now,a['event_id'],'approval_result',{'action':action,'approval_id':aid})

    def refresh_pending(self,db,user):
        pending=db.execute("SELECT 1 FROM approvals WHERE user_id=? AND status IN ('pending','editing','approved') LIMIT 1",(user,)).fetchone()
        db.execute('UPDATE conversations SET pending=?,lead_state=CASE WHEN lead_state=\'awaiting approval\' THEN \'warm lead\' ELSE lead_state END WHERE user_id=?',(int(bool(pending)),user))

    def owner_message(self,db,m,update_id):
        reply_id=m.get('reply_to_message',{}).get('message_id');text=m['text'];now=self.clock()
        if reply_id:
            a=db.execute("SELECT * FROM approvals WHERE edit_prompt_id=? AND status='editing'",(reply_id,)).fetchone()
            if a and a['expires']>now and 0<len(text.strip().encode())<=1000:
                conv=db.execute('SELECT version FROM conversations WHERE user_id=?',(a['user_id'],)).fetchone()
                if conv['version']==a['conversation_version']:
                    db.execute("UPDATE approvals SET draft=?,version=version+1,status='pending',telegram_message_id=NULL,edit_prompt_id=NULL WHERE id=?",(text,a['id']))
                    self.approval_notice(db,a['id']);return
        response=self.command(db,text)
        self.queue(db,'tg:command:'+str(update_id),'telegram',{'method':'sendMessage','body':{'chat_id':self.s.owner_id,'text':response}})

    def command(self,db,text):
        if text=='/pause':
            db.execute("INSERT OR REPLACE INTO controls VALUES('paused','true')");return 'ارسال متوقف شد.'
        if text=='/resume':
            db.execute("INSERT OR REPLACE INTO controls VALUES('paused','false')");return 'توقف دستی برداشته شد؛ تنظیمات ایمنی همچنان اعمال می‌شوند.'
        if text=='/rules':
            rows=list(db.execute('SELECT * FROM rules ORDER BY id LIMIT 30'))
            return '\n'.join(f"{r['id']} | {r['trigger']} | {r['media_id']} | {r['keyword']} | {'فعال' if r['active'] else 'خاموش'}" for r in rows) or 'هنوز قانونی ثبت نشده.'
        # Owner data entry is conversational, never application-source editing.
        if text.startswith('/rule\n'):
            try:
                fields=dict(line.split(':',1) for line in text.splitlines()[1:] if ':' in line)
                fields={k.strip():v.strip() for k,v in fields.items()}
                rule=validate_rule({'id':fields['id'],'trigger':fields['trigger'],'media_id':fields.get('post','*'),
                    'keyword':fields['keyword'],'response':fields['reply'],'approval':fields.get('approval','no')=='yes','active':True,'priority':0})
                self.upsert_rule(db,rule);return 'قانون ذخیره شد: '+rule['id']
            except (KeyError,ValueError):return 'قانون ناقص است. /help قالب را نشان می‌دهد.'
        if text.startswith(('/off ','/on ')):
            cmd,key=text.split(' ',1);db.execute('UPDATE rules SET active=? WHERE id=?',(int(cmd=='/on'),key));return 'وضعیت قانون به‌روزرسانی شد.'
        if text.startswith('/lead '):
            parts=text.split(' ',2)
            if len(parts)==3 and valid_id(parts[1]) and parts[2] in LEADS:
                db.execute('UPDATE conversations SET lead_state=? WHERE user_id=?',(parts[2],parts[1]));return 'وضعیت مخاطب ثبت شد.'
        if text=='/status':
            rows=list(db.execute('SELECT status,COUNT(*) AS n FROM outbox GROUP BY status'))
            return f"حالت آزمایشی: {self.s.dry_run}\nارسال فعال: {self.s.outbound_enabled}\n"+'\n'.join(f"{r['status']}: {r['n']}" for r in rows)
        return ('/pause توقف ارسال\n/resume ادامه\n/rules قوانین\n/on ID و /off ID\n/status وضعیت\n'
                '/lead USER_ID customer\nقانون جدید:\n/rule\nid: lawyer-reel\ntrigger: comment\npost: شناسه عددی ریلز\nkeyword: وکیل\nreply: متن پاسخ\napproval: no\n'
                'برای استوری trigger: story و post: شناسه استوری. برای دایرکت trigger: dm و post: *')

    @staticmethod
    def upsert_rule(db,r):
        db.execute('INSERT INTO rules(id,trigger,media_id,keyword,response,approval,active,priority) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET trigger=excluded.trigger,media_id=excluded.media_id,keyword=excluded.keyword,response=excluded.response,approval=excluded.approval,active=excluded.active,priority=excluded.priority',
                   tuple(r[k] for k in ['id','trigger','media_id','keyword','response','approval','active','priority']))

    def dispatch(self):
        processed=0
        for _ in range(2):
            now=self.clock()
            with self.store.transaction() as db:
                row=db.execute("SELECT * FROM outbox WHERE status='pending' AND next_at<=? ORDER BY rowid LIMIT 1",(now,)).fetchone()
                if not row:break
                r=dict(row);p=json.loads(r['payload']);e=None
                if r['channel']=='instagram':
                    paused=db.execute("SELECT value FROM controls WHERE key='paused'").fetchone()
                    if not self.s.outbound_enabled or (paused and paused['value']=='true'):
                        db.execute('UPDATE outbox SET next_at=? WHERE id=?',(now+30,r['id']));continue
                    e=dict(db.execute('SELECT * FROM events WHERE id=?',(r['event_id'],)).fetchone())
                    conv=db.execute('SELECT * FROM conversations WHERE user_id=?',(e['user_id'],)).fetchone()
                    valid=conv['version']==p['conversation_version']
                    if r['approval_id']:
                        a=db.execute('SELECT * FROM approvals WHERE id=?',(r['approval_id'],)).fetchone()
                        valid=valid and a['status']=='approved' and a['expires']>now and a['draft']==p['text']
                    window=e['timestamp'] if e['kind']=='comment' else conv['last_inbound']
                    duration=7*86400 if e['kind']=='comment' else 86400
                    if not valid or not window or not 0<=now-window<duration-60:
                        db.execute("UPDATE outbox SET status='blocked',error='stale_or_expired' WHERE id=?",(r['id'],))
                        if r['approval_id']:db.execute("UPDATE approvals SET status='expired' WHERE id=?",(r['approval_id'],));self.refresh_pending(db,e['user_id'])
                        self.alert(db,'stale_or_expired',r['id']);continue
                    sent=db.execute("SELECT COUNT(*) AS n FROM outbox WHERE channel='instagram' AND sent_at>?",(now-60,)).fetchone()['n']
                    if sent>=self.s.send_per_minute:
                        db.execute('UPDATE outbox SET next_at=? WHERE id=?',(now+15,r['id']));continue
                    if not self.s.dry_run and (not self.s.meta_verified or not self.s.meta_token):
                        db.execute('UPDATE outbox SET next_at=? WHERE id=?',(now+60,r['id']));continue
                elif not self.s.telegram_token:
                    db.execute('UPDATE outbox SET next_at=? WHERE id=?',(now+60,r['id']));continue
                if r['channel']=='telegram' and p.get('save_as')=='approval':
                    a=db.execute('SELECT * FROM approvals WHERE id=?',(r['approval_id'],)).fetchone()
                    v=int(r['id'].rsplit(':',1)[-1])
                    if not a or a['status']!='pending' or a['version']!=v or a['expires']<=now:
                        db.execute("UPDATE outbox SET status='blocked',error='stale_approval' WHERE id=?",(r['id'],));continue
                db.execute("UPDATE outbox SET status='sending',started_at=?,attempts=attempts+1 WHERE id=?",(now,r['id']))
            try:
                if e:
                    provider='simulated' if self.s.dry_run else self.clients.instagram(e,p['text'])
                    result={}
                else:
                    result=self.clients.telegram(p['method'],p['body']);provider=str(result.get('message_id','callback')) if isinstance(result,dict) else 'callback'
                status='simulated' if e and self.s.dry_run else 'sent';error=None
            except APIError as err:
                status='pending' if err.kind=='rate_limit' and r['attempts']<4 else ('unknown_delivery' if err.kind=='unknown_delivery' else 'failed')
                error=err.kind;provider=None;result={};retry=err.retry_after or 30
            except Exception:
                status='unknown_delivery';error='unexpected_provider_response';provider=None;result={}
            with self.store.transaction() as db:
                db.execute('UPDATE outbox SET status=?,provider_id=?,error=?,sent_at=?,next_at=? WHERE id=?',
                           (status,provider,error,now if status in ('sent','simulated') else None,now+retry if status=='pending' else 0,r['id']))
                Store.audit(db,now,r['event_id'],'message_sent' if status=='sent' else 'send_'+status,{'channel':r['channel'],'error':error})
                if e and status in ('sent','simulated'):
                    db.execute('INSERT INTO messages(event_id,user_id,role,text,timestamp) VALUES(?,?,?,?,?)',(e['id'],e['user_id'],'human' if r['approval_id'] else 'assistant',p['text'],now))
                    db.execute('UPDATE conversations SET last_response=? WHERE user_id=?',(p['text'],e['user_id']))
                    db.execute('UPDATE events SET status=? WHERE id=?',(status,e['id']))
                    if r['approval_id']:db.execute('UPDATE approvals SET status=? WHERE id=?',(status,r['approval_id']));self.refresh_pending(db,e['user_id'])
                if not e and status=='sent' and p.get('save_as') and isinstance(result,dict):
                    column='telegram_message_id' if p['save_as']=='approval' else 'edit_prompt_id'
                    db.execute(f'UPDATE approvals SET {column}=? WHERE id=?',(result['message_id'],r['approval_id']))
                if e and status in ('failed','unknown_delivery'):self.alert(db,error or status,r['id'])
            processed+=1
        return {'processed':processed}

    def maintenance(self):
        now=self.clock();cutoff=now-self.s.retention_days*86400
        with self.store.transaction() as db:
            stuck=list(db.execute("SELECT id FROM outbox WHERE status='sending' AND started_at<?",(now-120,)))
            for r in stuck:
                db.execute("UPDATE outbox SET status='unknown_delivery',error='send_lease_expired' WHERE id=?",(r['id'],))
                self.alert(db,'send_lease_expired',r['id'])
            users=[r['user_id'] for r in db.execute("SELECT DISTINCT user_id FROM approvals WHERE expires<=? AND status IN ('pending','editing','approved')",(now,))]
            db.execute("UPDATE approvals SET status='expired' WHERE expires<=? AND status IN ('pending','editing','approved')",(now,))
            for u in users:self.refresh_pending(db,u)
            exhausted=list(db.execute("SELECT id FROM events WHERE status='processing' AND lease_until<? AND attempts>=3",(now,)))
            for e in exhausted:
                db.execute("UPDATE events SET status='failed' WHERE id=?",(e['id'],));self.alert(db,'processing_failed',e['id'])
            db.execute('DELETE FROM messages WHERE timestamp<?',(cutoff,))
            db.execute('DELETE FROM audit WHERE timestamp<?',(cutoff,))
            db.execute("DELETE FROM telegram_updates WHERE status!='pending'")
            # Keep compact dedup tombstones, redact old content (Meta retry protection survives retention).
            db.execute("UPDATE events SET text='',draft='',username='' WHERE created<? AND status NOT IN ('pending','processing','awaiting_approval')",(cutoff,))
            db.execute("UPDATE approvals SET draft='' WHERE expires<? AND status NOT IN ('pending','editing','approved')",(cutoff,))
            db.execute("UPDATE outbox SET payload='{}' WHERE status IN ('sent','simulated','blocked','failed') AND event_id IN (SELECT id FROM events WHERE created<?)",(cutoff,))
            db.execute("UPDATE conversations SET username='',last_response=NULL WHERE last_interaction<? AND pending=0",(cutoff,))
        return {'ok':True}

LEADS={'new','interested','warm lead','project inquiry','awaiting approval','customer','closed'}
def validate_rule(r):
    if not isinstance(r,dict):raise ValueError('Invalid rule')
    out={**{'media_id':'*','approval':False,'active':True,'priority':0},**r}
    if not isinstance(out.get('id'),str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',out['id']):raise ValueError('Invalid rule ID')
    if out.get('trigger') not in ('dm','story','comment'):raise ValueError('Invalid trigger')
    if out['media_id']!='*' and not valid_id(out['media_id']):raise ValueError('Invalid media ID')
    if out['trigger']=='comment' and out['media_id']=='*':raise ValueError('Comment rules must target a post')
    if not isinstance(out.get('keyword'),str) or not normalize_text(out['keyword']) or len(out['keyword'])>100:raise ValueError('Invalid keyword')
    if not isinstance(out.get('response'),str) or not out['response'].strip() or len(out['response'].encode())>1000:raise ValueError('Response exceeds 1000 UTF-8 bytes')
    if type(out['approval']) is not bool or type(out['active']) is not bool or type(out['priority']) is not int:raise ValueError('Invalid flags')
    return out
