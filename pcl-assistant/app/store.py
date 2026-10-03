import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

SCHEMA='''
CREATE TABLE IF NOT EXISTS events (
 id TEXT PRIMARY KEY, account TEXT NOT NULL, user_id TEXT NOT NULL, username TEXT NOT NULL,
 kind TEXT NOT NULL, text TEXT NOT NULL, media_id TEXT NOT NULL, timestamp REAL NOT NULL,
 conversation_version INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending', lease TEXT, lease_until REAL DEFAULT 0,
 attempts INTEGER DEFAULT 0, category TEXT, confidence REAL, draft TEXT, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS events_pending ON events(status,lease_until);
CREATE TABLE IF NOT EXISTS conversations (
 user_id TEXT PRIMARY KEY, username TEXT NOT NULL DEFAULT '', lead_state TEXT NOT NULL DEFAULT 'new',
 version INTEGER NOT NULL DEFAULT 0, last_inbound REAL DEFAULT 0, last_interaction REAL DEFAULT 0,
 pending INTEGER DEFAULT 0, intent TEXT, last_response TEXT);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY, event_id TEXT, user_id TEXT, role TEXT, text TEXT, timestamp REAL);
CREATE INDEX IF NOT EXISTS messages_user ON messages(user_id,id);
CREATE TABLE IF NOT EXISTS rules (
 id TEXT PRIMARY KEY, trigger TEXT NOT NULL, media_id TEXT NOT NULL DEFAULT '*',
 keyword TEXT NOT NULL, response TEXT NOT NULL, approval INTEGER NOT NULL DEFAULT 0,
 active INTEGER NOT NULL DEFAULT 1, priority INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS approvals (
 id TEXT PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, user_id TEXT NOT NULL, draft TEXT NOT NULL,
 category TEXT NOT NULL, confidence REAL NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 conversation_version INTEGER NOT NULL, expires REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 telegram_message_id INTEGER, edit_prompt_id INTEGER);
CREATE TABLE IF NOT EXISTS outbox (
 id TEXT PRIMARY KEY, channel TEXT NOT NULL, event_id TEXT, approval_id TEXT,
 payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER DEFAULT 0,
 next_at REAL NOT NULL DEFAULT 0, started_at REAL, sent_at REAL, provider_id TEXT, error TEXT);
CREATE INDEX IF NOT EXISTS outbox_pending ON outbox(status,next_at);
CREATE TABLE IF NOT EXISTS telegram_updates (
 id INTEGER PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, timestamp REAL NOT NULL, event_id TEXT, action TEXT NOT NULL, details TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS usage (day TEXT PRIMARY KEY,calls INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS controls (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS telegram_receipts (id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS public_users (
 user_id TEXT PRIMARY KEY,username TEXT NOT NULL DEFAULT '',lead_state TEXT NOT NULL DEFAULT 'new',last_interaction REAL NOT NULL);
CREATE TABLE IF NOT EXISTS public_messages (
 id INTEGER PRIMARY KEY,user_id TEXT NOT NULL,role TEXT NOT NULL,text TEXT NOT NULL,created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS public_messages_user ON public_messages(user_id,id);
CREATE TABLE IF NOT EXISTS public_tickets (
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL,category TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',
 version INTEGER NOT NULL DEFAULT 1,created REAL NOT NULL,updated REAL NOT NULL,draft TEXT NOT NULL DEFAULT '',
 notice_id INTEGER,edit_prompt_id INTEGER);
CREATE INDEX IF NOT EXISTS public_tickets_user ON public_tickets(user_id,status);
CREATE TABLE IF NOT EXISTS public_receipts (id INTEGER PRIMARY KEY,user_id TEXT NOT NULL,created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS public_receipts_user ON public_receipts(user_id,created);
CREATE TABLE IF NOT EXISTS public_prompts (id TEXT PRIMARY KEY,title TEXT NOT NULL,text TEXT NOT NULL,aliases TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS public_faqs (keyword TEXT PRIMARY KEY,response TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
'''

class Store:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        self.db=sqlite3.connect(path,check_same_thread=False,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA busy_timeout=5000')
        self.db.executescript(SCHEMA)
        # Compact tombstones survive payload retention and prevent duplicate owner/public sends.
        self.db.execute('INSERT OR IGNORE INTO telegram_receipts SELECT id FROM telegram_updates')

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self.db
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise

    def rows(self,sql,args=()):
        with self.lock:return [dict(r) for r in self.db.execute(sql,args)]

    def one(self,sql,args=()):
        rows=self.rows(sql,args)
        return rows[0] if rows else None

    @staticmethod
    def audit(db,now,event,action,details=None):
        # Only caller-controlled operational identifiers, never raw errors/tokens/user messages.
        db.execute('INSERT INTO audit(timestamp,event_id,action,details) VALUES(?,?,?,?)',
                   (now,event,action,json.dumps(details or {},ensure_ascii=False)))
