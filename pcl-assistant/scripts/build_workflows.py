"""Generate small maintainable n8n orchestration workflows, without embedded secrets."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CRED={'httpHeaderAuth':{'id':'pcl-runtime-auth','name':'PCL runtime internal API'}}

def node(name,typ,params,pos,version=1):
 return {'id':name.lower().replace(' ','-'),'name':name,'type':'n8n-nodes-base.'+typ,'typeVersion':version,'position':pos,'parameters':params}
def call(name,path,pos,body=None):
 p={'method':'POST','url':'http://gateway:8080/internal/'+path,'authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth','options':{'timeout':90000}}
 if body:p.update({'sendBody':True,'specifyBody':'json','jsonBody':body})
 return {**node(name,'httpRequest',p,pos,4.2),'credentials':CRED,'retryOnFail':True,'maxTries':2,'waitBetweenTries':1500}
def schedule(seconds):
 return node('Schedule','scheduleTrigger',{'rule':{'interval':[{'field':'seconds','secondsInterval':seconds}]}},[0,0],1.2)
def flow(id,name,nodes,links,error=True):
 d={'id':id,'name':name,'active':False,'nodes':nodes,'connections':{},'settings':{'executionOrder':'v1','saveDataSuccessExecution':'none','saveDataErrorExecution':'none','saveManualExecutions':False,'executionTimeout':120,'timezone':'Asia/Tehran'},'pinData':{}}
 if error:d['settings']['errorWorkflow']='pcl-error'
 for a,b in links:d['connections'][a]={'main':[[{'node':b,'type':'main','index':0}]]}
 return d
flows=[flow('pcl-receive','PCL A — Receive, rule router and OpenAI',[
 schedule(5),call('Claim durable events','jobs/claim',[250,0]),
 node('Each event','splitOut',{'fieldToSplitOut':'jobs','options':{}},[500,0]),
 call('Classify DM comment or story','events/process',[750,0],'={{ JSON.stringify({event_id: $json.event_id, lease: $json.lease}) }}')],
 [('Schedule','Claim durable events'),('Claim durable events','Each event'),('Each event','Classify DM comment or story')]),
 flow('pcl-approval','PCL B — Telegram approval and owner commands',[schedule(5),call('Apply owner decisions','telegram/process',[250,0])],[('Schedule','Apply owner decisions')]),
 flow('pcl-send','PCL C — Guarded Instagram and Telegram outbox',[schedule(5),call('Send and verify','outbox/dispatch',[250,0])],[('Schedule','Send and verify')]),
 flow('pcl-maintenance','PCL D — Expiry recovery retention and logging',[schedule(60),call('Maintain queues','maintenance',[250,0])],[('Schedule','Maintain queues')]),
 flow('pcl-error','PCL E — Error alert',[node('Workflow error','errorTrigger',{},[0,0]),call('Alert owner','alerts',[250,0],'={{ JSON.stringify({execution_id: $json.execution?.id || "unknown"}) }}')],[('Workflow error','Alert owner')],False)]
for d in flows:(ROOT/'workflows'/(d['id']+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print(f'Generated {len(flows)} workflows')
