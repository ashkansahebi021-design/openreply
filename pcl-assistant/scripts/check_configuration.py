"""Readiness report; prints only variable names, never secret values."""
import os,sys
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from app.settings import Settings
s=Settings.from_env()
required=['IG_ACCOUNT_ID','META_ACCESS_TOKEN','META_APP_SECRET','WEBHOOK_VERIFY_TOKEN','OPENAI_API_KEY','TELEGRAM_BOT_TOKEN','TELEGRAM_WEBHOOK_SECRET','TELEGRAM_OWNER_USER_ID','INTERNAL_API_TOKEN']
missing=[k for k in required if not os.environ.get(k)]
print('Missing: '+', '.join(missing) if missing else 'Required credentials present')
print(f'DRY_RUN={s.dry_run}; OUTBOUND_ENABLED={s.outbound_enabled}; META_CAPABILITIES_VERIFIED={s.meta_verified}')
sys.exit(1 if missing else 0)
