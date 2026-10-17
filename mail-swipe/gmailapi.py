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
    return con
