import io,json,tempfile,unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from app.clients import APIError,Clients
from app.engine import Engine,validate_rule
from app.events import keyword_matches
from app.server import Application
from app.settings import Settings
NOW=1791046800.
class Fake:
 def __init__(self):self.sent=[];self.tg=[];self.calls=0;self.failure=None;self.n=100
 def instagram(self,e,text):
  self.sent.append((e,text))
  if self.failure:raise APIError(self.failure,30)
  return 'sent'
 def telegram(self,method,body):self.n+=1;self.tg.append((method,body));return {'message_id':self.n}
 def comment_time(self,e):return NOW-60
 def ai(self,*args):
  self.calls+=1
  return {'category':'tool','confidence':.96,'reply':'با AI محتوای حرفه‌ای‌تر بساز.','needs_approval':False,'missing_information':False,'fact_ids':['brand']}
class System(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.now=NOW;self.c=Fake()
  self.s=Settings(db_path=self.tmp.name+'/db',account_id='100',owner_id='999',telegram_token='mock',internal_token='internal',meta_secret='secret',verify_token='verify',telegram_secret='tg-secret',openai_key='mock',meta_token='mock',outbound_enabled=True,dry_run=False,meta_verified=True)
  self.e=Engine(self.s,clients=self.c,clock=lambda:self.now,knowledge={'brand':'AI content'});self.addCleanup(self.e.store.db.close)
 def dm(self,text='سلام',mid='m1',user='200',story=None):
  m={'mid':mid,'text':text}
  if story:m['reply_to']={'story':{'id':story}}
  return {'object':'instagram','entry':[{'id':'100','messaging':[{'sender':{'id':user},'recipient':{'id':'100'},'timestamp':self.now*1000,'message':m}]}]}
 def comment(self,media='400',ts=NOW-5):
  return {'object':'instagram','entry':[{'id':'100','changes':[{'field':'comments','value':{'id':'300','text':'وکیل','from':{'id':'200','username':'ashkan'},'media':{'id':media},'timestamp':ts}}]}]}
 def process(self,p):
  self.e.ingest(p)
  return [self.e.process(j['event_id'],j['lease']) for j in self.e.claim()['jobs']]
 def rule(self,trigger='comment',media='400',word='وکیل',response='این آموزش برای تو آماده شده.'):
  with self.e.store.transaction() as db:self.e.upsert_rule(db,validate_rule({'id':'test','trigger':trigger,'media_id':media,'keyword':word,'response':response}))
 def approval(self):return self.e.store.one('SELECT * FROM approvals ORDER BY rowid DESC LIMIT 1')
 def callback(self,action='approve',a=None,uid='999',msg=None,update=1):
  a=a or self.approval();self.e.receive_telegram({'update_id':update,'callback_query':{'id':'cb','from':{'id':int(uid)},'data':f'{action}:{a["id"]}:{a["version"]}','message':{'message_id':msg or a['telegram_message_id'],'chat':{'id':999,'type':'private'}}}});self.e.telegram_process()
 def test_normal_dm(self):
  self.process(self.dm());self.e.dispatch();self.assertEqual(len(self.c.sent),1);self.assertEqual(self.c.calls,0)
 def test_grounded_ai(self):
  self.process(self.dm('چه کاری انجام می‌دهید؟'));self.e.dispatch();self.assertEqual(self.c.calls,1);self.assertEqual(len(self.c.sent),1)
 def test_keyword_comment(self):
  self.rule();self.process(self.comment());self.e.dispatch();self.assertEqual(len(self.c.sent),1);self.assertEqual(self.c.calls,0)
 def test_wrong_post(self):
  self.rule();self.process(self.comment('500'));self.e.dispatch();self.assertEqual(len(self.c.sent),0)
 def test_story(self):
  self.rule('story','600','آموزش');self.process(self.dm('آموزش',story='600'));self.e.dispatch();self.assertEqual(len(self.c.sent),1);self.assertEqual(self.c.calls,0)
 def test_pricing(self):
  self.process(self.dm('قیمت چنده؟'));self.e.dispatch();self.assertEqual(len(self.c.sent),0);self.assertEqual(self.approval()['category'],'pricing')
 def test_sensitive_rule_bypass_blocked(self):
  self.rule('dm','*','قیمت');self.process(self.dm('قیمت'));self.assertIsNotNone(self.approval())
 def test_approve(self):
  self.process(self.dm('قیمت'));self.e.dispatch();self.callback();self.e.dispatch();self.assertEqual(len(self.c.sent),1);self.assertEqual(self.approval()['status'],'sent')
 def test_reject(self):
  self.process(self.dm('قیمت'));self.e.dispatch();self.callback('reject');self.e.dispatch();self.assertEqual(len(self.c.sent),0);self.assertEqual(self.approval()['status'],'rejected')
 def test_unauthorized(self):
  self.process(self.dm('قیمت'));self.e.dispatch();self.callback(uid='888');self.e.dispatch();self.assertEqual(len(self.c.sent),0)
 def test_wrong_card(self):
  self.process(self.dm('قیمت'));self.e.dispatch();self.callback(msg=333);self.e.dispatch();self.assertEqual(len(self.c.sent),0)
 def test_duplicate_callback(self):
  self.process(self.dm('قیمت'));self.e.dispatch();a=self.approval();self.callback(a=a);self.callback(a=a,update=2);self.e.dispatch();self.assertEqual(len(self.c.sent),1)
 def test_edit_then_approve(self):
  self.process(self.dm('قیمت'));self.e.dispatch();a=self.approval();self.callback('edit');self.e.dispatch();edit=self.approval()
  self.e.receive_telegram({'update_id':2,'message':{'message_id':50,'from':{'id':999},'chat':{'id':999,'type':'private'},'text':'جزئیات پروژه را بفرست.','reply_to_message':{'message_id':edit['edit_prompt_id']}}});self.e.telegram_process();self.e.dispatch();a2=self.approval();self.assertEqual(a2['version'],2);self.assertEqual(len(self.c.sent),0)
  self.callback(a=a,update=3);self.assertEqual(self.approval()['status'],'pending');self.callback(a=a2,update=4);self.e.dispatch();self.e.dispatch();self.assertEqual(self.c.sent[0][1],'جزئیات پروژه را بفرست.')
 def test_custom(self):
  self.process(self.dm('قیمت'));self.e.dispatch();self.callback('custom');self.e.dispatch();self.assertEqual(self.approval()['status'],'editing')
 def test_unknown(self):
  self.c.ai=lambda *args:(_ for _ in ()).throw(APIError());self.process(self.dm('نامشخص'));self.e.dispatch();self.assertEqual(len(self.c.sent),0);self.assertEqual(self.approval()['category'],'unknown')
 def test_low_confidence(self):
  old=self.c.ai
  def low(*args):d=old(*args);d['confidence']=.4;return d
  self.c.ai=low;self.process(self.dm('ابزار چی؟'));self.assertIsNotNone(self.approval())
 def test_invented_link(self):
  old=self.c.ai
  def unsafe(*args):d=old(*args);d['reply']='https://invented.invalid';return d
  self.c.ai=unsafe;self.process(self.dm('لینک ابزار'));self.assertIsNotNone(self.approval())
 def test_duplicate_webhook(self):
  p=self.dm();self.process(p);self.process(p);self.e.dispatch();self.assertEqual(len(self.c.sent),1)
 def test_concurrent_duplicate(self):
  with ThreadPoolExecutor(4) as pool:list(pool.map(lambda _:self.e.ingest(self.dm()),range(8)))
  self.assertEqual(len(self.e.store.rows('SELECT * FROM events')),1)
 def test_batch_all(self):
  p=self.dm();p['entry'][0]['messaging']+=self.dm(mid='m2',user='201')['entry'][0]['messaging'];self.process(p);self.e.dispatch();self.assertEqual(len(self.c.sent),2)
 def test_latest_dm_only(self):
  p=self.dm();p['entry'][0]['messaging']+=self.dm(mid='m2')['entry'][0]['messaging'];self.process(p);self.e.dispatch();self.assertEqual(len(self.c.sent),1)
 def test_newer_context_blocks_approval(self):
  self.process(self.dm('قیمت'));self.e.dispatch();a=self.approval();self.e.ingest(self.dm('جزئیات',mid='m2'));self.callback(a=a);self.e.dispatch();self.assertEqual(len(self.c.sent),0)
 def test_followup_handoff(self):
  self.process(self.dm('قیمت'));self.process(self.dm('باشه',mid='m2'));self.e.dispatch();self.assertEqual(len(self.c.sent),0)
 def test_expired_window(self):
  self.process(self.dm());self.now+=86400;self.e.dispatch();self.assertEqual(len(self.c.sent),0)
 def test_comment_timestamp_lookup(self):
  self.rule();self.process(self.comment(ts=None));self.e.dispatch();self.assertEqual(len(self.c.sent),1)
 def test_missing_timestamp_held(self):
  self.rule();self.c.comment_time=lambda e:(_ for _ in ()).throw(APIError());self.process(self.comment(ts=None));self.e.dispatch();self.assertEqual(len(self.c.sent),0);self.assertIsNotNone(self.approval())
 def test_comment_expired(self):
  self.rule();self.process(self.comment(ts=NOW-8*86400));self.e.dispatch();self.assertEqual(len(self.c.sent),0)
 def test_failed_api(self):
  self.c.failure='api_rejected';self.process(self.dm());self.e.dispatch();self.e.dispatch();self.assertEqual(len(self.c.sent),1);self.assertEqual(self.e.store.one("SELECT status FROM outbox WHERE channel='instagram'")['status'],'failed')
 def test_ambiguous_no_retry(self):
  self.c.failure='unknown_delivery';self.process(self.dm());self.e.dispatch();self.now+=600;self.e.dispatch();self.assertEqual(len(self.c.sent),1)
 def test_429_retry(self):
  self.c.failure='rate_limit';self.process(self.dm());self.e.dispatch();self.c.failure=None;self.now+=31;self.e.dispatch();self.assertEqual(len(self.c.sent),2)
 def test_crash_during_send(self):
  self.process(self.dm())
  with self.e.store.transaction() as db:db.execute("UPDATE outbox SET status='sending' WHERE channel='instagram'")
  Engine(self.s,self.e.store,self.c,clock=lambda:self.now).dispatch();self.assertEqual(len(self.c.sent),0)
 def test_pause(self):
  self.process(self.dm())
  with self.e.store.transaction() as db:self.e.command(db,'/pause')
  self.e.dispatch();self.assertEqual(len(self.c.sent),0)
 def test_dryrun(self):
  self.s.dry_run=True;self.process(self.dm());self.e.dispatch();self.assertEqual(len(self.c.sent),0);self.assertEqual(self.e.store.one("SELECT status FROM outbox WHERE channel='instagram'")['status'],'simulated')
 def test_budget(self):
  self.s.ai_daily_limit=0;self.process(self.dm('خدمات؟'));self.assertEqual(self.c.calls,0);self.assertIsNotNone(self.approval())
 def test_byte_limit(self):
  with self.assertRaises(ValueError):validate_rule({'id':'a','trigger':'dm','keyword':'الف','response':'ش'*501})
 def test_arabic_script(self):
  self.assertTrue(keyword_matches('وَكيل!','وکیل'));self.assertFalse(keyword_matches('وکیلک','وکیل'))
 def test_echo(self):
  p=self.dm();p['entry'][0]['messaging'][0]['message']['is_echo']=True;self.assertEqual(self.e.ingest(p)['accepted'],0)
 def test_rule_control(self):
  with self.e.store.transaction() as db:r=self.e.command(db,'/rule\nid: lawyer\ntrigger: comment\npost: 400\nkeyword: وکیل\nreply: آموزش برای شما\napproval: no')
  self.assertIn('lawyer',r);self.process(self.comment());self.e.dispatch();self.assertEqual(len(self.c.sent),1)
 def test_retention_dedup(self):
  p=self.dm();self.process(p);self.e.dispatch();self.now+=31*86400;self.e.maintenance();self.assertEqual(self.e.store.one('SELECT text FROM events')['text'],'');self.assertEqual(self.e.ingest(p)['accepted'],0)
 def http(self,path,method='POST',body=b'{}',headers=None,query=''):
  status=[];env={'PATH_INFO':path,'REQUEST_METHOD':method,'CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body),'QUERY_STRING':query,**(headers or {})};out=b''.join(Application(self.e)(env,lambda s,h:status.append(s)));return status[0],out
 def test_challenge(self):
  s,b=self.http('/webhooks/meta','GET',query='hub.mode=subscribe&hub.verify_token=verify&hub.challenge=123');self.assertTrue(s.startswith('200'));self.assertEqual(b,b'123')
 def test_empty_verify_rejected(self):
  self.s.verify_token='';s,_=self.http('/webhooks/meta','GET',query='hub.mode=subscribe&hub.verify_token=&hub.challenge=123');self.assertTrue(s.startswith('403'))
 def test_invalid_signature(self):
  s,_=self.http('/webhooks/meta',body=json.dumps(self.dm()).encode());self.assertTrue(s.startswith('401'))
 def test_valid_signature(self):
  import hmac,hashlib
  body=json.dumps(self.dm(),ensure_ascii=False).encode();sig='sha256='+hmac.new(b'secret',body,hashlib.sha256).hexdigest();s,b=self.http('/webhooks/meta',body=body,headers={'HTTP_X_HUB_SIGNATURE_256':sig});self.assertTrue(s.startswith('200'));self.assertEqual(json.loads(b)['accepted'],1)
 def test_telegram_secret(self):
  s,_=self.http('/webhooks/telegram');self.assertTrue(s.startswith('401'))
 def test_internal_auth(self):
  s,_=self.http('/internal/jobs/claim');self.assertTrue(s.startswith('401'))
 def test_commission_requires_auth(self):
  s,_=self.http('/internal/telegram/commission');self.assertTrue(s.startswith('401'));self.assertEqual(self.c.tg,[])
 def test_runtime_status_is_authenticated_and_redacted(self):
  s,_=self.http('/internal/status','GET');self.assertTrue(s.startswith('401'))
  s,b=self.http('/internal/status','GET',headers={'HTTP_AUTHORIZATION':'Bearer internal'})
  self.assertTrue(s.startswith('200'));d=json.loads(b)
  self.assertTrue(d['integrations_configured']['telegram']);self.assertNotIn('mock',b.decode())
  self.assertNotIn('999',b.decode());self.assertEqual(d['queues']['outbox'],[])
 def test_scheduler_heartbeat_is_bounded(self):
  for _ in range(3):
   s,_=self.http('/internal/jobs/claim',headers={'HTTP_AUTHORIZATION':'Bearer internal'});self.assertTrue(s.startswith('200'))
  rows=self.e.store.rows("SELECT * FROM controls WHERE key LIKE 'scheduler:%'")
  self.assertEqual(len(rows),1);self.assertEqual(float(rows[0]['value']),NOW)
 def test_commission_validates_bot_and_preserves_updates(self):
  self.s.public_base_url='https://pcl.example.com'
  with patch.object(self.c,'telegram',side_effect=[{'id':123,'is_bot':True,'username':'pcl_bot'},True]) as tg:
   s,b=self.http('/internal/telegram/commission',body=b'{"expected_username":"pcl_bot"}',headers={'HTTP_AUTHORIZATION':'Bearer internal'})
   self.assertTrue(s.startswith('200'));self.assertEqual(json.loads(b)['bot_username'],'pcl_bot')
   self.assertFalse(tg.call_args.args[1]['drop_pending_updates'])
   self.assertEqual(tg.call_args.args[1]['secret_token'],'tg-secret')
  self.assertEqual(len(self.e.store.rows("SELECT * FROM outbox WHERE id='telegram-commission:123'")),1)
 def test_commission_wrong_bot_rejected(self):
  self.s.public_base_url='https://pcl.example.com'
  with patch.object(self.c,'telegram',return_value={'id':123,'is_bot':True,'username':'other_bot'}) as tg:
   s,_=self.http('/internal/telegram/commission',body=b'{"expected_username":"pcl_bot"}',headers={'HTTP_AUTHORIZATION':'Bearer internal'})
   self.assertTrue(s.startswith('400'));self.assertEqual(tg.call_count,1)
 def test_commission_invalid_url_rejected(self):
  for url in ('http://pcl.example.com','https://user:password@pcl.example.com','https://pcl.example.com/path','https://pcl.example.com?token=x'):
   self.s.public_base_url=url
   s,_=self.http('/internal/telegram/commission',body=b'{"expected_username":"pcl_bot"}',headers={'HTTP_AUTHORIZATION':'Bearer internal'})
   self.assertTrue(s.startswith('400'))
  self.assertEqual(self.c.tg,[])
 def test_secrets_not_logged(self):
  self.process(self.dm());self.c.failure='api_rejected';self.e.dispatch();self.assertNotIn('mock',json.dumps(self.e.store.rows('SELECT * FROM audit')))
 def test_private_reply_recipient(self):
  c=Clients(self.s)
  with patch.object(c,'request',return_value={'message_id':'yes'}) as req:
   c.instagram({'id':'100:comment:300','kind':'comment','user_id':'200'},'متن');self.assertEqual(req.call_args.args[1]['recipient'],{'comment_id':'300'})
 def test_incomplete_ai(self):
  c=Clients(self.s)
  with patch.object(c,'request',return_value={'status':'incomplete'}):
   with self.assertRaises(APIError):c.ai({'text':'سلام','kind':'dm'},[],{})
if __name__=='__main__':unittest.main()
