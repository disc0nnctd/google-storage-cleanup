#!/usr/bin/env python3
"""Mail Swipe: triage Gmail one sender at a time (trash all / trash old / keep).

Trash is Gmail's own Trash (auto-emptied after 30 days, restorable). Every action is logged in
index.db:action with the exact message ids, so Undo / Restore untrashes precisely those.
Never touches: starred mail, mail you sent, mail from your own address.
"""
import json,os,re,sys,time,threading
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from gmailapi import service,db
PORT=int(sys.argv[1]) if len(sys.argv)>1 else 8092
HERE=os.path.dirname(os.path.abspath(__file__))
LOG=os.environ.get('MAILSWIPE_LOG') or os.path.join(HERE,'index.log')
YEAR=365*86400
CATS={'promotions':'CATEGORY_PROMOTIONS','social':'CATEGORY_SOCIAL','updates':'CATEGORY_UPDATES',
      'forums':'CATEGORY_FORUMS','primary':'CATEGORY_PERSONAL'}
# Money, tax, identity, health: flagged so trashing them takes an extra confirmation.
PROTECT=re.compile(r'bank|icici|hdfc|sbi\b|axis|kotak|yes ?bank|idfc|indusind|rbl|nsdl|cdsl|zerodha|kite|groww|'
    r'dhan|upstox|angel|paytm money|incometax|income tax|\bitr\b|form ?16|\btds\b|traces|gst|epfo|\bpf\b|uan|'
    r'insurance|\blic\b|policy|bajaj|hdfc ?life|star ?health|demat|cams|kfin|mutual fund|\bsip\b|nps|'
    r'aadhaar|\bpan\b|passport|uidai|digilocker|statement|invoice|receipt|salary|payslip|loan|emi|'
    r'credit card|tax|hospital|medical|lab report|apollo|practo',re.I)
lock=threading.Lock()
_svc=None
def svc():
    global _svc
    if _svc is None:_svc=service()
    return _svc

_profile=None
def profile():
    global _profile
    if _profile is None:_profile=svc().users().getProfile(userId='me').execute()
    return _profile
def me():return profile()['emailAddress'].lower()

def eligible(r):
    """Messages we are allowed to trash."""
    labs=r['labels'].split(',')
    return r['state']=='live' and 'STARRED' not in labs and 'SENT' not in labs and r['sender']!=me()

_cache={};_ver=[0]
def bump():_ver[0]+=1;_cache.clear()
def senders(cat):
    aiv=db().execute('select count(*),max(at) from sender_ai').fetchone()   # new AI results also refresh the list
    k=(cat,aiv[0],aiv[1])
    if k in _cache:return _cache[k]
    _cache[k]=_senders(cat);return _cache[k]
def _senders(cat):
    con=db();notes={r['sender']:r['decision'] for r in con.execute('select * from sender_note')}
    ai={r['sender']:r for r in con.execute('select * from sender_ai')}
    rows=con.execute("select * from msg where state='live'").fetchall()
    g={}
    want=CATS.get(cat)
    for r in rows:
        labs=r['labels']
        if want and want not in labs:continue
        if cat=='primary' and 'SENT' in labs:continue
        s=g.setdefault(r['sender'],dict(sender=r['sender'],name='',n=0,size=0,first=r['date'],last=0,starred=0,unread=0,
            trashable=0,old=0,old_size=0,subjects=[],unsub='',cats={}))
        s['n']+=1;s['size']+=r['size'];s['first']=min(s['first'],r['date'])
        if r['date']>=s['last']:
            s['last']=r['date'];s['name']=r['name'] or s['name']
            if r['unsub']:s['unsub']=r['unsub']
        if 'STARRED' in labs:s['starred']+=1
        if 'UNREAD' in labs:s['unread']+=1
        if eligible(r):
            s['trashable']+=1
            if r['date']<time.time()-YEAR:s['old']+=1;s['old_size']+=r['size']
        s['subjects'].append((r['date'],r['subject']))
        for k,v in CATS.items():
            if v in labs:s['cats'][k]=s['cats'].get(k,0)+1
    out=[]
    for s in g.values():
        if s['sender']==me():continue
        s['subjects']=[t for _,t in sorted(s['subjects'],reverse=True)[:6]]
        s['note']=notes.get(s['sender'])
        a=ai.get(s['sender'])
        s['ai']=dict(action=a['action'],category=a['category'],sub=a['subcategory'],conf=a['confidence'],reason=a['reason']) if a else None
        hit=PROTECT.search(' '.join([s['sender'],s['name']]+s['subjects']))
        s['protect']=hit.group(0) if hit else ''
        out.append(s)
    out.sort(key=lambda s:-s['size'])
    return out

def batch_call(ids,method):
    """messages.trash / untrash in HTTP batches of 50, retrying rate-limited ones. Returns ids that succeeded."""
    if os.environ.get('MAILSWIPE_DRYRUN'):return list(ids),[]
    ok=[];todo=list(ids);tries=0
    while todo and tries<6:
        failed=[]
        for i in range(0,len(todo),50):
            chunk=todo[i:i+50]
            def cb(rid,resp,exc,_f=failed,_o=ok):
                (_f if exc is not None else _o).append(rid)
            b=svc().new_batch_http_request(callback=cb)
            for m in chunk:b.add(getattr(svc().users().messages(),method)(userId='me',id=m),request_id=m)
            b.execute();time.sleep(0.4)
        todo=failed;tries+=1
        if todo:time.sleep(2*tries)
    return ok,todo

def act(sender,kind,batch=None,cat='all'):
    try:return _act(sender,kind,batch,cat)
    finally:bump()   # after the change, so a read mid-action can't cache stale data
def _act(sender,kind,batch=None,cat='all'):
    with lock:
        con=db()
        if kind in('keep','skip'):
            con.execute('insert or replace into sender_note values(?,?,?)',(sender,kind,int(time.time())))
            aid=con.execute('insert into action(at,sender,kind,ids,batch) values(?,?,?,?,?)',(int(time.time()),sender,kind,'[]',batch)).lastrowid;con.commit()
            return dict(ok=True,n=0,id=aid)
        if kind=='unnote':
            con.execute('delete from sender_note where sender=?',(sender,));con.commit();return dict(ok=True,n=0)
        rows=[r for r in con.execute("select * from msg where sender=? and state='live'",(sender,)) if eligible(r)]
        if CATS.get(cat):rows=[r for r in rows if CATS[cat] in r['labels'].split(',')]   # only the Gmail tab the card showed
        if kind=='trash_old':rows=[r for r in rows if r['date']<time.time()-YEAR]
        ids=[r['id'] for r in rows]
        if not ids:return dict(ok=True,n=0,size=0,id=None)
        ok,bad=batch_call(ids,'trash')
        con.executemany("update msg set state='trashed' where id=?",[(i,) for i in ok])
        size=sum(r['size'] for r in rows if r['id'] in set(ok))
        aid=con.execute('insert into action(at,sender,kind,ids,batch) values(?,?,?,?,?)',(int(time.time()),sender,kind,json.dumps(ok),batch)).lastrowid
        con.execute('insert or replace into sender_note values(?,?,?)',(sender,'trashed' if kind=='trash_all' else 'trimmed',int(time.time())))
        con.commit()
        return dict(ok=not bad,n=len(ok),failed=len(bad),size=size,id=aid)

def undo(action_id):
    try:return _undo(action_id)
    finally:bump()
def _undo(action_id):
    with lock:
        con=db();a=con.execute('select * from action where id=?',(action_id,)).fetchone()
        if not a:return dict(ok=False)
        ids=json.loads(a['ids'])
        ok,bad=batch_call(ids,'untrash') if ids else ([],[])
        # Gmail's untrash drops the INBOX label; put it back on the ones that had it.
        inbox=[i for i in ok if 'INBOX' in (con.execute('select labels from msg where id=?',(i,)).fetchone() or [''])[0].split(',')]
        if inbox and not os.environ.get('MAILSWIPE_DRYRUN'):
            for k in range(0,len(inbox),1000):
                svc().users().messages().batchModify(userId='me',body={'ids':inbox[k:k+1000],'addLabelIds':['INBOX']}).execute()
        con.executemany("update msg set state='live' where id=?",[(i,) for i in ok])
        con.execute('delete from sender_note where sender=?',(a['sender'],))
        if not bad:con.execute('delete from action where id=?',(action_id,))
        con.commit()
        return dict(ok=not bad,n=len(ok),failed=len(bad))

JOB={'running':False}
def start_job(title,work):
    if JOB.get('running'):return dict(ok=False,error='Another bulk job is still running')
    JOB.clear();JOB.update(running=True,title=title,done=0,total=0,emails=0,size=0,failed=0,error=None)
    def run():
        try:work(JOB)
        except Exception as e:JOB['error']=str(e)[:300]
        finally:JOB['running']=False;bump()
    threading.Thread(target=run,daemon=True).start()
    return dict(ok=True)

def accept_ai(senders_list,cat='all'):
    batch=int(time.time()*1000)
    def work(j):
        j['total']=len(senders_list);j['batch']=batch
        for snd in senders_list:
            a=db().execute('select action from sender_ai where sender=?',(snd,)).fetchone()
            if not a or a['action'] not in('trash_all','trash_old','keep'):j['done']+=1;continue
            r=act(snd,a['action'],batch,cat)
            j['done']+=1;j['emails']+=r.get('n',0);j['size']+=r.get('size',0) or 0;j['failed']+=r.get('failed',0) or 0
    return start_job('Applying AI suggestions',work)

def undo_last_job():
    con=db();a=con.execute('select id,sender,kind,batch from action order by id desc limit 1').fetchone()
    if not a:return dict(ok=False,none=True)
    if not a['batch']:
        r=undo(a['id']);r.update(sender=a['sender'],kind=a['kind']);return r
    ids=[r['id'] for r in con.execute('select id from action where batch=?',(a['batch'],))]
    def work(j):
        j['total']=len(ids)
        for i in ids:
            r=undo(i);j['done']+=1;j['emails']+=r.get('n',0);j['failed']+=r.get('failed',0)
    r=start_job('Undoing bulk action',work);r.update(job=True,senders=len(ids));return r

def history():
    con=db();out=[]
    for a in con.execute("select * from action where kind like 'trash%' order by at desc limit 500"):
        ids=json.loads(a['ids'])
        sz=con.execute(f"select coalesce(sum(size),0),max(name) from msg where id in ({','.join('?'*len(ids))})",ids).fetchone() if ids else (0,'')
        out.append(dict(id=a['id'],at=a['at'],sender=a['sender'],name=sz[1] or '',kind=a['kind'],n=len(ids),size=sz[0]))
    kept=[dict(sender=r['sender'],decision=r['decision'],at=r['at']) for r in con.execute(
        "select * from sender_note where decision in('keep','skip','trimmed') order by at desc")]
    return dict(trashed=out,kept=kept)

def stats():
    con=db()
    live=con.execute("select count(*),coalesce(sum(size),0) from msg where state='live'").fetchone()
    tr=con.execute("select count(*),coalesce(sum(size),0) from msg where state='trashed'").fetchone()
    log=open(LOG).read().split('\n') if os.path.exists(LOG) else []
    indexing=not any(l.startswith('DONE') for l in log)
    last=con.execute('select sender,kind,batch from action order by id desc limit 1').fetchone()
    if last and last['batch']:
        n=con.execute('select count(*) from action where batch=?',(last['batch'],)).fetchone()[0]
        last=dict(sender=f'{n} senders',kind='bulk',batch=last['batch'])
    return dict(live=live[0],live_size=live[1],trashed=tr[0],trashed_size=tr[1],indexing=indexing,total=profile().get('messagesTotal',0),
                actions=con.execute('select count(*) from action').fetchone()[0],last=dict(last) if last else None)

class H(BaseHTTPRequestHandler):
    def log_message(s,*a):pass
    def send(s,code,obj,ct='application/json'):
        body=obj if isinstance(obj,bytes) else json.dumps(obj).encode()
        s.send_response(code);s.send_header('Content-Type',ct);s.send_header('Content-Length',str(len(body)))
        s.send_header('Cache-Control','no-store');s.end_headers();s.wfile.write(body)
    def do_GET(s):
        u=urlparse(s.path);q=parse_qs(u.query)
        if u.path=='/':return s.send(200,open(os.path.join(HERE,'index.html'),'rb').read(),'text/html; charset=utf-8')
        if u.path=='/senders':return s.send(200,senders(q.get('cat',['promotions'])[0]))
        if u.path=='/history':return s.send(200,history())
        if u.path=='/stats':return s.send(200,stats())
        if u.path=='/job':return s.send(200,{k:v for k,v in JOB.items()})
        s.send(404,{})
    def do_POST(s):
        d=json.loads(s.rfile.read(int(s.headers.get('Content-Length',0))) or b'{}')
        try:
            if s.path=='/act':return s.send(200,act(d['sender'],d['kind'],cat=d.get('cat','all')))
            if s.path=='/undo':return s.send(200,undo(int(d['id'])))
            if s.path=='/undo_last':return s.send(200,undo_last_job())
            if s.path=='/accept_ai':return s.send(200,accept_ai(d['senders'],d.get('cat','all')))
        except Exception as e:
            return s.send(500,dict(ok=False,error=str(e)[:300]))
        s.send(404,{})
ThreadingHTTPServer(('127.0.0.1',PORT),H).serve_forever()
