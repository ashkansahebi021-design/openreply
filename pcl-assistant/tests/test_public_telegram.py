import tempfile,unittest
from unittest.mock import patch
from app.engine import Engine
from app.clients import APIError
from app.settings import Settings
from test_system import Fake,NOW

class PublicTelegramTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.now=NOW;self.c=Fake();self.s=Settings(db_path=self.tmp.name+'/db',owner_id='999',telegram_token='mock',public_telegram_enabled=True)
  self.e=Engine(self.s,clients=self.c,clock=lambda:self.now);self.addCleanup(self.e.store.db.close)
 def message(self,text,update=1,user=200,reply=None,chat_type='private'):
  m={'message_id':update,'from':{'id':user,'username':'visitor'},'chat':{'id':user,'type':chat_type},'text':text}
  if reply:m['reply_to_message']={'message_id':reply}
  self.e.receive_telegram({'update_id':update,'message':m});self.e.telegram_process()
 def drain(self):
  for _ in range(20):self.e.dispatch()
 def ticket(self):return self.e.store.one('SELECT * FROM public_tickets ORDER BY rowid DESC LIMIT 1')
 def callback(self,action='pubreply',update=2,user=999,ticket=None,msg=None):
  t=ticket or self.ticket()
  self.e.receive_telegram({'update_id':update,'callback_query':{'id':'cb'+str(update),'from':{'id':user},'data':f'{action}:{t["id"]}:{t["version"]}',
   'message':{'message_id':msg or t['notice_id'],'chat':{'id':999,'type':'private'}}}})
  self.e.telegram_process()
 def test_start_public_with_no_ai_or_instagram(self):
  self.message('/start');self.drain()
  self.assertEqual(self.c.calls,0);self.assertEqual(self.c.sent,[])
  self.assertIn('چت آزاد ChatGPT نیست',self.c.tg[0][1]['text']);self.assertEqual(self.c.tg[0][1]['chat_id'],'200')
 def test_public_disabled_and_group_rejected(self):
  self.s.public_telegram_enabled=False;self.message('/start');self.drain();self.assertEqual(self.c.tg,[])
  self.s.public_telegram_enabled=True;self.message('/start',2,chat_type='group');self.drain();self.assertEqual(self.c.tg,[])
 def test_admin_commands_not_exposed(self):
  self.message('/status');self.drain();self.assertIn('مخصوص مدیر',self.c.tg[0][1]['text'])
  self.assertEqual(self.e.store.rows('SELECT * FROM public_tickets'),[])
 def test_services_and_owner_editable_faq(self):
  self.message('/tgfaq\nkeyword: آموزش\nreply: پاسخ تأییدشده',1,999)
  self.message('آموزش',2);self.message('/services',3,user=201);self.drain()
  answers=[body['text'] for method,body in self.c.tg if body['chat_id']=='200']
  self.assertEqual(answers,['پاسخ تأییدشده']);self.assertEqual(self.c.calls,0)
 def test_sensitive_keyword_precedes_faq(self):
  self.message('/tgfaq\nkeyword: قیمت\nreply: تخفیف تضمینی',1,999);self.message('قیمت',2);self.drain()
  self.assertEqual(self.ticket()['category'],'pricing');self.assertEqual(self.c.calls,0)
  self.assertFalse(any(body.get('chat_id')=='200' and body.get('text')=='تخفیف تضمینی' for _,body in self.c.tg))
 def test_risky_faq_reply_requires_human(self):
  self.message('/tgfaq\nkeyword: تست\nreply: تحویل تضمینی',1,999);self.message('تست',2);self.drain()
  self.assertEqual(self.ticket()['status'],'pending')
  self.assertFalse(any(body.get('chat_id')=='200' and body.get('text')=='تحویل تضمینی' for _,body in self.c.tg))
 def test_unknown_inquiry_callback_reply(self):
  self.message('یک درخواست اختصاصی دارم');self.drain();self.callback();self.drain()
  t=self.ticket();self.assertEqual(t['status'],'editing')
  self.message('توضیحات نهایی تیم',3,999,t['edit_prompt_id']);self.drain()
  self.assertEqual(self.ticket()['status'],'sent');self.assertEqual(self.c.calls,0)
  self.assertTrue(any(body.get('chat_id')=='200' and body.get('text')=='توضیحات نهایی تیم' for _,body in self.c.tg))
 def test_nonowner_cannot_approve_or_reply(self):
  self.message('قیمت؟');self.drain();self.callback(user=200);self.message('/tgreply '+self.ticket()['id']+' پاسخ جعلی',3)
  self.drain();self.assertEqual(self.ticket()['status'],'pending')
  self.assertFalse(any(body.get('text')=='پاسخ جعلی' for _,body in self.c.tg))
 def test_new_context_blocks_old_card_and_unsent_reply(self):
  self.message('قیمت؟');self.drain();old=self.ticket()
  self.message('/tgreply '+old['id']+' پاسخ قدیمی',2,999)
  self.message('پروژه جدید',3);self.drain();self.callback(ticket=old,update=4);self.drain()
  self.assertEqual(self.ticket()['status'],'pending');self.assertEqual(self.ticket()['version'],2)
  self.assertFalse(any(body.get('text')=='پاسخ قدیمی' for _,body in self.c.tg))
 def test_close_request_sends_no_reply(self):
  self.message('قیمت؟');self.drain();self.callback('pubclose');self.drain()
  self.assertEqual(self.ticket()['status'],'closed')
 def test_duplicate_after_maintenance_does_not_resend(self):
  self.message('/start');self.drain();sent=len(self.c.tg)
  self.e.maintenance();self.message('/start');self.drain();self.assertEqual(len(self.c.tg),sent)
 def test_ambiguous_public_send_not_replayed_and_alerted(self):
  self.message('قیمت؟');self.drain();t=self.ticket()
  self.message('/tgreply '+t['id']+' پاسخ تیم',2,999)
  def fail(method,body):
   if body.get('chat_id')=='200':raise APIError('unknown_delivery')
   return {'message_id':888}
  with patch.object(self.c,'telegram',side_effect=fail) as tg:
   self.drain();self.assertEqual(sum(call.args[1].get('chat_id')=='200' for call in tg.call_args_list),1)
  self.assertEqual(self.ticket()['status'],'unknown_delivery')
  self.assertTrue(self.e.store.one("SELECT id FROM outbox WHERE id LIKE 'alert:unknown_delivery:%'"))
 def test_rate_limits_and_retention(self):
  for i in range(1,10):self.message('سؤال '+str(i),i)
  self.assertEqual(len(self.e.store.rows('SELECT * FROM public_messages')),5)
  self.drain();self.now+=31*86400;self.e.maintenance()
  self.assertEqual(self.e.store.rows('SELECT * FROM public_messages'),[])
  self.assertEqual(self.ticket()['status'],'expired')
  self.assertEqual(self.e.store.one('SELECT username FROM public_users')['username'],'')
 def test_owner_public_preview_is_available(self):
  self.message('/public',user=999);self.drain()
  self.assertIn('پاسخ‌گویی عمومی تلگرام: True',self.c.tg[0][1]['text'])
  self.assertEqual(self.e.store.rows('SELECT * FROM public_users'),[])

 def test_services_answers_while_human_inquiry_pending(self):
  self.message('قیمت؟');self.drain();before=self.ticket();sent=len(self.c.tg)
  self.message('خدمات',2);self.drain()
  self.assertEqual(len(self.c.tg),sent+1)
  self.assertEqual(self.c.tg[-1][1]['chat_id'],'200')
  self.assertIn('تمرکز Persian Creative Lab',self.c.tg[-1][1]['text'])
  self.assertEqual(self.ticket()['version'],before['version'])
  self.assertEqual(self.ticket()['status'],'pending')
 def test_owner_can_preview_welcome_and_services(self):
  self.message('/start',1,999);self.message('خدمات',2,999);self.drain()
  self.assertIn('چت آزاد ChatGPT نیست',self.c.tg[0][1]['text'])
  self.assertIn('تمرکز Persian Creative Lab',self.c.tg[1][1]['text'])
  self.assertEqual(self.e.store.rows('SELECT * FROM public_tickets'),[])
  self.assertEqual(self.c.calls,0)

 def add_prompt(self,title='وکیل',aliases=None,body='متن اصلی پرامپت',update=1):
  self.message('/prompt\ntitle: '+title+'\naliases: '+','.join(aliases or ['حقوقی'])+'\ntext: '+body,update,999)
 def test_prompt_natural_request_returns_original_without_ai(self):
  self.add_prompt();self.message('من اون پرامپت وکیل رو میخوام',2);self.drain()
  self.assertTrue(any(b.get('chat_id')=='200' and b['text']=='وکیل\n\nمتن اصلی پرامپت' for _,b in self.c.tg))
  self.assertEqual(self.c.calls,0);self.assertIsNone(self.ticket())
 def test_prompt_alias_and_persian_normalization(self):
  self.add_prompt();self.message('پرامپت حقوقي میخوام',2);self.drain()
  self.assertTrue(any(b.get('chat_id')=='200' and 'متن اصلی' in b['text'] for _,b in self.c.tg))
 def test_prompt_ambiguous_then_exact_title_selection(self):
  self.add_prompt('وکیل', ['حقوقی']);self.add_prompt('قرارداد نمونه',['حقوقی'],update=2)
  self.message('پرامپت حقوقی',3);self.message('وکیل',4);self.drain()
  answers=[b['text'] for _,b in self.c.tg if b.get('chat_id')=='200']
  self.assertIn('چند پرامپت',answers[0]);self.assertEqual(answers[1],'وکیل\n\nمتن اصلی پرامپت')
 def test_prompt_missing_does_not_invent_or_forward(self):
  self.message('پرامپت وکیل میخوام');self.drain()
  self.assertIn('هنوز پرامپت تأییدشده',self.c.tg[0][1]['text'])
  self.assertIsNone(self.ticket());self.assertEqual(self.c.calls,0)
 def test_prompt_owner_only_and_price_kept_sensitive(self):
  self.message('/prompt\ntitle: جعلی\ntext: متن جعلی',1)
  self.assertEqual(self.e.store.rows('SELECT * FROM public_prompts'),[])
  self.add_prompt(update=2);self.message('قیمت پرامپت وکیل',3);self.drain()
  self.assertEqual(self.ticket()['category'],'pricing')
 def test_prompt_update_and_inactive(self):
  from app.prompt_catalog import PromptCatalog
  self.add_prompt();self.add_prompt(body='نسخه جدید',update=2)
  with self.e.store.transaction() as db:
   PromptCatalog.save(db,{'title':'وکیل','text':'نسخه جدید','aliases':[],'active':False})
  self.message('پرامپت وکیل',3);self.drain()
  self.assertFalse(any(b.get('chat_id')=='200' and 'نسخه جدید' in b['text'] for _,b in self.c.tg))
 def test_prompt_long_text_split_and_deduplicated(self):
  body='a'*8000;self.add_prompt(body=body);self.message('پرامپت وکیل',2);self.drain();self.message('پرامپت وکیل',2);self.drain()
  answers=[b['text'] for _,b in self.c.tg if b.get('chat_id')=='200']
  self.assertEqual(''.join(answers),'وکیل\n\n'+body);self.assertTrue(all(len(x)<=3500 for x in answers))
 def test_prompt_invalid_registration_and_internal_api(self):
  from app.server import Application
  from app.prompt_catalog import PromptCatalog
  app=Application(self.e)
  self.assertEqual(app.internal('/internal/prompts','POST',{'title':'وکیل','text':'متن اصلی','aliases':['حقوقی']}),{'saved':'وکیل'})
  with self.e.store.transaction() as db:
   with self.assertRaises(ValueError):PromptCatalog.save(db,{'title':'خالی','text':''})

 def test_owner_can_request_own_registered_prompt(self):
  self.add_prompt();self.message('پرامپت وکیل رو میخوام',2,999);self.drain()
  self.assertEqual(self.c.tg[-1][1]['text'],'وکیل\n\nمتن اصلی پرامپت')
  self.assertIsNone(self.ticket())

 def test_approved_legal_prompt_seed_is_delivered_verbatim(self):
  import json
  from pathlib import Path
  items=json.loads((Path(__file__).resolve().parents[1]/'config/prompts.approved.json').read_text())
  with self.e.store.transaction() as db:self.e.public.catalog.seed(db,items)
  self.message('پرامپت وکیل رو میخوام');self.drain()
  replies=[b['text'] for _,b in self.c.tg if b.get('chat_id')=='200']
  self.assertEqual(''.join(replies),items[0]['title']+'\n\n'+items[0]['text'])
  self.assertIn('https://t.me/persiancreativelab/6',''.join(replies))
  self.assertIsNone(self.ticket());self.assertEqual(self.c.calls,0)
 def test_approved_seed_preserves_owner_edits_and_disabled_state(self):
  from app.prompt_catalog import PromptCatalog
  asset={'title':'وکیل','text':'نسخه عمومی','aliases':['حقوقی']}
  with self.e.store.transaction() as db:
   PromptCatalog.seed(db,[asset])
   PromptCatalog.save(db,{**asset,'text':'ویرایش مالک','active':False})
   PromptCatalog.seed(db,[asset])
  row=self.e.store.one('SELECT text,active FROM public_prompts')
  self.assertEqual(row,{'text':'ویرایش مالک','active':0})

if __name__=='__main__':unittest.main()
