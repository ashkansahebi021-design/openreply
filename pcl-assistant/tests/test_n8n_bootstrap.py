import json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(shutil.which('node'),'Node required for n8n bootstrap tests')
class Bootstrap(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.folder=Path(self.tmp.name);self.log=self.folder/'calls.jsonl'
  binary=self.folder/'mock-n8n';binary.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['MOCK_LOG'],'a') as f:f.write(json.dumps(args)+'\\n')
if args[0]=='import:credentials':
 data=json.loads(Path(args[1].split('=',1)[1]).read_text())
 assert data[0]['data']['value']=='Bearer '+os.environ['INTERNAL_API_TOKEN']
if args[0]=='import:workflow':
 data=json.loads(Path(args[1].split('=',1)[1]).read_text())
 for n in data['nodes']:
  if n['type']=='n8n-nodes-base.httpRequest':assert n['parameters']['url'].startswith(os.environ['PCL_INTERNAL_URL']+'/internal/')
if os.environ.get('MOCK_FAIL')==args[0]:
 print(os.environ['INTERNAL_API_TOKEN']);sys.exit(1)
''');binary.chmod(0o700)
  self.env={**os.environ,'INTERNAL_API_TOKEN':'unique-test-secret','PCL_INTERNAL_URL':'http://gateway.railway.internal:8080',
   'N8N_ENCRYPTION_KEY':'test-encryption-key','N8N_USER_FOLDER':str(self.folder/'state'),
   'PCL_WORKFLOW_FOLDER':str(ROOT/'workflows'),'PCL_N8N_BINARY':str(binary),'MOCK_LOG':str(self.log)}
 def run_bootstrap(self):
  return subprocess.run(['node',str(ROOT/'scripts/start-n8n.mjs')],env=self.env,capture_output=True,text=True,timeout=30)
 def calls(self):return [json.loads(s) for s in self.log.read_text().splitlines()]
 def test_import_publish_idempotence_and_credential_rotation(self):
  r=self.run_bootstrap();self.assertEqual(r.returncode,0,r.stderr)
  self.assertEqual(sum(c[0]=='publish:workflow' for c in self.calls()),5)
  self.assertEqual(self.calls()[-1],['start'])
  before=len(self.calls());self.assertEqual(self.run_bootstrap().returncode,0)
  self.assertEqual(len(self.calls()),before+1)
  self.env['INTERNAL_API_TOKEN']='rotated-test-secret'
  self.assertEqual(self.run_bootstrap().returncode,0)
  self.assertEqual(sum(c[0]=='import:credentials' for c in self.calls()),2)
 def test_failure_has_no_marker_no_start_and_no_secret_log(self):
  self.env['MOCK_FAIL']='publish:workflow';r=self.run_bootstrap()
  self.assertNotEqual(r.returncode,0)
  self.assertNotIn(self.env['INTERNAL_API_TOKEN'],r.stdout+r.stderr)
  self.assertNotIn(['start'],self.calls())
  self.assertFalse((self.folder/'state/.n8n/pcl-bootstrap.json').exists())
