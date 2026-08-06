"""
backend/api -- the GazeLens HTTP API and the integration layer.

    cd backend
    uvicorn api.main:app --reload --port 8000

This is the only module that knows about all the others. Everything else does
one job and knows nothing downstream of itself; api/pipeline.py is what calls
them in order and turns a pile of independent modules into a working pipeline.

Deliberately does NOT re-export `app` at package level: importing
backend.api would then build the FastAPI app (and touch the database) as a
side effect of importing anything here -- including init_db.py, which needs to
configure the database before the app exists.
"""

__all__: list[str] = []
