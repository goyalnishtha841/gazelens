# Deploying GazeLens (free, no card)

Frontend on **Vercel**, API on a **Hugging Face Docker Space**. Both are free and
need no payment details, and neither needs Docker on your machine.

```
browser ──HTTPS──► Vercel  (frontend-new, static)
   │
   └─────HTTPS──► Hugging Face Space  (backend/Dockerfile, built by Hugging Face)
                     ▲
                     └── pushed automatically by .github/workflows/deploy-hf.yml
```

Both halves are HTTPS, which browsers require for webcam access. The frontend
calls the API directly: its URL is a Vercel setting (`VITE_API_BASE_URL`) and the
API allows the frontend's origin (`GAZELENS_CORS_ORIGINS`).

**Why a Space for the API:** the free CPU tier gives 2 vCPU and 16 GB RAM, which is
enough for MediaPipe plus headless Chromium. Vercel functions are too small for
them (250 MB limit), and Render's free tier has 512 MB of RAM and no disk.

## The catch: free storage is temporary

A free Space has no persistent disk. Accounts, calibrations, sessions and reports
are kept until the Space restarts, which happens:
- on every deploy, meaning every push to `main` that touches the backend;
- after about 48 hours with no visitors, when the Space sleeps.

For a demo, run the whole flow in one sitting: sign up, calibrate, test, then
download the PDF. After a restart, sign up again. Paid persistent storage
mounts at `/data`, where the app already keeps everything, so upgrading needs no
code change.

## 1. API on Hugging Face (one-time setup, ~10 min)

1. Sign up at **huggingface.co**. It's free and no card is needed.
2. Click **New → Space**:
   - Space name: `gazelens-api`
   - SDK: **Docker** → *Blank*
   - Hardware: **CPU basic · free**
   - Visibility: **Public**. A private Space needs a login to reach, so the
     website couldn't call it.
3. In the Space, open **Settings → Variables and secrets** and add:
   - **Secret** `GAZELENS_SECRET_KEY`: the output of
     `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
     The API refuses to start without it.
   - **Secret** `GROQ_API_KEY` (optional): turns on LLM-written report text.
   - **Variable** `GAZELENS_CORS_ORIGINS`: fill this in after step 2 below.
4. Create a token: your avatar → **Settings → Access Tokens → Create new token**,
   type **Write**. Copy it.
5. In GitHub, open the repo's **Settings → Secrets and variables → Actions**:
   - **Secrets** tab → `HF_TOKEN` = the token from step 4.
   - **Variables** tab → `HF_SPACE` = `<your-hf-username>/gazelens-api`.
6. Open GitHub's **Actions** tab → *Deploy API to Hugging Face* → **Run workflow**.
   It pushes the backend to the Space, and Hugging Face builds it (~10 min the
   first time; watch the Space's **Logs** tab).
7. Open `https://<your-hf-username>-gazelens-api.hf.space/health` and check that
   `"cv_available": true`.

After this, every push to `main` that changes the backend redeploys it
automatically.

## 2. Frontend on Vercel

1. Vercel → **Add New → Project**, then import the repo.
2. **Root Directory: `frontend-new`**. Vercel detects Vite.
3. **Environment Variables:** `VITE_API_BASE_URL` =
   `https://<your-hf-username>-gazelens-api.hf.space` (no trailing slash).
4. **Deploy.** Note the URL, for example `https://gazelens.vercel.app`.
5. Back in the Space's **Settings → Variables and secrets**:
   - `GAZELENS_CORS_ORIGINS` = that URL (comma-separate several).
   - Optional, so Vercel preview deployments work too: `GAZELENS_CORS_ORIGIN_REGEX` =
     `^https://gazelens(-[a-z0-9-]+)?\.vercel\.app$`.

   Saving the settings restarts the Space.

## 3. Check it

Open the Vercel URL, then:
1. Sign up.
2. Calibrate and pass the accuracy check.
3. Run a session on a test page and on a URL.
4. Open the report and download the PDF.

If something fails, the Space's **Logs** tab shows the API's errors.

## Configuration reference

All configuration is environment variables. See [`.env.example`](.env.example).

| Variable | Where | Default | Purpose |
|---|---|---|---|
| `GAZELENS_SECRET_KEY` | Space secret | none | JWT signing key. **Required in production.** (`FIXATION_SECRET_KEY` still works.) |
| `GAZELENS_CORS_ORIGINS` | Space variable | `http://localhost:5180` | Comma-separated frontend origins |
| `GAZELENS_CORS_ORIGIN_REGEX` | Space variable | none | Extra origins by regex, e.g. Vercel previews |
| `GAZELENS_LOGIN_MAX_FAILURES` | Space variable | `10` | Failed logins per client IP per window before `429` |
| `GAZELENS_LOGIN_WINDOW_SECONDS` | Space variable | `900` | That window |
| `GROQ_API_KEY` / `ANTHROPIC_API_KEY` | Space secret | none | Optional LLM writing for the report agents |
| `GAZELENS_ENV` | set in the image | `production` | Refuses to start without a secret key |
| `FIXATION_DATABASE_URL`, `FIXATION_DATA_DIR`, `GAZELENS_CALIBRATION_DIR`, `GAZELENS_GAZE_MODEL_DIR` | set in the image | everything under `/data` | Storage locations |
| `VITE_API_BASE_URL` | Vercel, build time | empty, same origin | The API's URL |
| `VITE_PROXY_TARGET` | local `npm run dev` only | `http://localhost:8000` | Where the dev server proxies `/api` |

## Notes

- **One process.** The API runs one uvicorn worker on purpose. SQLite, the
  in-memory login rate limiter and the gaze-model cache all assume a single process.
- **Participant data.** Calibrations and gaze streams are recordings of real
  people's eyes. Use the hosted demo with test participants, or check that your
  consent forms cover hosted storage.
- **Latency.** Every webcam frame is a round trip to the Space. If the live cursor
  feels slow, run the API locally for real study sessions.
- **Paid alternative with a persistent disk:** [`render.yaml`](render.yaml) deploys
  the same image to Render with a `/data` disk. That needs a paid Render instance.

## CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push to `main`
and on every PR:
- all backend test suites, each run from inside its own folder;
- `ruff`;
- the frontend build;
- a build of the API image.

[`deploy-hf.yml`](.github/workflows/deploy-hf.yml) does the deploy, and skips itself
until `HF_SPACE` is set.
