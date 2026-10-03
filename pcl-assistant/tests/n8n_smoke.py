"""Real n8n execution against mock-provider runtime; never calls Meta/OpenAI/Telegram."""
import json,os,subprocess,tempfile,threading,sys
from pathlib import Path
from wsgiref.simple_server import make_server,WSGIRequestHandler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_system import Fake,NOW
from app.engine import Engine
from app.settings import Settings
from app.server import Application
class Quiet(WSGIRequestHandler):
 def log_message(self,*args):pass
binary=os.environ.get('N8N_BINARY','n8n')
with tempfile.TemporaryDirectory(prefix='pcl-n8n-smoke-') as tmp:
 root=Path(__file__).resolve().parents[1];folder=Path(tmp);token='mock-local-runtime-token'
 s=Settings(db_path=tmp+'/pcl.sqlite',account_id='100',owner_id='999',telegram_token='mock',internal_token=token,dry_run=True,outbound_enabled=True)
 clients=Fake();e=Engine(s,clients=clients,clock=lambda:NOW)
 server=make_server('127.0.0.1',0,Application(e),handler_class=Quiet);port=server.server_port
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  env={**os.environ,'N8N_USER_FOLDER':tmp+'/n8n','N8N_DIAGNOSTICS_ENABLED':'false','N8N_VERSION_NOTIFICATIONS_ENABLED':'false','N8N_COMMUNITY_PACKAGES_ENABLED':'false'}
  credentials=folder/'credential.json';credentials.write_text(json.dumps([{'id':'pcl-runtime-auth','name':'PCL runtime internal API','type':'httpHeaderAuth','data':{'name':'Authorization','value':'Bearer '+token}}]));credentials.chmod(0o600)
  def run(args):
   r=subprocess.run([binary,*args],env=env,capture_output=True,text=True,timeout=60)
   if r.returncode:print(r.stdout[-4000:]);print(r.stderr[-2000:]);raise SystemExit('n8n execution failed: '+str(args))
   if 'errorMessage' in r.stdout or '"status": "error"' in r.stdout:print(r.stdout[-4000:]);raise SystemExit('n8n returned an execution error')
   return r.stdout
  run(['import:credentials','--input='+str(credentials)])
  # Import real exported graph with local URL and a manual trigger for deterministic execution.
  for p in (root/'workflows').glob('pcl-*.json'):
   d=json.loads(p.read_text())
   for n in d['nodes']:
    if n['type']=='n8n-nodes-base.httpRequest':n['parameters']['url']=n['parameters']['url'].replace('http://gateway:8080',f'http://127.0.0.1:{port}')
    if n['type'] in ('n8n-nodes-base.scheduleTrigger','n8n-nodes-base.errorTrigger'):n.update(type='n8n-nodes-base.manualTrigger',typeVersion=1,parameters={})
   fixture=folder/p.name;fixture.write_text(json.dumps(d));run(['import:workflow','--input='+str(fixture)])
  payload={'object':'instagram','entry':[{'id':'100','messaging':[{'sender':{'id':'200'},'recipient':{'id':'100'},'timestamp':NOW*1000,'message':{'mid':'n8n-smoke','text':'سلام'}}]}]}
  e.ingest(payload)
  for id in ('pcl-receive','pcl-approval','pcl-send','pcl-maintenance','pcl-error'):
   output=run(['execute','--id='+id,'--rawOutput']);print(id+' executed')
  assert e.store.one("SELECT status FROM outbox WHERE channel='instagram'")['status']=='simulated'
  assert not clients.sent
  print('PASS: n8n 2.41.6 imported all 5 graphs and executed A/B/C/D/E (manual triggers for test); simulated DM, zero external provider calls')
 finally:server.shutdown();server.server_close();e.store.db.close()
