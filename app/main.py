"""Qiskit Fall Fest 2026 — internal registrations dashboard.

A small, password-gated FastAPI app that reads the `registrations` table from
Supabase using the service-role key (server-side only) and renders a dashboard
with summary stats, charts, and a searchable table. Also offers CSV export.

SECURITY:
- The Supabase service-role key bypasses RLS and MUST stay server-side. It is
  read from the SUPABASE_SERVICE_ROLE_KEY env var and never sent to the client.
- Access is gated by a single shared password (DASHBOARD_PASSWORD) stored in a
  signed session cookie. This is an internal tool for a small trusted team.
- Registrant data is PII (names, emails, phones). Do not log row contents.
"""

from __future__ import annotations

import csv
import io
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from supabase import Client, create_client

# --- Configuration (all from environment) ---------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-prod")

SESSION_COOKIE = "qff_dash_session"
TABLE = "registrations"

_serializer = URLSafeSerializer(SECRET_KEY, salt="qff-dashboard")

BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

app = FastAPI(title="QFF 2026 Dashboard", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


def get_supabase() -> Client:
    """Create a Supabase client with the service-role key (server-side only)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase env vars are not configured.")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def is_authed(request: Request) -> bool:
    """Return True if the request carries a valid signed session cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    try:
        data = _serializer.loads(token)
    except BadSignature:
        return False
    return data.get("ok") is True


def fetch_registrations() -> list[dict[str, Any]]:
    """Fetch all registrations ordered by creation time (oldest first)."""
    supabase = get_supabase()
    # Service-role read bypasses RLS. Only reachable behind the auth gate.
    resp = supabase.table(TABLE).select("*").order("created_at", desc=False).execute()
    return resp.data or []


def _count(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    """Count non-empty values of a field into an ordered dict."""
    counter: Counter[str] = Counter()
    for row in rows:
        val = row.get(key)
        if val:
            counter[str(val)] += 1
    return dict(counter.most_common())


def build_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary statistics for the dashboard cards and charts."""
    total = len(rows)

    # Attendance format split.
    fmt = _count(rows, "attendance_format")
    in_person = fmt.get("in-person", 0)
    virtual = fmt.get("virtual", 0)

    # Days attending (array column) — count each day across all registrants.
    day_labels = {"day1": "Day 1 · Nov 12", "day2": "Day 2 · Nov 13", "day3": "Day 3 · Nov 14"}
    day_counter: Counter[str] = Counter()
    for row in rows:
        days = row.get("days_attending") or []
        if isinstance(days, list):
            for d in days:
                if d in day_labels:
                    day_counter[d] += 1
    days_attending = {day_labels[k]: day_counter.get(k, 0) for k in ("day1", "day2", "day3")}

    # Hackathon interest.
    hackathon = _count(rows, "hackathon_interest")

    # Team-matching requests (boolean column).
    team_matching = sum(1 for r in rows if r.get("team_matching") is True)

    # Discord usernames provided.
    discord_provided = sum(1 for r in rows if (r.get("discord_username") or "").strip())

    # Experience level distribution (0..10).
    exp_buckets = {str(i): 0 for i in range(11)}
    exp_values: list[int] = []
    for row in rows:
        lvl = row.get("experience_level")
        if isinstance(lvl, int) and 0 <= lvl <= 10:
            exp_buckets[str(lvl)] += 1
            exp_values.append(lvl)
    avg_exp = round(sum(exp_values) / len(exp_values), 1) if exp_values else 0

    # Institutions represented.
    institutions = _count(rows, "institution")

    # How did you hear about us.
    how_heard = _count(rows, "how_heard")

    # Accessibility / dietary needs flagged.
    accessibility = sum(1 for r in rows if (r.get("accessibility_needs") or "").strip())
    dietary = sum(1 for r in rows if (r.get("dietary_restrictions") or "").strip())

    # Registrations over time (by date) for the trend line.
    by_date: Counter[str] = Counter()
    for row in rows:
        created = row.get("created_at")
        if created:
            # created_at is ISO; take the date part.
            by_date[str(created)[:10]] += 1
    timeline = dict(sorted(by_date.items()))

    return {
        "total": total,
        "in_person": in_person,
        "virtual": virtual,
        "days_attending": days_attending,
        "hackathon": hackathon,
        "hackathon_yes": hackathon.get("yes", 0),
        "team_matching": team_matching,
        "discord_provided": discord_provided,
        "exp_buckets": exp_buckets,
        "avg_exp": avg_exp,
        "institutions": institutions,
        "institutions_count": len(institutions),
        "how_heard": how_heard,
        "accessibility": accessibility,
        "dietary": dietary,
        "timeline": timeline,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if not is_authed(request):
        return RedirectResponse("/login", status_code=302)
    try:
        rows = fetch_registrations()
    except RuntimeError:
        return templates.TemplateResponse(
            "error.html", {"request": request, "message": "Server is not configured (missing Supabase env vars)."}
        )
    except Exception:
        # Don't leak internals; registrant data must never appear in errors.
        return templates.TemplateResponse(
            "error.html", {"request": request, "message": "Could not load registrations from the database. Check the Supabase credentials and try again."}
        )
    stats = build_stats(rows)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "rows": rows, "stats": stats, "generated": generated},
    )


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str = ""):
    if is_authed(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
def login_submit(request: Request, password: str = Form(...)):
    if not DASHBOARD_PASSWORD:
        return templates.TemplateResponse(
            "error.html", {"request": request, "message": "Dashboard password is not configured."}
        )
    if password != DASHBOARD_PASSWORD:
        return RedirectResponse("/login?error=1", status_code=302)
    token = _serializer.dumps({"ok": True})
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 12,  # 12h session
    )
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get("/export.csv")
def export_csv(request: Request):
    if not is_authed(request):
        return RedirectResponse("/login", status_code=302)
    rows = fetch_registrations()
    if not rows:
        return Response("No registrations yet.", media_type="text/plain")

    headers = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        # Flatten list columns (e.g. days_attending) to a readable string.
        flat = {k: (", ".join(v) if isinstance(v, list) else v) for k, v in row.items()}
        writer.writerow(flat)
    buf.seek(0)
    filename = f"qff-registrations-{datetime.now().strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
