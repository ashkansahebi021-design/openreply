"""Offline deployment checks, no external calls."""
import json,re,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from app.engine import validate_rule
for r in json.loads((root/'config/rules.example.json').read_text()):validate_rule(r)
for p in (root/'workflows').glob('pcl-*.json'):
 d=json.loads(p.read_text());names={n['name'] for n in d['nodes']}
 assert d['active'] is False
 for name,links in d['connections'].items():
  assert name in names
  for branch in links.get('main',[]):
   for target in branch:assert target['node'] in names
 assert d['settings']['saveDataSuccessExecution']=='none'
 assert not re.search(r'sk-[a-zA-Z0-9]{20,}',p.read_text())
print('Rule validation, workflow links, inactive defaults and log-retention settings passed')
