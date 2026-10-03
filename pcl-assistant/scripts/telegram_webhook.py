"""Engineer sets the approved Telegram bot webhook, preserving pending updates."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.clients import Clients
from app.settings import Settings
s=Settings.from_env();url=os.environ['PUBLIC_BASE_URL'].rstrip('/')
if not url.startswith('https://') or not s.telegram_secret:raise SystemExit('HTTPS and Telegram secret required')
Clients(s).telegram('setWebhook',{'url':url+'/webhooks/telegram','secret_token':s.telegram_secret,'allowed_updates':['message','callback_query'],'drop_pending_updates':False})
print('Telegram webhook configured')
