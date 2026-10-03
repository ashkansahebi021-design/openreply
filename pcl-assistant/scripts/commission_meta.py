"""Engineer-run authenticated preflight. Never sends Instagram messages."""
import os,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.clients import Clients,APIError
from app.settings import Settings
s=Settings.from_env();c=Clients(s)
if not re.fullmatch(r'\d+',s.account_id) or not s.meta_token:raise SystemExit('Missing account/token')
base='https://graph.instagram.com/'+s.graph_version
try:
 profile=c.request(base+'/me?fields=id,user_id,username',token=s.meta_token)
 if str(profile.get('user_id',profile.get('id')))!=s.account_id:raise SystemExit('Token account does not match configured Instagram account')
 permissions=c.request(base+'/me/permissions',token=s.meta_token)
 needed={'instagram_business_basic','instagram_business_manage_comments','instagram_business_manage_messages'}
 granted={p['permission'] for p in permissions.get('data',[]) if p.get('status')=='granted'}
 if not needed<=granted:raise SystemExit('Missing scopes: '+','.join(sorted(needed-granted)))
 subscriptions=c.request(base+'/'+s.account_id+'/subscribed_apps',token=s.meta_token)
 fields={f for app in subscriptions.get('data',[]) for f in app.get('subscribed_fields',[])}
 if not {'messages','comments'}<=fields:raise SystemExit('Engineer must configure messages/comments subscriptions')
except APIError:raise SystemExit('Meta preflight failed; inspect owner dashboard. No secret output.') from None
print('Account, scopes and subscriptions verified. Complete test-account DM/comment/story tests and app access-level review before enabling live sends.')
