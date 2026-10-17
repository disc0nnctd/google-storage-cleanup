"""Shared Gmail client + SQLite index for mail-swipe."""
import sqlite3,time,os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
TOKEN=os.path.expanduser(os.environ.get('GMAIL_TOKEN','~/.config/google-storage-cleanup/gmail_token.json'))  # needs gmail.modify
DB=os.environ.get('MAILSWIPE_DB') or os.path.join(os.path.dirname(os.path.abspath(__file__)),'index.db')
def service():
    c=Credentials.from_authorized_user_file(TOKEN)
    if not c.valid:c.refresh(Request())
    return build('gmail','v1',credentials=c,cache_discovery=False)
def db():
    con=sqlite3.connect(DB,timeout=30);con.row_factory=sqlite3.Row
    con.execute('''create table if not exists msg(id text primary key,thread text,sender text,name text,subject text,
      date integer,size integer,labels text,unsub text,state text default 'live')''')
    con.execute('create index if not exists msg_sender on msg(sender)')
    con.execute('create table if not exists sender_note(sender text primary key,decision text,at integer)')
    con.execute('create table if not exists action(id integer primary key,at integer,sender text,kind text,ids text)')
    if 'batch' not in [c[1] for c in con.execute('pragma table_info(action)')]:
        try:con.execute('alter table action add column batch integer')   # bulk actions share a batch id: one undo step
        except sqlite3.OperationalError:pass   # another thread added it first
    con.execute('''create table if not exists sender_ai(sender text primary key,category text,subcategory text,action text,
        confidence real,reason text,n_at integer,model text,at integer)''')
    return con
