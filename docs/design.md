# Google storage → local disk automation: design notes

Status: thinking only, nothing built beyond the swipe page (`~/photo-swipe`). Written 2026-10-17.

**Scope decision (2026-10-17): Gmail + Drive only. Google Photos is out of scope**, so ignore the Takeout and
Photos items below.

## 1. Where the 15 GB actually goes

| Bucket | Size | Known? |
|---|---|---|
| Drive (owned files) | ~3.0 GB of 4.76 GB "in Drive" | measured |
| Gmail, messages > 1 MB | ~2.1 GB (434 msgs) | measured |
| Gmail, the other ~81,700 msgs | unknown, guess 2–4 GB | estimate |
| Google Photos | unknown, likely the gap (~3–6 GB) | **not visible to us** |
| Total used | 14.85 / 15 GB | measured |

First action: open one.google.com/storage, which shows the exact Gmail / Drive / Photos split. That decides
where the effort should go.

## 2. Hard platform limits (these shape the whole design)

1. **Google Photos cannot be read by an automated job.** Since March 2025 the Photos API only lets an app see
   photos *that app uploaded*. The only way to get the existing library out is **Google Takeout**, which
   can be set to "export every 2 months for 1 year". So Photos intake is semi-manual: Takeout emails a
   link, the download lands in an inbox folder, and the pipeline takes it from there.
   - Don't pick "deliver to Drive": it uses the quota we're trying to free.
2. **Google Photos cannot be deleted from by API.** Deletes happen in the web or phone app. The pipeline can
   produce a ready-made list or album to bulk-select, but the click is yours.
3. **Uploading back to Photos works** (append-only access), including creating albums. "Folder = album" is
   doable, so the folder layout you asked for maps cleanly.
4. **Drive**: the current token is read-only. Deleting needs a new sign-in with write access, which I'd keep
   separate from the tax tokens.
5. **Gmail**: the current token can trash but can't permanently delete. Trash empties itself after 30 days,
   which is a good safety net.

## 3. Pipeline (runs occasionally, e.g. monthly, via a Hermes scheduled job)

```
 PULL ─► VERIFY ─► DEDUPE ─► PRE-SORT (local AI) ─► YOU SWIPE ─► APPLY (gated) ─► CLOUD CLEANUP (gated)
```

1. **Pull.** Fetch only what's new since the last run: Drive changes, new large Gmail attachments, and any
   Takeout archive in `~/Downloads`. Files land under `/mnt/expansion/google-archive/<source>/<original folders>`.
2. **Verify.** Check every file against Google's checksum (Drive) or for a full download (Takeout zips).
   Nothing gets a "deletable from cloud" mark without a verified copy.
3. **Dedupe.** The same photo turns up in Drive, Gmail and Photos. An exact-hash pass removes copies, and a
   look-alike pass groups bursts and edited versions so you pick one per group, not five.
4. **Pre-sort** (§4). Each item gets a suggested label and a confidence score.
5. **Swipe.** The page groups by suggestion: "probably delete: 340 items" gets reviewed fast as a grid, and
   the uncertain ones get one-by-one swiping. You always make the final call.
6. **Apply.** Move files into `cloud/`, `local/` and `delete/`, keeping folders. Local deletes go to a
   holding folder for 30 days, never straight to `rm`.
7. **Cloud cleanup.** Trash the Gmail messages, delete the Drive files, and hand you the Photos list. Each
   step asks for confirmation with counts and sizes, and a Discord ping says "N items ready to review".

## 4. The "intelligence": cheap signals first, model second

Most decisions don't need a big model:

| Signal | Tool | Catches |
|---|---|---|
| Blur / darkness | plain image math, no model | accidental shots, pocket photos |
| Screenshot | dimensions + missing camera data | screenshots, saved memes |
| Near-duplicates | perceptual hash | bursts, WhatsApp re-saves |
| What's in it | **CLIP-style image embeddings** (small, runs on dcmini's CPU) | receipts, documents, people, landscapes, food, memes |
| Your taste | **tiny classifier trained on your swipes** | learns "he always deletes food pics" |
| Hard cases | vision LLM (e.g. Qwen2.5-VL 3B/7B) on Predator in `llm` mode | one-line descriptions for ambiguous photos |

Why this order:
- The embedding plus your swipe history is the part that **learns**. After a few hundred swipes it predicts
  your choices, and it gets better every run.
- The vision LLM is slow on a GTX 1060 (about 5–15 s per image), so it's only for leftovers. It would block
  Predator for other jobs, so it runs in a booked window.
- Everything stays on your machines. No photos go to a cloud model.

Hard rules:
- AI only **suggests**. Nothing is deleted without your swipe or bulk approval.
- Anything that looks like a document, ID, receipt or tax paper gets forced into a "review carefully" pile,
  never auto-sorted into delete.

## 5. Risks to decide on

1. **One disk = one copy.** Once something is "local only" and deleted from Google, the expansion drive is
   its only home. A dead drive loses it for good. You need a second copy of `local/`: Predator's disk, a
   second USB drive, or an encrypted copy on cheap cloud.
   **This is the most important decision in the whole plan.**
2. **Personal data.** Photos, IDs and tax attachments are sensitive. Keep the archive folder private and
   never push it anywhere (existing rule).
3. **Sign-in expiry.** If the Google app is in "testing" mode, tokens can stop working. The job should warn
   on Discord rather than fail silently.
4. **Predator contention.** The vision model needs `mode llm`. Schedule it, don't grab the GPU ad hoc.

## 6. Suggested build order

1. You check the storage split (one.google.com/storage) and decide the second-copy location.
2. Finish the current Drive pull and swipe. This gives the first ~1,000 labelled examples for free.
3. Add blur, screenshot and duplicate signals, plus CLIP suggestions, to the swipe page (dcmini only, no Predator).
4. Train the taste classifier from your swipes.
5. Add the monthly Hermes job: incremental pull, plus a Discord ping.
6. Add the Takeout intake for Photos.
7. Add Predator vision-LLM descriptions for hard cases, only if 3–4 aren't good enough.

## Open questions for you

- What does the storage page say: is Photos the big one?
- Where should the second copy of "local only" photos live?
- Monthly, or "when storage passes 80%"?
