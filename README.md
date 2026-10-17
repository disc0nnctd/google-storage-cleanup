# google-storage-cleanup

Free up Google storage (Gmail + Drive) from your phone, by swiping. Everything runs on your own machine and is
served only on your Tailscale network.

| App | Port | What it does |
|---|---|---|
| **Photo Swipe** (`photo-swipe/`) | 8091 | Sort a local Drive backup: → Google Photos · ↑ Google Drive · ↓ local only · ← delete. Has a whole-folder move, a "5 from this folder" hint, review tabs and a server-side Undo. Its **📱 Send** button pushes the Google Photos picks to your phone over Syncthing, where Google Photos backs them up. |
| **Mail Swipe** (`mail-swipe/`) | 8092 | One card per sender: ← trash all · ↓ trash > 1 year · → keep · skip. Starred and sent mail are never touched. Bank/tax/ID-looking senders ask first. Every action is logged with exact message ids and can be undone or restored. |
| `mail-swipe/classify.py` | – | AI sender classifier (default: `gpt-6-luna`, low effort, via the local codex-lb proxy). Gives each sender a category, a subcategory, a suggested action and a reason. Only metadata (names, counts, subject lines) is sent, never bodies. Incremental; re-run after `index.py`. |
| `tools/drive_backup.py` | – | `report` (quota, biggest files, duplicates) and `backup DEST` (incremental, md5-verified, keeps Drive dates and folder layout). |

## Setup

1. **Google tokens.** Create authorized-user JSON tokens with your own OAuth client: Gmail `gmail.modify`, and Drive
   `drive.readonly` (`drive` if you want deletes later).
2. **Config.** `cp config.example.env ~/.config/google-storage-cleanup/config.env`, fill it in, then `chmod 600` it.
3. **Python.** Photo Swipe needs `pillow` and `qrcode`. Mail Swipe and the tools need `google-api-python-client` and `google-auth`.
4. **Back up Drive.** `DRIVE_TOKEN=... tools/drive_backup.py backup /mnt/expansion/gdrive-backup`
5. **Index Gmail.** `cd mail-swipe && GMAIL_TOKEN=... python index.py` (metadata only; about 40 min for 80k emails; re-run any time for new mail).
   **Then classify.** `python classify.py` (about 15 min for ~3k senders) adds the 🤖 suggestions, filters and *Accept all*.
6. **Install services.** `deploy/install.sh /mnt/expansion/gdrive-backup /path/to/venv/bin/python`
7. **Phone sync (optional).** `sudo apt install syncthing && sudo systemctl enable --now syncthing@$USER`, then follow
   the 📱 Send panel. Install Syncthing-Fork on the phone, scan the QR code, accept the folder as *Receive only*,
   and turn on backup for it in Google Photos.

## Safety notes

- Gmail actions use Gmail's Trash, which is recoverable for 30 days. Gmail's `untrash` does **not** put the INBOX
  label back; Mail Swipe re-adds it on undo.
- Photo decisions are only labels until you act on them (`apply.py --dry-run`, the Send button).
- The backup disk may be exFAT, which has no hard links or symlinks, so the phone folder holds real copies.
- Test without touching real mail: `MAILSWIPE_DRYRUN=1 MAILSWIPE_DB=/tmp/copy.db python server.py 8098`.
- Personal state (`decisions.json`, `history.json`, `index.db`, thumbnails) is git-ignored. Keep it that way.

`docs/design.md` covers the wider plan. `docs/mailclean-review.md` explains why this doesn't use mailclean-py.
