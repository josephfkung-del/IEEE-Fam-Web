from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
SQLITE_PATH = BASE_DIR / "familieee_local.db"

app = FastAPI(title="FamilIEEEs Event Review")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-only-change-this-secret")
COOKIE_NAME = "familieee_admin"
SESSION_TTL = 60 * 60 * 12
MAX_PHOTO_CHARS = 1_800_000


def _using_postgres() -> bool:
    return DATABASE_URL.startswith("postgres")


def _pg_connect():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("DATABASE_URL is set but psycopg is not installed") from exc
    return psycopg.connect(DATABASE_URL)


@contextmanager
def db_cursor():
    if _using_postgres():
        conn = _pg_connect()
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db() -> None:
    if _using_postgres():
        statement = """
        CREATE TABLE IF NOT EXISTS familieee_submissions (
          id text PRIMARY KEY,
          family_name text NOT NULL,
          submitter_name text NOT NULL,
          submitter_email text,
          event_title text NOT NULL,
          event_date date NOT NULL,
          event_type text NOT NULL DEFAULT 'social',
          description text NOT NULL,
          member_count integer NOT NULL DEFAULT 0,
          fam_head_present boolean NOT NULL DEFAULT false,
          advertised_beforehand boolean NOT NULL DEFAULT false,
          photo_data text NOT NULL,
          photo_filename text,
          photo_mime text,
          status text NOT NULL DEFAULT 'pending',
          points_awarded integer NOT NULL DEFAULT 0,
          reviewer_note text,
          submitted_at timestamptz NOT NULL DEFAULT now(),
          reviewed_at timestamptz
        )
        """
    else:
        statement = """
        CREATE TABLE IF NOT EXISTS familieee_submissions (
          id TEXT PRIMARY KEY,
          family_name TEXT NOT NULL,
          submitter_name TEXT NOT NULL,
          submitter_email TEXT,
          event_title TEXT NOT NULL,
          event_date TEXT NOT NULL,
          event_type TEXT NOT NULL DEFAULT 'social',
          description TEXT NOT NULL,
          member_count INTEGER NOT NULL DEFAULT 0,
          fam_head_present INTEGER NOT NULL DEFAULT 0,
          advertised_beforehand INTEGER NOT NULL DEFAULT 0,
          photo_data TEXT NOT NULL,
          photo_filename TEXT,
          photo_mime TEXT,
          status TEXT NOT NULL DEFAULT 'pending',
          points_awarded INTEGER NOT NULL DEFAULT 0,
          reviewer_note TEXT,
          submitted_at TEXT NOT NULL,
          reviewed_at TEXT
        )
        """
    with db_cursor() as cur:
        cur.execute(statement)


init_db()


def _sign(value: str) -> str:
    digest = hmac.new(SESSION_SECRET.encode(), value.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def create_admin_token() -> str:
    issued = str(int(time.time()))
    nonce = secrets.token_urlsafe(12)
    payload = f"{issued}.{nonce}"
    return f"{payload}.{_sign(payload)}"


def valid_admin_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        issued, nonce, signature = token.split(".", 2)
        payload = f"{issued}.{nonce}"
        if not hmac.compare_digest(signature, _sign(payload)):
            return False
        return int(time.time()) - int(issued) <= SESSION_TTL
    except Exception:
        return False


def require_admin(request: Request) -> None:
    if not valid_admin_token(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="Admin login required")


def row_to_dict(row: Any, columns: list[str] | None = None) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return dict(row)
    if columns is None:
        raise ValueError("columns required for Postgres tuple row")
    return dict(zip(columns, row))


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if _using_postgres():
        query = query.replace("?", "%s")
    with db_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        cols = [d.name if hasattr(d, "name") else d[0] for d in cur.description] if cur.description else []
    return [row_to_dict(r, cols) for r in rows]


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    rows = fetch_all(query, params)
    return rows[0] if rows else None


def execute(query: str, params: tuple[Any, ...] = ()) -> None:
    if _using_postgres():
        query = query.replace("?", "%s")
    with db_cursor() as cur:
        cur.execute(query, params)


def serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: serialize_value(v) for k, v in row.items()}


def quarter_name(event_date: str) -> str:
    try:
        month = datetime.fromisoformat(event_date).month
    except Exception:
        return "Unknown"
    if month in (9, 10, 11, 12):
        return "Fall"
    if month in (1, 2, 3):
        return "Winter"
    return "Spring"


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    if valid_admin_token(request.cookies.get(COOKIE_NAME)):
        return RedirectResponse("/admin", status_code=302)
    return templates.TemplateResponse("admin_login.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    if not valid_admin_token(request.cookies.get(COOKIE_NAME)):
        return RedirectResponse("/admin/login", status_code=302)
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/health")
def health():
    return {"ok": True, "database": "postgres" if _using_postgres() else "sqlite"}


@app.post("/api/admin/login")
async def admin_login(request: Request):
    body = await request.json()
    password = str(body.get("password", ""))
    if not hmac.compare_digest(password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Incorrect password")
    response = JSONResponse({"ok": True})
    response.set_cookie(
        COOKIE_NAME,
        create_admin_token(),
        max_age=SESSION_TTL,
        httponly=True,
        secure=os.getenv("VERCEL") == "1",
        samesite="lax",
        path="/",
    )
    return response


@app.post("/api/admin/logout")
def admin_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@app.post("/api/submissions")
async def create_submission(request: Request):
    body = await request.json()

    required = ["family_name", "submitter_name", "event_title", "event_date", "description", "photo_data"]
    missing = [key for key in required if not str(body.get(key, "")).strip()]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    photo_data = str(body.get("photo_data", ""))
    if not photo_data.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Photo must be an image")
    if len(photo_data) > MAX_PHOTO_CHARS:
        raise HTTPException(status_code=413, detail="Photo is too large after compression")

    try:
        event_date = datetime.fromisoformat(str(body["event_date"])).date().isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event date")

    try:
        member_count = max(0, min(int(body.get("member_count", 0)), 100))
    except (TypeError, ValueError):
        member_count = 0

    submission_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    params = (
        submission_id,
        str(body["family_name"]).strip()[:120],
        str(body["submitter_name"]).strip()[:120],
        str(body.get("submitter_email", "")).strip()[:200] or None,
        str(body["event_title"]).strip()[:160],
        event_date,
        str(body.get("event_type", "social")).strip()[:40] or "social",
        str(body["description"]).strip()[:1800],
        member_count,
        bool(body.get("fam_head_present", False)),
        bool(body.get("advertised_beforehand", False)),
        photo_data,
        str(body.get("photo_filename", "photo.jpg"))[:255],
        str(body.get("photo_mime", "image/jpeg"))[:80],
        now,
    )

    execute(
        """
        INSERT INTO familieee_submissions (
            id, family_name, submitter_name, submitter_email, event_title, event_date,
            event_type, description, member_count, fam_head_present, advertised_beforehand,
            photo_data, photo_filename, photo_mime, submitted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        params,
    )
    return {"ok": True, "id": submission_id, "quarter": quarter_name(event_date)}


@app.get("/api/admin/submissions")
def list_submissions(request: Request, status: str = "all"):
    require_admin(request)
    if status in {"pending", "approved", "denied"}:
        rows = fetch_all(
            "SELECT * FROM familieee_submissions WHERE status = ? ORDER BY submitted_at DESC",
            (status,),
        )
    else:
        rows = fetch_all("SELECT * FROM familieee_submissions ORDER BY submitted_at DESC")
    return {"submissions": [serialize_row(r) for r in rows]}


@app.patch("/api/admin/submissions/{submission_id}")
async def review_submission(submission_id: str, request: Request):
    require_admin(request)
    body = await request.json()
    status = str(body.get("status", "")).lower()
    if status not in {"approved", "denied", "pending"}:
        raise HTTPException(status_code=400, detail="Invalid status")

    try:
        points = max(0, min(int(body.get("points_awarded", 0)), 999))
    except (TypeError, ValueError):
        points = 0
    if status != "approved":
        points = 0

    note = str(body.get("reviewer_note", "")).strip()[:1000] or None
    reviewed_at = datetime.now(timezone.utc).isoformat() if status != "pending" else None

    execute(
        """
        UPDATE familieee_submissions
        SET status = ?, points_awarded = ?, reviewer_note = ?, reviewed_at = ?
        WHERE id = ?
        """,
        (status, points, note, reviewed_at, submission_id),
    )
    updated = fetch_one("SELECT * FROM familieee_submissions WHERE id = ?", (submission_id,))
    if not updated:
        raise HTTPException(status_code=404, detail="Submission not found")
    return {"ok": True, "submission": serialize_row(updated)}


@app.get("/api/leaderboard")
def leaderboard():
    rows = fetch_all(
        """
        SELECT family_name,
               COALESCE(SUM(points_awarded), 0) AS points,
               COUNT(*) AS approved_events
        FROM familieee_submissions
        WHERE status = 'approved'
        GROUP BY family_name
        ORDER BY points DESC, approved_events DESC, family_name ASC
        """
    )
    return {"leaderboard": [serialize_row(r) for r in rows]}
