# Deploying GazeLens

Frontend on **Vercel**, API on **Render**. Neither needs Docker on your machine.

```
browser ──HTTPS──► Vercel (frontend-new, static)
                      │  /api, /health, /test-uis  (rewrites in frontend-new/vercel.json)
                      ▼
                   Render (backend/Dockerfile, built by Render)  ──► /data persistent disk
```

The browser only ever talks to the Vercel domain, so it is one HTTPS origin. That
matters because browsers only allow webcam access on HTTPS (or `localhost`), and it
means no CORS setup.

## Why the API isn't on Vercel too

Vercel's Python functions can't run this backend:
- MediaPipe + OpenCV + Chromium are well over the 250 MB function size limit.
- There's no persistent disk for the SQLite database, calibrations, trained gaze
  models and reports.
- `/finalize` keeps working after it responds, and the live session keeps a trained
  model in memory. Both need a long-running process.

Render builds `backend/Dockerfile` on its own servers. The Dockerfile is only how
Render installs the Linux libraries MediaPipe and Chromium need. You never run
Docker yourself.

## 1. API on Render

1. Push this branch to GitHub.
2. Render dashboard → **New → Blueprint**, then pick the repo. It reads
   [`render.yaml`](render.yaml), which sets up:
   - the `gazelens-api` web service, built from `backend/Dockerfile`;
   - a 2 GB persistent disk at `/data`, holding all participant data;
   - a generated `GAZELENS_SECRET_KEY`;
   - health checks on `/health`.
3. Optional: set `GROQ_API_KEY` or `ANTHROPIC_API_KEY` for LLM-written reports.
4. Wait for the deploy, then open `https://<service>.onrender.com/health`.
   `cv_available` should be `true`.

**Plan:** `standard` (2 GB RAM). MediaPipe and Chromium together get OOM-killed on
512 MB instances, and a persistent disk needs a paid instance anyway.

If Render gives the service a different URL than `gazelens-api.onrender.com`
(names are global), update the three rewrite destinations in
`frontend-new/vercel.json`.

## 2. Frontend on Vercel

1. Vercel → **Add New → Project**, then import the repo.
2. **Root Directory: `frontend-new`**. Vercel detects Vite. `vercel.json` already
   sets the build command, the output directory and the rewrites.
3. Deploy. No environment variables are needed.

### Alternative: call the API directly instead of through rewrites

Every webcam frame passes through Vercel's proxy on its way to Render. If that adds
too much latency, or a long request (URL capture of a heavy page) hits the proxy's
timeout, skip the rewrites:

1. In Vercel, set `VITE_API_BASE_URL=https://<service>.onrender.com`, then redeploy.
2. In Render, set `GAZELENS_CORS_ORIGINS=https://<your-app>.vercel.app`, plus any
   preview domains you use.
3. Delete the `/api`, `/health` and `/test-uis` rewrites from `vercel.json` (keep the
   last one, the single-page-app fallback).

## Configuration reference

All configuration is environment variables. See [`.env.example`](.env.example).

| Variable | Service | Default | Purpose |
|---|---|---|---|
| `GAZELENS_SECRET_KEY` | API | generated file (dev only) | JWT signing key. **Required in production.** (`FIXATION_SECRET_KEY` still works.) |
| `GAZELENS_ENV` | API | `production` in the image | Refuses to start without a secret key |
| `GAZELENS_CORS_ORIGINS` | API | `http://localhost:5180` | Comma-separated origins allowed cross-origin |
| `GAZELENS_LOGIN_MAX_FAILURES` | API | `10` | Failed logins per client IP per window before `429` |
| `GAZELENS_LOGIN_WINDOW_SECONDS` | API | `900` | That window |
| `FIXATION_DATABASE_URL` | API | `sqlite:////data/gazelens.db` in the image | SQLAlchemy URL |
| `FIXATION_DATA_DIR` | API | `/data/sessions` in the image | Gaze streams, captures, reports |
| `GAZELENS_CALIBRATION_DIR` | API | `/data/calibration` in the image | Calibration recordings |
| `GAZELENS_GAZE_MODEL_DIR` | API | `/data/gaze_models` in the image | Trained per-session gaze models |
| `VITE_API_BASE_URL` | Vercel (build time) | empty, same origin | API URL for direct mode |
| `VITE_PROXY_TARGET` | local `npm run dev` only | `http://localhost:8000` | Where the dev server proxies `/api` |

## Operational notes

- **One process.** The API runs a single uvicorn worker on purpose. SQLite, the
  in-memory login rate limiter and the gaze-model cache all assume one process.
  Scale the instance up, not out, or move those to Postgres and Redis first.
- **Participant data.** `/data` holds recordings of real people's eye positions.
  Keep the service private to your study, and check that your consent forms cover
  hosted storage.
- **Backups.** Render snapshots disks daily. For a manual copy, from the Render
  shell: `python -c "import sqlite3; sqlite3.connect('/data/gazelens.db').backup(sqlite3.connect('/data/backup.db'))"`.
- **Region.** Every webcam frame is a round trip, so set `region` in `render.yaml`
  close to your participants.

## CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push to `main`
and on every PR:
- all seven backend test suites, each run from inside its own folder;
- `ruff`;
- the frontend build;
- a build of the API image, so a broken Dockerfile fails in CI rather than on Render.
