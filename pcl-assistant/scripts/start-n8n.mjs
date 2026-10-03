// Bootstrap the dedicated PCL n8n instance before starting its scheduler.
// Never expose this unconfigured admin UI publicly. CLI manages the five graphs.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn, spawnSync} from 'node:child_process';

const token=process.env.INTERNAL_API_TOKEN;
const target=process.env.PCL_INTERNAL_URL;
if (!token || !target || !process.env.N8N_ENCRYPTION_KEY) {
  console.error('PCL n8n configuration is incomplete'); process.exit(1);
}
const url=new URL(target);
if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
  console.error('PCL n8n internal URL is invalid'); process.exit(1);
}
const workflowFolder=process.env.PCL_WORKFLOW_FOLDER || '/opt/pcl/workflows';
const files=fs.readdirSync(workflowFolder).filter(f=>/^pcl-.*\.json$/.test(f)).sort();
const workflows=files.map(file=>JSON.parse(fs.readFileSync(path.join(workflowFolder,file),'utf8')));
const expected=['pcl-approval','pcl-error','pcl-maintenance','pcl-receive','pcl-send'];
if (JSON.stringify(workflows.map(w=>w.id).sort())!==JSON.stringify(expected)) {
  console.error('PCL n8n workflow set is incomplete'); process.exit(1);
}
for (const workflow of workflows) {
  for (const node of workflow.nodes) {
    if (node.type==='n8n-nodes-base.httpRequest') {
      if (!node.parameters.url.startsWith('http://gateway:8080/internal/')) throw new Error('Unexpected workflow endpoint');
      node.parameters.url=node.parameters.url.replace('http://gateway:8080',target.replace(/\/$/,''));
    }
  }
}
const hash=crypto.createHash('sha256').update(JSON.stringify(workflows)+token).digest('hex');
const stateFolder=path.join(process.env.N8N_USER_FOLDER || '/data','.n8n');
fs.mkdirSync(stateFolder,{recursive:true,mode:0o700});
const marker=path.join(stateFolder,'pcl-bootstrap.json');
let prior=''; try {prior=JSON.parse(fs.readFileSync(marker,'utf8')).hash;} catch {}
function run(args) {
  const result=spawnSync(process.env.PCL_N8N_BINARY || 'n8n',args,{stdio:'pipe',timeout:120000});
  if (result.status!==0) {
    // Child output can include credentials: emit only the command name.
    console.error('PCL n8n bootstrap failed: '+args[0]); process.exitCode=1;
    throw new Error('Bootstrap command failed');
  }
}
if (prior!==hash) {
  const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'pcl-n8n-bootstrap-'));
  try {
    const credentialFile=path.join(temporary,'credential.json');
    fs.writeFileSync(credentialFile,JSON.stringify([{id:'pcl-runtime-auth',name:'PCL runtime internal API',
      type:'httpHeaderAuth',data:{name:'Authorization',value:'Bearer '+token}}]),{mode:0o600});
    run(['import:credentials','--input='+credentialFile]);
    for (const workflow of workflows) {
      const file=path.join(temporary,workflow.id+'.json');
      fs.writeFileSync(file,JSON.stringify(workflow),{mode:0o600});
      run(['import:workflow','--input='+file]);
      run(['publish:workflow','--id='+workflow.id]);
    }
    const temporaryMarker=marker+'.tmp';
    fs.writeFileSync(temporaryMarker,JSON.stringify({hash,workflowIds:expected}),{mode:0o600});
    fs.renameSync(temporaryMarker,marker);
    console.log('PCL: five workflows imported and published');
  } finally {fs.rmSync(temporary,{recursive:true,force:true});}
}
const child=spawn(process.env.PCL_N8N_BINARY || 'n8n',['start'],{stdio:'inherit'});
for (const signal of ['SIGTERM','SIGINT']) process.on(signal,()=>child.kill(signal));
child.on('error',()=>{console.error('PCL n8n failed to start');process.exit(1);});
child.on('exit',code=>process.exit(code ?? 1));
