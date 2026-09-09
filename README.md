# News Brief Desk

A Django + React newsroom demo. Ingests ~60 raw items a day (wire copy, press releases, blogs, social posts), clusters same-event items into candidate stories, lets reporters draft and editors publish one brief per real event, and surfaces desk-head analytics.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seeddesk --reset
python manage.py runserver
```

In a second terminal:

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies `/api` to Django.

For a production-style single-origin run (Django serves the built frontend):

```bash
cd frontend && npm run build
python manage.py collectstatic --noinput
python manage.py runserver
```

Then open http://localhost:8000.

## Demo accounts

| Username | Password | Role |
|---|---|---|
| `reporter` | `demo` | Reporter — triages inbox, drafts, submits |
| `editor` | `demo` | Editor — rewrites, publishes, merges, corrects |
| `deskhead` | `demo` | Desk Head — read-only analytics dashboard |

## End-to-end walkthrough

1. **Sign in as reporter** → `/inbox` — 60 items in the pile, 8 are noise
2. **Run Cluster** (or press `c`) — 40 candidate stories created, machine drafts written
3. Open a story → **Claim** → edit the brief → **Submit for Review**
4. **Sign in as editor** → open the story → rewrite → **Publish**
5. Open `/published/<slug>` — the public brief page
6. Try to publish as reporter — blocked (403)
7. **Post-publish merge**: find the Vizhinjam pair (two stories that share no entities at first), merge the loser into the winner — loser's publication becomes SUPERSEDED, winner gets Publication v2
8. **Sign in as deskhead** → `/desk` — yesterday's count, median dwell, stage breakdown, rewrite rate, dedup savings

## What the plan required — and what was built

| Requirement (their words) | Mechanism |
|---|---|
| "A reporter must not be able to push something live." | `desk/services/mutations.py::publish()` calls `_require_role(user, "EDITOR")` — raises `PermissionDenied` regardless of caller. Tested in `test_reporter_cannot_publish`. |
| "Once a brief is out, it is out." | `BriefRevision.save()` raises `ValueError` if `self.pk` is set. `Publication.save()` raises on any field change except `status`. Changes are new rows. Tested in `test_published_revision_is_never_mutated`. |
| "Two things that looked separate turn out to be the same event, after one has already gone out." | `Merge` model; loser's Publication → `SUPERSEDED` (still reachable at its URL); winner gets a `MERGE_NOTE` revision + new `Publication` v2 carrying both source sets. Tested in `test_post_publish_merge_supersedes_and_corrects`. |
| "How many went out yesterday, on what subjects, how long did each sit." | Timestamps at every hop (`first_item_received_at`, `claimed_at`, `submitted_at`, `first_published_at`) → `analytics/views.py::dashboard()` computes per-stage dwell, median, p90, rewrite rate, dedup savings. Tested in `test_yesterday_dwell_metrics`. |

## Decisions and assumptions

| Topic | Decision | Why |
|---|---|---|
| Auth | Session-based Django auth + DRF `SessionAuthentication` | Single origin — no CORS, no cross-site cookie issues that Safari/Brave block by default |
| Deployment | Single-origin: Vite builds into `frontend/dist`, Django serves both SPA and API via Whitenoise | One URL for the reviewer, no CORS config, no split-origin cookie problems |
| Database | SQLite locally, `DATABASE_URL` env var for Postgres on Render | Zero code difference; free Postgres is abundant where free MySQL is not |
| Clustering | Pure Python TF-IDF + entity + quantity + time blend — no numpy/sklearn | Keeps the ~100 MB numpy tree out of the deploy; the interesting part is the *blend*, not the vector maths. Documented in `brain/scoring.py` |
| No cosine similarity | Removed after measurement — tracked IDF-overlap to within a few points on symmetric pairs, strictly worse on asymmetric ones (social post vs wire copy) | `python -m brain.explain --dist` shows the gap |
| Confidence bands | `≥0.62` auto-cluster; `0.45–0.62` → human suggestion with reasoning shown; `<0.45` separate | The grey band is the honest answer. Silently merging or silently missing are both worse than "possible duplicate — review" |
| Hard vetoes | Conflicting death tolls, disjoint datelines, time gap >72h override any text score | Two NH-48 crashes and two pharma Phase-3 releases need this; text alone fails both |
| AI | Optional — `ANTHROPIC_API_KEY` upgrades brief drafting, borderline-pair adjudication, screenshot OCR. Deterministic path always works | A reviewer can run it cold. Disclosed here and in the UI |
| Desk head role | Read-only — no publish, no revise | Stated assumption: "desk head reads numbers" |
| Append-only revisions | `BriefRevision` rows are never updated or deleted — a guard in `save()` enforces this | Makes the editor's rewrite rate measurable and the history trustworthy |
| Immutable publications | `Publication` rows are immutable except for `status` — a guard in `save()` enforces this | "Once a brief is out, it is out" |

## AI tools used

- **Amazon Q Developer** — primary coding assistant throughout. Used for all file generation, debugging, and iteration.
- **Claude claude-3-5-haiku-20241022** (optional, via `ANTHROPIC_API_KEY`) — brief drafting, borderline-pair adjudication, screenshot OCR. The app works without it.

All AI-generated code was reviewed and tested. The clustering logic (`brain/`) was arrived at by measurement (`python -m brain.explain --dist`) not by prompting.

## Running the tests

```bash
python manage.py test desk.tests
```

Eight tests, named after the brief's own sentences:

1. `test_reporter_cannot_publish` — 403 at service layer, not just HTTP
2. `test_editor_can_publish` — Publication row created, story status updated
3. `test_published_revision_is_never_mutated` — correction inserts new row; original byte-identical
4. `test_three_wordings_become_one_story` — metro quartet from real seed data
5. `test_lookalike_pairs_stay_separate` — pharma pair and NH-48 crash pair
6. `test_post_publish_merge_supersedes_and_corrects` — loser SUPERSEDED, winner gets v2
7. `test_yesterday_dwell_metrics` — dashboard returns correct 180-minute dwell
8. `test_every_mutation_writes_an_audit_event` — claim/revise/submit/publish/correct all audited

## Verifying the clusterer without Django

```bash
python -m brain.explain                          # summary + accuracy
python -m brain.explain --dist                   # score distribution
python -m brain.explain --pairs                  # every scored pair
python -m brain.explain --case metro-purple-line-fault
```

## Project structure

```
newsbrief/
  manage.py              entry point
  requirements.txt
  render.yaml            Render.com deploy config
  Dockerfile
  config/                settings (env-driven), urls, wsgi
  accounts/              User(role), session auth endpoints
  ingest/                Source, RawItem, file + screenshot ingest
  desk/                  Story, StoryItem, BriefRevision, Publication, Merge, AuditEvent
    services/            mutations.py (all guarded + audited), clustering.py
  analytics/             dwell + stage + rewrite-rate dashboard
  brain/                 clustering, scoring, text, llm — no Django dependency
  seed/                  raw_items.json (60 items), sources.json, seeddesk command
  frontend/              Vite + React + TypeScript + Tailwind v4
    src/
      pages/             Login, Inbox, Stories, StoryWorkspace, PublishedBrief, Ingest, Desk
      components/        Nav, ui primitives
      hooks/             useAuth
      lib/               api.ts (all API calls + types)
```

## If I had another week

- Richer merge adjudication: show the similarity signals side-by-side in the merge UI
- LLM-assisted duplicate checks on the grey-band suggestions
- Screenshot OCR quality: pre-process with PIL before sending to Claude
- Production hardening: rate limiting, structured logging, Sentry, health check endpoint
- Real-time inbox updates via SSE or WebSocket
- Mobile-responsive layout
