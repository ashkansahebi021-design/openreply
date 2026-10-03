"""Public PCL FAQ and inquiry channel. No model calls or owner permissions."""
import json
import re
import uuid
from .events import normalize_text,keyword_matches
from .store import Store

WELCOME=('سلام 👋 به Persian Creative Lab خوش اومدی.\n'
         'کمک می‌کنیم با AI و ابزارهای خلاقانه، محتوای بهتر و حرفه‌ای‌تر بسازی.\n'
         'اینجا می‌تونی دربارهٔ خدمات، آموزش یا سفارش پروژه پیام بدی.\n'
         'فعلاً پاسخ‌های آماده فعال‌اند؛ سؤال‌های اختصاصی برای بررسی به تیم می‌رسند.\n'
         'این ربات در حال حاضر چت آزاد ChatGPT نیست.\n\n'
         '/services خدمات\n/tutorial آموزش و پرامپت\n/project درخواست پروژه\n/human گفت‌وگو با تیم\n/privacy حریم خصوصی')
SERVICES='تمرکز Persian Creative Lab آموزش کاربردی AI و اجرای پروژه‌های تولید محتوای خلاقانه است. برای بررسی پروژهٔ خودت، نوع محتوا و هدفت را بنویس. قیمت و شرایط را تیم پس از بررسی اعلام می‌کند.'
SERVICE_COMMANDS={'/services','/about'}
SERVICE_PHRASES={'خدمات','درباره ما','خدمات شما چیست','چه خدماتی دارید'}
MENUS={'/start','/help','/menu'}
OWNER_COMMANDS={'/status','/pause','/resume','/rules','/rule','/lead','/on','/off','/public','/tgfaq','/tgfaqs','/tgreply'}

class PublicTelegram:
    def __init__(self,engine):self.e=engine

    def send(self,db,key,user,text,**extra):
        self.e.queue(db,key,'telegram',{'method':'sendMessage','body':{'chat_id':user,'text':text},**extra})

    def receive(self,db,m,update_id,sensitive,risky_reply):
        e=self.e;frm=m.get('from') or {};chat=m.get('chat') or {};user=str(frm.get('id',''))
        if (not e.s.public_telegram_enabled or not e.s.owner_id or not user.isdigit() or int(user)<=0
            or str(chat.get('id'))!=user or chat.get('type')!='private' or frm.get('is_bot')):return False
        now=e.clock()
        if not db.execute('INSERT OR IGNORE INTO public_receipts VALUES(?,?,?)',(update_id,user,now)).rowcount:return True
        count=db.execute('SELECT COUNT(*) AS n FROM public_receipts WHERE user_id=? AND created>?',(user,now-3600)).fetchone()['n']
        burst=db.execute('SELECT COUNT(*) AS n FROM public_receipts WHERE user_id=? AND created>?',(user,now-60)).fetchone()['n']
        if count>30 or burst>5:
            self.send(db,f'public:limit:{user}:{int(now//3600)}',user,'تعداد پیام‌ها زیاد شده؛ لطفاً کمی بعد دوباره پیام بده.')
            return True
        if db.execute('SELECT COUNT(*) AS n FROM public_receipts WHERE created>?',(now-now%86400,)).fetchone()['n']>500:
            self.send(db,f'public:daily-limit:{user}:{int(now//86400)}',user,'ظرفیت پاسخ‌گویی امروز تکمیل شده؛ لطفاً بعداً دوباره پیام بده.')
            return True
        username=str(frm.get('username') or '')[:64]
        db.execute('INSERT INTO public_users(user_id,username,last_interaction) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,last_interaction=excluded.last_interaction',(user,username,now))
        text=m.get('text');key='public:response:'+str(update_id)
        if not isinstance(text,str) or not text.strip():
            self.send(db,key,user,'فعلاً لطفاً سؤال یا درخواستت را به‌صورت متن بفرست.');return True
        text=text.strip()
        if len(text.encode())>4000:
            self.send(db,key,user,'لطفاً پیام را کوتاه‌تر بفرست تا بتوانیم بررسی کنیم.');return True
        cmd=text.split()[0].split('@')[0]
        if cmd in OWNER_COMMANDS:
            self.send(db,key,user,'این دستور مخصوص مدیر است. برای راهنمایی /help را بفرست.');return True
        db.execute('INSERT INTO public_messages(user_id,role,text,created) VALUES(?,?,?,?)',(user,'user',text,now))
        if cmd in MENUS or normalize_text(text) in ('سلام','درود','hi','hello'):
            self.send(db,key,user,WELCOME);return True
        if cmd=='/privacy':
            self.send(db,key,user,'برای پیگیری درخواست، شناسهٔ تلگرام، نام کاربری و پیام‌ها در سامانهٔ PCL ذخیره و با مدیر به اشتراک گذاشته می‌شوند. متن گفتگوها معمولاً تا ۳۰ روز نگهداری می‌شود؛ رسیدهای بدون متن برای جلوگیری از ارسال تکراری باقی می‌مانند. اطلاعات بانکی، رمز یا کلید API نفرست.');return True
        category=next((c for c,words in sensitive.items() if any(keyword_matches(text,w) for w in words)),None)
        pending=db.execute("SELECT * FROM public_tickets WHERE user_id=? AND status IN ('pending','editing','approved') ORDER BY updated DESC LIMIT 1",(user,)).fetchone()
        # Menu requests do not modify a pending commercial inquiry or its draft.
        if not category and (cmd in SERVICE_COMMANDS or normalize_text(text) in SERVICE_PHRASES):
            self.send(db,key,user,SERVICES);return True
        if not category and not pending:
            faq=db.execute('SELECT response FROM public_faqs WHERE keyword=? AND active=1',(normalize_text(text),)).fetchone()
            if faq:
                if not risky_reply.search(faq['response']):
                    self.send(db,key,user,faq['response']);return True
                category='unknown'
        if cmd=='/project':category='project_inquiry'
        elif cmd=='/tutorial':category='tutorial'
        elif cmd=='/human':category='human'
        category=category or (pending['category'] if pending else 'unknown')
        if pending:
            tid=pending['id'];version=pending['version']+1
            db.execute("UPDATE public_tickets SET category=?,status='pending',version=?,updated=?,notice_id=NULL,edit_prompt_id=NULL,draft='' WHERE id=?",(category,version,now,tid))
        else:
            tid=uuid.uuid4().hex[:20];version=1
            db.execute('INSERT INTO public_tickets(id,user_id,category,created,updated) VALUES(?,?,?,?,?)',(tid,user,category,now,now))
        db.execute("UPDATE public_users SET lead_state='awaiting approval' WHERE user_id=?",(user,))
        self.notice(db,tid)
        self.send(db,key,user,'پیامت برای بررسی به تیم PCL رسید. اگر درخواست پروژه داری، نوع محتوا، هدف و توضیحات لازم را همین‌جا بنویس؛ جزئیات به درخواستت اضافه می‌شود.')
        Store.audit(db,now,'public:'+tid,'public_inquiry_received',{'category':category,'version':version})
        return True

    def notice(self,db,tid):
        t=db.execute('SELECT * FROM public_tickets WHERE id=?',(tid,)).fetchone()
        user=db.execute('SELECT * FROM public_users WHERE user_id=?',(t['user_id'],)).fetchone()
        rows=list(db.execute('SELECT role,text FROM public_messages WHERE user_id=? ORDER BY id DESC LIMIT 5',(t['user_id'],)))
        context='\n'.join(f"{r['role']}: {r['text'][:500]}" for r in reversed(rows))
        text=f"PCL | مخاطب تلگرام @{user['username'] or '(بدون نام کاربری)'}\nدرخواست: {tid}\nدسته: {t['category']}\nپاسخ هوش مصنوعی تولید نشده؛ پاسخ تیم لازم است.\n\n{context}"
        self.e.queue(db,f"public:notice:{tid}:{t['version']}",'telegram',{'method':'sendMessage','body':{
            'chat_id':self.e.s.owner_id,'text':text[:3900],'reply_markup':{'inline_keyboard':[[
                {'text':'نوشتن پاسخ','callback_data':f"pubreply:{tid}:{t['version']}"},
                {'text':'بستن درخواست','callback_data':f"pubclose:{tid}:{t['version']}"}]]}},'save_as':'public_notice','ticket_id':tid,'ticket_version':t['version']})

    def callback(self,db,cq,m):
        match=re.fullmatch(r'(pubreply|pubclose):([a-f0-9]{20}):([1-9]\d{0,5})',cq.get('data',''))
        if not match:return False
        action,tid,v=match.groups();t=db.execute('SELECT * FROM public_tickets WHERE id=?',(tid,)).fetchone()
        if not t or t['status']!='pending' or t['version']!=int(v) or t['notice_id']!=m.get('message_id'):return True
        if action=='pubclose':
            db.execute("UPDATE public_tickets SET status='closed',updated=? WHERE id=?",(self.e.clock(),tid))
            db.execute("UPDATE public_users SET lead_state='closed' WHERE user_id=?",(t['user_id'],))
        else:
            db.execute("UPDATE public_tickets SET status='editing' WHERE id=?",(tid,))
            self.e.queue(db,f'public:edit:{tid}:{v}','telegram',{'method':'sendMessage','body':{'chat_id':self.e.s.owner_id,
                'text':'با Reply به همین پیام، پاسخ نهایی را بنویس؛ متن مستقیم برای این مخاطب ارسال می‌شود.',
                'reply_markup':{'force_reply':True}},'save_as':'public_edit','ticket_id':tid,'ticket_version':t['version']})
        return True

    def owner_message(self,db,m,update):
        reply=m.get('reply_to_message',{}).get('message_id');text=m['text'].strip()
        if not text:return False
        if reply:
            t=db.execute("SELECT * FROM public_tickets WHERE edit_prompt_id=? AND status='editing'",(reply,)).fetchone()
            if t:
                self.owner_reply(db,t['id'],text,update);return True
        if text.split()[0].split('@')[0] in {'/start','/menu'} or normalize_text(text) in ('سلام','درود','hi','hello'):
            answer=WELCOME
        elif text.split()[0].split('@')[0] in SERVICE_COMMANDS or normalize_text(text) in SERVICE_PHRASES:
            answer=SERVICES
        elif text.startswith('/tgreply '):
            parts=text.split(maxsplit=2)
            answer=self.reply(db,parts[1],parts[2]) if len(parts)==3 else 'قالب: /tgreply ID متن پاسخ'
        elif text.startswith('/tgfaq\n'):
            fields={k.strip():v.strip() for k,v in (line.split(':',1) for line in text.splitlines()[1:] if ':' in line)}
            word=normalize_text(fields.get('keyword',''));answer=fields.get('reply','')
            if not word or len(word)>100 or not answer or len(answer.encode())>3000:answer='قالب: /tgfaq سپس keyword: کلمه و reply: متن در خط‌های جدا.'
            else:
                db.execute('INSERT INTO public_faqs(keyword,response) VALUES(?,?) ON CONFLICT(keyword) DO UPDATE SET response=excluded.response,active=1',(word,answer));answer='پاسخ آمادهٔ تلگرام ذخیره شد: '+word
        elif text=='/tgfaqs':
            answer='\n'.join(r['keyword'] for r in db.execute('SELECT keyword FROM public_faqs ORDER BY keyword LIMIT 50')) or 'هنوز پاسخ آماده‌ای اضافه نشده.'
        elif text=='/public':
            count=db.execute('SELECT COUNT(*) AS n FROM public_users').fetchone()['n']
            pending=db.execute("SELECT COUNT(*) AS n FROM public_tickets WHERE status IN ('pending','editing','approved')").fetchone()['n']
            answer=f'پاسخ‌گویی عمومی تلگرام: {self.e.s.public_telegram_enabled}\nمدل برای مخاطب عمومی: غیرفعال\nمخاطب‌ها: {count}\nدرخواست باز: {pending}\n\n'+WELCOME
        else:return False
        self.send(db,'public:ownercommand:'+str(update),self.e.s.owner_id,answer);return True

    def owner_reply(self,db,tid,text,update):
        self.send(db,'public:ownerreply:'+str(update),self.e.s.owner_id,self.reply(db,tid,text))

    def reply(self,db,tid,text):
        if not re.fullmatch(r'[a-f0-9]{20}',tid) or not text.strip() or len(text.encode())>3000:return 'شناسه یا متن پاسخ معتبر نیست؛ متن باید کمتر از ۳۰۰۰ بایت باشد.'
        t=db.execute("SELECT * FROM public_tickets WHERE id=? AND status IN ('pending','editing')",(tid,)).fetchone()
        if not t:return 'درخواست باز پیدا نشد؛ از کارت جدید استفاده کن.'
        db.execute("UPDATE public_tickets SET status='approved',draft=?,updated=? WHERE id=?",(text,self.e.clock(),tid))
        self.send(db,f"public:answer:{tid}:{t['version']}",t['user_id'],text,ticket_id=tid,ticket_version=t['version'],public_answer=True)
        return 'پاسخ در صف ارسال قرار گرفت.'

    def valid_outbox(self,db,p):
        if not p.get('ticket_id'):return True
        t=db.execute('SELECT * FROM public_tickets WHERE id=?',(p['ticket_id'],)).fetchone()
        expected={'public_notice':'pending','public_edit':'editing'}.get(p.get('save_as'),'approved')
        return bool(t and t['version']==p.get('ticket_version') and t['status']==expected and
                    (not p.get('public_answer') or (t['draft']==p['body']['text'] and t['user_id']==str(p['body']['chat_id']))))

    def delivered(self,db,p,result):
        tid=p.get('ticket_id')
        if not tid:return
        if p.get('save_as') in ('public_notice','public_edit'):
            column='notice_id' if p['save_as']=='public_notice' else 'edit_prompt_id'
            db.execute(f'UPDATE public_tickets SET {column}=? WHERE id=? AND version=?',(result['message_id'],tid,p['ticket_version']))
        elif p.get('public_answer'):
            t=db.execute('SELECT * FROM public_tickets WHERE id=?',(tid,)).fetchone()
            db.execute('INSERT INTO public_messages(user_id,role,text,created) VALUES(?,?,?,?)',(t['user_id'],'human',p['body']['text'],self.e.clock()))
            db.execute("UPDATE public_tickets SET status='sent' WHERE id=? AND version=?",(tid,p['ticket_version']))
            if t['version']==p['ticket_version']:
                db.execute("UPDATE public_users SET lead_state='interested' WHERE user_id=?",(t['user_id'],))

    def maintenance(self,db,cutoff):
        db.execute("UPDATE public_tickets SET status='expired',draft='' WHERE updated<? AND status IN ('pending','editing','approved')",(cutoff,))
        db.execute('DELETE FROM public_messages WHERE created<?',(cutoff,))
        db.execute("UPDATE public_users SET username='' WHERE last_interaction<?",(cutoff,))
        db.execute("UPDATE public_tickets SET draft='' WHERE updated<?",(cutoff,))
        # Keep IDs, redact delivery payloads and terminal webhook payloads elsewhere.
        for row in list(db.execute("SELECT id,payload FROM outbox WHERE channel='telegram' AND status IN ('sent','blocked','failed','unknown_delivery') AND COALESCE(sent_at,started_at,0)<?",(cutoff,))):
            if row['id'].startswith('public:'):db.execute("UPDATE outbox SET payload='{}' WHERE id=?",(row['id'],))
