"""Live demo: a small business's free-trial signup, guarded in real time.

Three parts share one SQLite file:
  * POST /api/trial/signup  the trial form on the business site. Every signup is
    judged by signup_guard the moment it arrives, and the whole recent stream is
    re-judged, so a farm can be caught (and earlier accounts suspended) as it grows.
  * GET  /api/guard/state   everything the live dashboard shows.
  * a background thread that plays ordinary customers signing up, so the
    stream has normal traffic around the attack (marked "simulated" everywhere).

Two weeks of ordinary signups from the demo file are loaded as history, so the
timing tests have a baseline from the first request.

The attack script may send an X-Demo-Truth header saying which campaign a
request belongs to. It is stored for the scoreboard only and is never passed
to the detector.
"""
from __future__ import annotations

import importlib.util
import json
import os
import random
import secrets
import sqlite3
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from signup_guard import Signups, analyse, load_signups, split_email  # noqa: E402
from signup_lists import FREE_PROVIDERS, disposable_domains  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).parent / "static"
DB_PATH = Path(os.environ.get("GUARD_DB", ROOT / "data" / "live" / "guard.sqlite"))
DEMO_KEY = os.environ.get("GUARD_DEMO_KEY", "")
SIM_EVERY = float(os.environ.get("GUARD_SIM_EVERY", "20"))       # seconds between simulated customers, on average
TRUST_PROXY = os.environ.get("SIGNUP_TRUST_PROXY", "0") == "1"
WINDOW_DAYS = 7
MAX_LIVE_ROWS = 20000
FIELDS = ["id", "created_at", "email", "username", "ip", "asn", "asn_org", "user_agent", "device_id",
          "fill_ms", "honeypot", "webdriver"]

router = APIRouter()
_lock = threading.RLock()
_state: dict = {"version": 0, "report": None, "frame": None, "started": time.time()}

spec = importlib.util.spec_from_file_location("make_signup_data", ROOT / "data" / "make_signup_data.py")
_gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_gen)


# ---------------------------------------------------------------- storage

def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS signups (
        id TEXT PRIMARY KEY, created_at REAL, email TEXT, username TEXT, ip TEXT, asn TEXT, asn_org TEXT,
        user_agent TEXT, device_id TEXT, fill_ms TEXT, honeypot TEXT, webdriver TEXT,
        source TEXT, campaign TEXT, action_at_signup TEXT, action_now TEXT, reasons TEXT, risk INTEGER)""")
    return con


_con = _db()


def _history() -> pd.DataFrame:
    """Ordinary signups from the demo file, shifted to end when the server started."""
    demo = ROOT / "data" / "signups" / "demo_signups.csv"
    su = load_signups(demo, label_col="label")
    frame = su.frame[[lab == "organic" for lab in su.labels]].reset_index(drop=True)
    frame["time"] = frame["time"] + (_state["started"] - 120 - float(frame["time"].max()))
    for col in ("fill_ms", "honeypot", "webdriver"):
        frame[col] = ""
    return frame


HISTORY = _history()


def _live_rows(since: float) -> list[sqlite3.Row]:
    return _con.execute("SELECT * FROM signups WHERE created_at >= ? ORDER BY created_at", (since,)).fetchall()


# ---------------------------------------------------------------- judging

def judge(row: dict, source: str, campaign: str = "") -> dict:
    """Store a signup, re-judge the recent stream, return this signup's verdict."""
    with _lock:
        _con.execute("INSERT INTO signups (id, created_at, email, username, ip, asn, asn_org, user_agent, device_id, "
                     "fill_ms, honeypot, webdriver, source, campaign) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     [row[f] for f in FIELDS] + [source, campaign])
        _rejudge()
        out = _con.execute("SELECT action_now, reasons, risk FROM signups WHERE id = ?", (row["id"],)).fetchone()
        _con.execute("UPDATE signups SET action_at_signup = action_now WHERE id = ?", (row["id"],))
        _con.commit()
        return {"id": row["id"], "action": out["action_now"], "reasons": json.loads(out["reasons"] or "[]")}


def _rejudge() -> None:
    since = time.time() - WINDOW_DAYS * 86400
    live = _live_rows(since)
    live_frame = pd.DataFrame([{**{f: (r[f] or "") for f in FIELDS}, "time": r["created_at"]} for r in live],
                              columns=FIELDS + ["time"]).drop(columns=["created_at"])
    frame = pd.concat([HISTORY, live_frame], ignore_index=True).fillna("")
    for col in frame.columns:
        if col != "time":
            frame[col] = frame[col].astype(str)
    frame["time"] = frame["time"].astype(float)
    report = analyse(Signups(frame, {}, len(frame)), sample=0, per_row=True)
    offset = len(HISTORY)
    clusters = {c["id"]: c for c in report["clusters"]}
    updates = []
    for k, r in enumerate(live):
        i = offset + k
        reasons = list(report["reasons"][i])
        c = clusters.get(report["cluster_of"][i])
        if c and report["actions"][i] != "allow" and c["action"] != "allow":
            shared = "; ".join(e["text"] for e in c["evidence"][:2])
            reasons.insert(0, f"Linked to {c['size'] - 1} other signups: {shared}. {c['timing']}")
        updates.append((report["actions"][i], json.dumps(reasons), report["risk"][i], r["id"]))
    _con.executemany("UPDATE signups SET action_now = ?, reasons = ?, risk = ? WHERE id = ?", updates)
    _state.update(report=report, offset=offset, live_ids=[r["id"] for r in live], version=_state["version"] + 1)


# ---------------------------------------------------------------- simulated customers

def _simulated_customers() -> None:
    rng = random.Random()
    while True:
        time.sleep(rng.expovariate(1 / SIM_EVERY))
        try:
            person = _gen.human(rng, None)
            row = {"id": f"s-{secrets.token_hex(5)}", "created_at": time.time(), "email": person["email"],
                   "username": person["username"], "ip": person["ip"], "asn": str(person["asn"]),
                   "asn_org": person["asn_org"], "user_agent": person["user_agent"], "device_id": person["device_id"],
                   "fill_ms": str(int(rng.uniform(6000, 45000))), "honeypot": "", "webdriver": ""}
            judge(row, "simulated")
        except Exception as exc:  # never let the simulator kill the server
            print(f"simulated customer failed: {exc}")


def start_background() -> None:
    if SIM_EVERY > 0:
        threading.Thread(target=_simulated_customers, daemon=True, name="simulated-customers").start()
    with _lock:
        _rejudge()
        _con.commit()


# ---------------------------------------------------------------- API

class TrialSignup(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    business: str = Field(default="", max_length=100)
    device_id: str = Field(default="", max_length=64)
    fill_ms: int | None = Field(default=None, ge=0, le=36_000_000)
    website: str = Field(default="", max_length=200)      # honeypot: hidden from people
    webdriver: bool = False


def _client_ip(request: Request) -> str:
    if TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else ""


_rate: dict[str, list[float]] = {}


def _rate_ok(ip: str, limit: int = 600, per: float = 3600) -> bool:
    now = time.time()
    hits = [t for t in _rate.get(ip, []) if now - t < per]
    hits.append(now)
    _rate[ip] = hits
    return len(hits) <= limit


@router.post("/api/trial/signup")
def trial_signup(item: TrialSignup, request: Request) -> dict:
    if "@" not in item.email or "." not in item.email.rsplit("@", 1)[-1]:
        raise HTTPException(400, "Please enter a valid email address.")
    ip = _client_ip(request)
    if not _rate_ok(ip):
        raise HTTPException(429, "Too many signups from this address. Try again later.")
    truth = request.headers.get("x-demo-truth", "")
    campaign = ""
    if truth and DEMO_KEY and truth.split(":", 1)[0] == DEMO_KEY:
        campaign = truth.split(":", 1)[1][:40] if ":" in truth else "attack"
    row = {"id": f"t-{secrets.token_hex(5)}", "created_at": time.time(), "email": item.email.strip(),
           "username": item.business.strip(), "ip": ip, "asn": "", "asn_org": "",
           "user_agent": request.headers.get("user-agent", "")[:300], "device_id": item.device_id.strip(),
           "fill_ms": "" if item.fill_ms is None else str(item.fill_ms),
           "honeypot": "1" if item.website.strip() else "", "webdriver": "1" if item.webdriver else ""}
    with _lock:
        if _con.execute("SELECT COUNT(*) FROM signups").fetchone()[0] >= MAX_LIVE_ROWS:
            _con.execute("DELETE FROM signups WHERE id IN (SELECT id FROM signups ORDER BY created_at LIMIT 1000)")
    result = judge(row, "attack" if campaign else "visitor", campaign)
    messages = {"allow": "Your 14-day trial is ready. Check your inbox for the login link.",
                "review": "Almost there. We need to confirm this signup before your trial starts.",
                "block": "We couldn't create a trial account with these details."}
    return {"id": result["id"], "action": result["action"], "message": messages[result["action"]],
            "reasons": result["reasons"] if campaign else []}


def _mask(email: str) -> str:
    local, domain = split_email(email)
    if domain in FREE_PROVIDERS or domain in disposable_domains():
        shown = domain
    else:
        shown = domain[:1] + "•••" + ("." + domain.rsplit(".", 1)[-1] if "." in domain else "")
    return f"{local[:1]}•••@{shown}"


@router.get("/api/guard/state")
def guard_state(since_version: int = -1) -> dict:
    with _lock:
        version = _state["version"]
        if since_version == version:
            return {"version": version, "unchanged": True}
        report = _state["report"]
        live_ids = list(_state["live_ids"])
        offset = _state["offset"]
        rows = {r["id"]: r for r in _live_rows(time.time() - WINDOW_DAYS * 86400)}
    now = time.time()
    since = now - 30 * 60
    recent = [r for r in rows.values() if r["created_at"] >= since]

    def counts(pred) -> dict:
        sel = [r for r in rows.values() if pred(r)]
        return {"total": len(sel), "block": sum(r["action_now"] == "block" for r in sel),
                "review": sum(r["action_now"] == "review" for r in sel),
                "allow": sum(r["action_now"] == "allow" for r in sel),
                "blocked_at_signup": sum(r["action_at_signup"] == "block" for r in sel),
                "caught_later": sum(r["action_at_signup"] == "allow" and r["action_now"] != "allow" for r in sel)}

    scoreboard = {"attack": counts(lambda r: r["source"] == "attack"),
                  "visitor": counts(lambda r: r["source"] == "visitor"),
                  "simulated": counts(lambda r: r["source"] == "simulated")}
    campaigns = {}
    for r in rows.values():
        if r["source"] == "attack":
            c = campaigns.setdefault(r["campaign"] or "attack", {"total": 0, "block": 0, "review": 0, "allow": 0})
            c["total"] += 1
            c[r["action_now"]] += 1

    bin_s, n_bins = 30, 40
    start = now - bin_s * n_bins
    timeline = [{"t": start + i * bin_s, "block": 0, "review": 0, "allow": 0} for i in range(n_bins)]
    for r in rows.values():
        if r["created_at"] >= start:
            b = min(int((r["created_at"] - start) // bin_s), n_bins - 1)
            timeline[b][r["action_now"]] += 1

    groups = []
    live_index = {offset + k: rid for k, rid in enumerate(live_ids)}
    for c in report["clusters"]:
        members = [live_index[i] for i in c.get("members", []) if i in live_index]
        if not members:
            continue
        member_rows = [rows[m] for m in members if m in rows]
        groups.append({"action": c["action"], "size": c["size"], "live": len(members),
                       "attack": sum(r["source"] == "attack" for r in member_rows),
                       "evidence": [e["text"] for e in c["evidence"]], "timing": c["timing"], "why": c["why"],
                       "organisation": c["organisation"], "last": max(r["created_at"] for r in member_rows)})
    groups.sort(key=lambda g: -g["last"])

    feed = sorted(rows.values(), key=lambda r: -r["created_at"])[:40]
    return {
        "version": version, "now": now, "uptime": now - _state["started"],
        "history_rows": len(HISTORY), "live_rows": len(rows), "recent_30min": len(recent),
        "scoreboard": scoreboard, "campaigns": campaigns, "timeline": timeline, "groups": groups[:6],
        "feed": [{"id": r["id"], "time": r["created_at"], "email": _mask(r["email"]), "source": r["source"],
                  "campaign": r["campaign"], "action": r["action_now"], "at_signup": r["action_at_signup"],
                  "risk": r["risk"], "reasons": json.loads(r["reasons"] or "[]")[:3]} for r in feed],
    }


def _check_key(request: Request) -> None:
    if not DEMO_KEY or request.headers.get("x-demo-key") != DEMO_KEY:
        raise HTTPException(403, "Demo key required.")


@router.post("/api/guard/reset")
def guard_reset(request: Request) -> dict:
    """Delete all live signups (history stays). Needs the demo key."""
    _check_key(request)
    with _lock:
        _con.execute("DELETE FROM signups")
        _rejudge()
        _con.commit()
    return {"ok": True}


@router.get("/trial")
def trial_page() -> FileResponse:
    return FileResponse(STATIC / "trial.html", media_type="text/html")


@router.get("/guard")
def guard_page() -> FileResponse:
    return FileResponse(STATIC / "guard.html", media_type="text/html")
