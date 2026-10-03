import os
from dataclasses import dataclass

@dataclass
class Settings:
    db_path: str = 'data/pcl.sqlite3'
    account_id: str = ''
    meta_token: str = ''
    meta_secret: str = ''
    verify_token: str = ''
    graph_version: str = 'v25.0'
    openai_key: str = ''
    model: str = 'gpt-4.1-mini'
    strong_model: str = ''
    telegram_token: str = ''
    telegram_secret: str = ''
    public_base_url: str = ''
    owner_id: str = ''
    internal_token: str = ''
    dry_run: bool = True
    outbound_enabled: bool = False
    meta_verified: bool = False
    confidence: float = .88
    ai_daily_limit: int = 100
    approval_ttl: int = 3600
    context_limit: int = 12
    retention_days: int = 30
    send_per_minute: int = 10

    @classmethod
    def from_env(cls):
        names={'db_path':'DATABASE_PATH','account_id':'IG_ACCOUNT_ID','meta_token':'META_ACCESS_TOKEN',
               'meta_secret':'META_APP_SECRET','verify_token':'WEBHOOK_VERIFY_TOKEN','graph_version':'META_GRAPH_API_VERSION',
               'openai_key':'OPENAI_API_KEY','model':'OPENAI_MODEL','strong_model':'OPENAI_STRONG_MODEL',
               'telegram_token':'TELEGRAM_BOT_TOKEN','telegram_secret':'TELEGRAM_WEBHOOK_SECRET',
               'public_base_url':'PUBLIC_BASE_URL',
               'owner_id':'TELEGRAM_OWNER_USER_ID','internal_token':'INTERNAL_API_TOKEN',
               'dry_run':'DRY_RUN','outbound_enabled':'OUTBOUND_ENABLED','meta_verified':'META_CAPABILITIES_VERIFIED',
               'confidence':'AUTO_REPLY_CONFIDENCE','ai_daily_limit':'AI_DAILY_CALL_LIMIT',
               'approval_ttl':'APPROVAL_TTL_SECONDS','context_limit':'CONTEXT_LIMIT',
               'retention_days':'RETENTION_DAYS','send_per_minute':'SEND_PER_MINUTE'}
        defaults=cls();values={}
        for key,env in names.items():
            raw=os.environ.get(env)
            if raw is None:continue
            typ=type(getattr(defaults,key))
            values[key]=raw.lower()=='true' if typ is bool else typ(raw)
        s=cls(**values)
        if not 0<=s.confidence<=1 or s.ai_daily_limit<0 or s.context_limit<1 or s.send_per_minute<1:
            raise ValueError('Invalid runtime limits')
        return s
