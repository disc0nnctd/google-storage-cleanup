#!/usr/bin/env python3
"""Daily money-mail cleanup: apply the keep rules to every bank/card/broker sender, through the running
Mail Swipe server (same queue, same one-step Undo, same 'never touch statements' guarantee).

  autoclean.py             dry run: print what would go
  autoclean.py --apply     queue it
Rules (gmailapi.TYPE_KEEP): transaction alerts 90 days, OTP/login alerts 7 days, offers 0, notices 1 year, records forever.
Senders you swiped "Keep" on in the 💳 Money view are skipped.
"""
import json,sys,urllib.request
B='http://127.0.0.1:8092'
senders=json.load(urllib.request.urlopen(B+'/senders?cat=money',timeout=300))
todo=[s for s in senders if s['old']>0 and not s['note']]
em=sum(s['old'] for s in todo);mb=sum(s['old_size'] for s in todo)/1e6
print(f'{len(todo)} money senders, {em} emails, {mb:.1f} MB past their keep time')
for s in sorted(todo,key=lambda s:-s['old'])[:10]:print(f"  {s['old']:6} {s['sender']}")
if '--apply' in sys.argv and todo:
    req=urllib.request.Request(B+'/accept_rules',data=json.dumps({'senders':[s['sender'] for s in todo]}).encode(),method='POST')
    print('queued:',json.load(urllib.request.urlopen(req,timeout=60)))
