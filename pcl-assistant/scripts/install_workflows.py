"""Engineer-run idempotent installer using the authenticated n8n public API."""
import json,os,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
base=os.environ['N8N_API_URL'].rstrip('/')+'/api/v1'
key=os.environ['N8N_API_KEY'];runtime=os.environ['INTERNAL_API_TOKEN']
if not base.startswith('https://') and not base.startswith('http://localhost:'):raise SystemExit('Use HTTPS or localhost for n8n')

def api(method,path,data=None):
 req=urllib.request.Request(base+path,method=method,data=json.dumps(data).encode() if data is not None else None,
   headers={'X-N8N-API-KEY':key,'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
# Credential values never enter workflow JSON or console output.
existing_cred=os.environ.get('N8N_RUNTIME_CREDENTIAL_ID')
cred={'id':existing_cred} if existing_cred else api('POST','/credentials',{'name':'PCL runtime internal API','type':'httpHeaderAuth','data':{'name':'Authorization','value':'Bearer '+runtime}})
existing=[];cursor=None
while True:
 from urllib.parse import quote
 page=api('GET','/workflows?limit=100'+('&cursor='+quote(cursor,safe='') if cursor else ''))
 existing.extend(page['data']);cursor=page.get('nextCursor')
 if not cursor:break
ids={};gateway=os.environ.get('PCL_INTERNAL_URL','http://gateway:8080').rstrip('/')
for path in sorted((ROOT/'workflows').glob('pcl-*.json'),key=lambda p:p.name!='pcl-error.json'):
 d=json.loads(path.read_text());ref=d['id'];payload={k:d[k] for k in ('name','nodes','connections','settings')}
 if ref!='pcl-error':payload['settings']['errorWorkflow']=ids['pcl-error']
 for n in payload['nodes']:
  if 'credentials' in n:n['credentials']['httpHeaderAuth']['id']=cred['id']
  if n['type']=='n8n-nodes-base.httpRequest':n['parameters']['url']=n['parameters']['url'].replace('http://gateway:8080',gateway)
 match=[w for w in existing if w['name']==d['name']]
 if len(match)>1:raise SystemExit('Duplicate named workflows; engineer must inspect')
 saved=api('PUT','/workflows/'+match[0]['id'],payload) if match else api('POST','/workflows',payload)
 ids[ref]=saved['id']
 # Start schedules only after explicit engineer commissioning; default remains inactive.
 if os.environ.get('ACTIVATE_WORKFLOWS')=='true':api('POST','/workflows/'+saved['id']+'/activate')
print('Workflows installed; secret values omitted. Credential ID='+cred['id']+'; Activation='+os.environ.get('ACTIVATE_WORKFLOWS','false'))
