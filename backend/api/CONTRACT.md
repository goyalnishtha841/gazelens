# Session API contract

The integration layer. Every other backend module does one job; this one calls
them in order and is the only place that knows about all of them.

```
POST /api/sessions                 -> create
POST /api/sessions/{id}/calibration -> link calibration + train gaze model
POST /api/sessions/{id}/gaze        -> append gaze batches
POST /api/sessions/{id}/finalize    -> attribution -> agents -> reports
GET  /api/sessions/{id}/report      -> the finished report (202 while pending)
```

---

## 1. The contract is provisional — `client.js` is not in this repo

The brief said to read `frontend/src/api/client.js` and map endpoints 1:1
against what it mocks. **There is no `frontend/` directory.** It has never
been pushed to `origin/main`, and neither has `backend/render/`. The README
describes both as built.

So the shape below was derived from the *screens* the README lists (landing,
auth, calibration, live session, dashboard, report view) rather than read off
the client. When the real `client.js` turns up, check these first:

| Likely mismatch | Where to change it |
|---|---|
| Endpoint paths (`/api/sessions` vs `/sessions`) | router `prefix` in `session_routes.py` |
| Field names (`id` vs `session_id`, `created_at` vs `createdAt`) | `schemas.py` only |
| Token envelope (`access_token`/`token_type`) | `schemas.TokenResponse` |
| Whether the client posts gaze at all, or expects server-side capture | `session_routes.append_gaze` |

Everything provisional is confined to `schemas.py` and the route decorators.
`models.py`, `pipeline.py` and `layouts.py` don't change if the wire format does.

### The auth that was supposed to exist

The brief also said to use `backend/api`'s existing JWT dependency. There
wasn't one — no users, no hashing, no tokens anywhere in the repo. Ownership
scoping is unbuildable without it, so it was built here: `security.py`
(bcrypt + PyJWT), `deps.get_current_user`, and the `users` table.

---

## 2. Data ownership — what this DB does and doesn't hold

The database is an **index that ties modules together**, not a second copy of
what they store.

| Data | Owner | How sessions reference it |
|---|---|---|
| Calibration samples | `backend/calibration` JSON store | `sessions.calibration_session_id` |
| Trained gaze model | `backend/gaze_estimation` | keyed by the same calibration id |
| Raw gaze stream | JSONL file per session | `sessions.gaze_path` |
| Metrics + agent findings | this DB (`reports`) | `reports.session_id` |

Gaze is a file, not a table, because it's append-only bulk timeseries (30Hz
for minutes) and nothing ever queries an individual point. Calibration is a
reference because copying it would create two truths about one participant
sitting.

`reports.pipeline_result` is stored **verbatim** as
`orchestrator.run_pipeline()` returned it — `behavior_summary`, `issues`,
`recommendations_kept`, `recommendations_rejected`. Not flattened or renamed:
`backend/reports` already consumes exactly that shape, and a second shape here
would be one more thing to keep in sync for nothing.

---

## 3. Session lifecycle

```
created ──calibration──> calibrated ──gaze──> recording ──finalize──> processing
                                                                        │
                                                          ┌─────────────┴────────┐
                                                       complete                failed
```

`GET /api/sessions/{id}` returns `next_action` (`calibrate`, `train_gaze_model`,
`record`, `finalize`, `wait`, `view_report`, `restart`) so the live-session UI
doesn't have to reimplement this state machine. Two copies of it would drift
the first time a status is added.

**Finalising is asynchronous.** The chain ends in a Chromium PDF render taking
seconds; holding the request open would time the browser out. `/finalize`
returns `202`-style immediately with `status: processing`, and `/report`
answers **202** — not 404 — until the report exists. A 404 would tell a
polling dashboard to give up on a resource that is about to appear.

**Failure is always terminal.** If the analysis raises, the session lands on
`failed` with the reason recorded. A session stuck on `processing` forever is
worse than one that says why it broke, because the dashboard polls it
indefinitely.

---

## 4. Ownership and auth

Every session route depends on `get_current_user`, and every lookup goes
through `deps.owned_session`. One function to audit, instead of a scoping
check repeated per route that someone eventually forgets.

**Another user's session returns 404, not 403.** A 403 confirms the id exists,
which makes session ids enumerable. A caller who doesn't own a session should
be unable to distinguish it from one that was never created.

Login returns the same 401 for "no such account" and "wrong password" —
distinguishing them turns the endpoint into an account-enumeration oracle.

`GAZELENS_SECRET_KEY` **must be set before the pilot study.** Unset, the app
generates a random key per process and warns loudly: tokens then break on
every restart, which is annoying in dev and safe everywhere. A hardcoded
default would have shipped into the deployment and let anyone mint a token
for any participant.

---

## 5. What is stubbed, and how to tell

**`backend/render` is missing**, so a `mode="url"` session cannot get real
element boxes. It is accepted anyway — the endpoint shape is final and the
pipeline runs end to end — but:

- boxes come from `layouts.PLACEHOLDER_URL_LAYOUT`, a generic page skeleton
- the session records `layout_is_placeholder=True`
- the report carries an explicit warning that per-element metrics **do not
  describe real UI elements**

Grep for `layout_is_placeholder` and `TODO(render)` when `render/` lands.
`pipeline.capture_page()` is the single call site to replace.

**`test_uis/` is a separate task**, so test-page layouts live in
`layouts.TEST_UI_LAYOUTS` — geometry from `reports/heatmap_stub.DEMO_LAYOUTS`,
labels from `agents/mock_sessions.py`, so a real session produces metrics
directly comparable to the mock data the agents were built against. Move them
next to each page's HTML when those pages exist; `layout_for()` is the only
function that changes.

---

## 6. Schema management

`python -m api.init_db` — idempotent `create_all`. No Alembic.

At this stage the schema changes by editing `models.py` and recreating a
throwaway pilot database, and a migration tool would be ceremony around a file
that gets deleted. **Add Alembic the moment the study has collected participant
data worth migrating rather than regenerating** — that is the trigger, and it
will arrive during the pilot, not after it.

SQLite pragmas set on every connection: `foreign_keys=ON` (off by default, so
without it the `ON DELETE CASCADE` from sessions to reports silently does
nothing and deleting a session orphans its report) and `journal_mode=WAL` (so
a dashboard polling for status doesn't block on the pipeline writing a result).
