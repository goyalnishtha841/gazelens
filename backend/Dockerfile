# GazeLens API: FastAPI + MediaPipe + headless Chromium (page capture, PDFs).
#
# Build from the REPO ROOT -- the API serves test_uis/ and loads models/:
# Hugging Face Spaces builds this (pushed by .github/workflows/deploy-hf.yml),
# or Render from render.yaml; nobody needs Docker locally. To build it by
# hand anyway:
#   docker build --platform linux/amd64 -f backend/Dockerfile -t gazelens-api .
#
# linux/amd64 only: mediapipe 0.10.35 publishes no linux/arm64 wheel. On Apple
# Silicon it runs under emulation; Render/Railway/CI are amd64 anyway.

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# libgl1/libglib2.0-0/libgles2/libegl1: OpenCV and MediaPipe's native libs
# (the face landmarker dlopens libGLESv2 even on CPU). Chromium's own system
# deps come from `playwright install --with-deps` below.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgles2 libegl1 curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements-server.txt ./
RUN pip install -r requirements-server.txt \
 && pip install --no-deps rapidocr-onnxruntime==1.4.4 \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

# MediaPipe face landmarker (~3.7MB). Fetched at build time so a container
# never starts without it.
COPY scripts/fetch_face_landmarker.py scripts/
RUN mkdir -p models && python scripts/fetch_face_landmarker.py

COPY models/__init__.py models/
COPY test_uis/ test_uis/
COPY backend/ backend/

# Everything that holds participant data lives under /data so one volume
# keeps it across container restarts.
ENV GAZELENS_ENV=production \
    FIXATION_DATABASE_URL=sqlite:////data/gazelens.db \
    FIXATION_DATA_DIR=/data/sessions \
    GAZELENS_CALIBRATION_DIR=/data/calibration \
    GAZELENS_GAZE_MODEL_DIR=/data/gaze_models \
    PORT=8000

# HOME for the app user either way: Hugging Face starts the container as
# uid 1000 directly, skipping the entrypoint's root branch.
ENV HOME=/home/gazelens

# When started as root, runs as root only long enough for docker-entrypoint.sh to make /data
# writable (a host's persistent disk is often mounted root-owned), then
# drops to this user.
RUN useradd --create-home --uid 1000 gazelens \
 && mkdir -p /data \
 && chown -R gazelens /data /app
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
VOLUME ["/data"]

WORKDIR /app/backend
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# One worker: SQLite + the in-memory login rate limiter + per-process gaze
# model cache all assume a single process. --proxy-headers so the rate limiter
# sees the real client IP behind the host's proxy.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
