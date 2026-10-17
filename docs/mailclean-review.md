# mailclean-py review (cedrichan/mailclean-py @ f1b1dd3, 2026-03-19)

I read the code only and didn't run it. It's about 250 lines of real logic, uses the Gmail API with the
`gmail.modify` scope, and has no network calls beyond Google. Nothing malicious.

**Verdict: don't run it on your inbox as-is, and especially not `oneshot.py`.** The idea is right; the
safety checks are not.

## Data-loss bugs

1. **The "safety check" protects nothing.** `delete_labeled_messages` skips an original only if *the
   original* has the POST_CLEANUP label, but only the new copies ever get that label. So every
   PRE_CLEANUP message is trashed whether or not its attachments were saved. If `insert_message` or the
   save step fails (the error is caught and printed), `oneshot.py` still trashes the original in step 3.
2. **Same-name attachments overwrite each other.** Two `image.jpg` files in one mail means only one survives.
3. **Attachments without a filename are dropped.** Inline images (pasted photos, signatures) have no
   filename, so they're neither saved nor kept. That's likely in your self-sent mails (~1.1 GB).
4. **No check after saving.** It never confirms the files on disk match what was in the mail.
5. **A part with a filename but an empty body crashes the run** (`write_bytes(None)`) halfway through.

## Smaller problems

- **No pagination.** It only handles the first ~100 matches per run.
- **The cleaned copy loses all labels** (Inbox, Starred, Important, your own labels) and gets only
  POST_CLEANUP.
- The default 20 MB threshold would catch almost none of your 434 large mails. Most are 1–10 MB.

## Recommendation: our own ~120-line version of the same idea

1. Save the **full original `.eml`** to `/mnt/expansion/google-archive/gmail/<year>/<date - sender - subject>/`,
   plus the extracted attachments with collision-safe names, so they're easy to browse.
2. Verify the saved `.eml` byte size and that it re-parses to the same attachment count and sizes.
3. Insert the stripped copy with **the original's labels** and a note listing the removed attachments.
4. Trash the original **only if** steps 1–3 all succeeded for that message. Trash empties itself after 30 days.
5. Dry run first: a table of what would be processed, which you approve.
6. Keep anything from banks, brokers, NSDL, insurers, or matching tax / ITR / Form 16 terms in Gmail
   untouched (archive-copy only), unless you say otherwise.
