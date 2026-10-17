"""
test_admin.py

Run with: python3 test_admin.py   (from inside backend/api)

The admin view's access rules, against a throwaway database:

  * off (404) unless GAZELENS_ADMIN_PASSWORD is set
  * wrong passwords are refused and throttled
  * only an admin token opens the admin routes; a user token does not
  * an admin token opens no user route
  * the data is right, and never includes password hashes
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

_TMP = Path(tempfile.mkdtemp(prefix="gazelens_admin_test_"))
os.environ["FIXATION_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["FIXATION_DATA_DIR"] = str(_TMP / "data")
os.environ["GAZELENS_LLM"] = "off"
os.environ.pop("GAZELENS_ADMIN_PASSWORD", None)
os.environ.setdefault("FIXATION_SECRET_KEY", "test-only-key-not-for-deployment-0123456789abcdef")

from fastapi.testclient import TestClient                          # noqa: E402

from api.admin_routes import admin_limiter                         # noqa: E402
from api.db import init_db                                         # noqa: E402
from api.main import app                                           # noqa: E402

passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        print(f"  PASS  {label}")
        passed += 1
    else:
        print(f"  FAIL  {label}")
        failed += 1


try:
    init_db()
    client = TestClient(app)

    def signup(email):
        r = client.post("/api/auth/signup", json={"email": email, "password": "correct-horse-1"})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    alice = signup("alice@example.com")
    bob = signup("bob@example.com")
    pages = client.get("/api/sessions/meta/test-uis", headers=alice).json()["ui_pages"]
    for _ in range(2):
        client.post("/api/sessions", headers=alice, json={"mode": "test_ui", "ui_page": pages[0]})

    # ------------------------------------------------------------------
    print("disabled -- no admin password configured")
    check("login -> 404", client.post("/api/admin/login", json={"password": "x"}).status_code == 404)
    check("overview -> 404", client.get("/api/admin/overview").status_code == 404)

    os.environ["GAZELENS_ADMIN_PASSWORD"] = "s3cret-admin-pass"

    # ------------------------------------------------------------------
    print("\nlogin")
    r = client.post("/api/admin/login", json={"password": "wrong"})
    check("wrong password -> 401", r.status_code == 401)
    r = client.post("/api/admin/login", json={"password": "s3cret-admin-pass"})
    check("right password -> 200", r.status_code == 200)
    admin = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # ------------------------------------------------------------------
    print("\nwho can see the admin data")
    check("no token -> 401", client.get("/api/admin/overview").status_code == 401)
    check("forged token -> 401",
          client.get("/api/admin/overview", headers={"Authorization": "Bearer not.a.jwt"}).status_code == 401)
    check("a user's token -> 401", client.get("/api/admin/overview", headers=alice).status_code == 401)
    check("admin token -> 200", client.get("/api/admin/overview", headers=admin).status_code == 200)

    print("\nan admin token is not a user login")
    check("/api/auth/me with admin token -> 401", client.get("/api/auth/me", headers=admin).status_code == 401)
    check("/api/sessions with admin token -> 401", client.get("/api/sessions", headers=admin).status_code == 401)

    # ------------------------------------------------------------------
    print("\nthe data")
    data = client.get("/api/admin/overview", headers=admin).json()
    check("two users", data["totals"]["users"] == 2)
    check("two tests", data["totals"]["tests"] == 2)
    by_email = {u["email"]: u for u in data["users"]}
    check("alice has 2 tests", by_email["alice@example.com"]["tests"] == 2)
    check("bob has 0 tests", by_email["bob@example.com"]["tests"] == 0)
    check("most recently active first", data["users"][0]["email"] == "alice@example.com")
    check("14 days of activity", len(data["daily"]) == 14 and sum(d["tests"] for d in data["daily"]) == 2)
    kinds = {e["kind"] for e in data["events"]}
    check("events include sign-ups and tests", {"signup", "test_started"} <= kinds)
    check("no password hashes anywhere", "password" not in str(data).lower())

    alice_id = by_email["alice@example.com"]["id"]
    detail = client.get(f"/api/admin/users/{alice_id}", headers=admin)
    check("user detail -> 200 with 2 tests", detail.status_code == 200 and len(detail.json()["tests"]) == 2)
    check("unknown user -> 404", client.get("/api/admin/users/usr_nope", headers=admin).status_code == 404)
    check("user detail needs admin", client.get(f"/api/admin/users/{alice_id}", headers=bob).status_code == 401)

    # ------------------------------------------------------------------
    print("\nthrottling")
    admin_limiter.reset("testclient")
    codes = [client.post("/api/admin/login", json={"password": "guess"}).status_code for _ in range(6)]
    check("first 5 wrong guesses -> 401", codes[:5] == [401] * 5)
    check("6th -> 429", codes[5] == 429)
    check("even the right password waits while throttled",
          client.post("/api/admin/login", json={"password": "s3cret-admin-pass"}).status_code == 429)
    admin_limiter.reset("testclient")
    check("after the window, the right password works",
          client.post("/api/admin/login", json={"password": "s3cret-admin-pass"}).status_code == 200)

    os.environ.pop("GAZELENS_ADMIN_PASSWORD", None)
    check("turning the password off closes it again -> 404",
          client.get("/api/admin/overview", headers=admin).status_code == 404)
finally:
    shutil.rmtree(_TMP, ignore_errors=True)

print(f"\n{'=' * 40}\n{passed} passed, {failed} failed\n{'=' * 40}")
if failed:
    raise SystemExit(1)
