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
# Demo transparency: show people their own live bot score and its reasons.
# A real site would turn this off, since it teaches attackers what is checked.
SHOW_SCORE = os.environ.get("GUARD_SHOW_SCORE", "1") == "1"
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
    have = {r[1] for r in con.execute("PRAGMA table_info(signups)")}
    for col, kind in (("score", "INTEGER"), ("score_at_signup", "INTEGER"), ("parts", "TEXT"),
                      ("history", "TEXT"), ("ticket", "TEXT"), ("token", "TEXT")):
        if col not in have:
            con.execute(f"ALTER TABLE signups ADD COLUMN {col} {kind}")
    con.execute("""CREATE TABLE IF NOT EXISTS bans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT UNIQUE, reason TEXT, accounts INTEGER, refused INTEGER DEFAULT 0,
        enabled INTEGER DEFAULT 1, created_at REAL, last_seen REAL, source TEXT)""")
    return con


_con = _db()
BAN_AFTER = int(os.environ.get("GUARD_BAN_AFTER", "2"))   # blocked accounts from one IP before it is banned


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

TICKET_ALPHABET = "ACDEFHJKLMNPQRTUVWXY3479"


def _ticket() -> str:
    return "".join(secrets.choice(TICKET_ALPHABET) for _ in range(4))


def judge(row: dict, source: str, campaign: str = "") -> dict:
    """Store a signup, re-judge the recent stream, return this signup's verdict."""
    ticket, token = _ticket(), secrets.token_hex(16)
    with _lock:
        _con.execute("INSERT INTO signups (id, created_at, email, username, ip, asn, asn_org, user_agent, device_id, "
                     "fill_ms, honeypot, webdriver, source, campaign, ticket, token, history) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     [row[f] for f in FIELDS] + [source, campaign, ticket, token, "[]"])
        _rejudge()
        _update_bans()
        out = _con.execute("SELECT action_now, reasons, score, parts FROM signups WHERE id = ?", (row["id"],)).fetchone()
        _con.execute("UPDATE signups SET action_at_signup = action_now, score_at_signup = score WHERE id = ?", (row["id"],))
        _con.commit()
        return {"id": row["id"], "ticket": ticket, "token": token, "action": out["action_now"], "score": out["score"],
                "parts": json.loads(out["parts"] or "[]"), "reasons": json.loads(out["reasons"] or "[]")}


def _update_bans() -> None:
    """Ban an IP once BAN_AFTER of its signups are blocked. A ban that was
    switched off on the dashboard stays off; its count still updates."""
    now = time.time()
    rows = _con.execute("SELECT ip, COUNT(*) AS n, MAX(source) AS src, MAX(reasons) AS why FROM signups "
                        "WHERE action_now = 'block' AND ip != '' GROUP BY ip HAVING COUNT(*) >= ?", (BAN_AFTER,)).fetchall()
    for r in rows:
        reason = (json.loads(r["why"] or "[]") or ["Blocked signups from this address."])[0][:200]
        _con.execute("INSERT INTO bans (ip, reason, accounts, created_at, last_seen, source) VALUES (?,?,?,?,?,?) "
                     "ON CONFLICT(ip) DO UPDATE SET accounts = excluded.accounts",
                     (r["ip"], reason, r["n"], now, now, r["src"]))


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
    now = time.time()
    updates = []
    for k, r in enumerate(live):
        i = offset + k
        parts = report["score_parts"][i]
        score = int(report["score"][i])
        history = json.loads(r["history"] or "[]")
        if not history or history[-1][1] != score:
            history.append([round(now, 1), score])     # every change of this person's score, for the live view
        updates.append((report["actions"][i], json.dumps([x["reason"] for x in parts]), report["risk"][i], score,
                        json.dumps(parts), json.dumps(history[-50:]), r["id"]))
    _con.executemany("UPDATE signups SET action_now = ?, reasons = ?, risk = ?, score = ?, parts = ?, history = ? "
                     "WHERE id = ?", updates)
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
    with _lock:
        ban = _con.execute("SELECT id, accounts FROM bans WHERE ip = ? AND enabled = 1", (ip,)).fetchone()
        if ban:
            _con.execute("UPDATE bans SET refused = refused + 1, last_seen = ? WHERE id = ?", (time.time(), ban["id"]))
            _con.commit()
            _state["version"] += 1
    if ban:
        why = f"This IP address is on Sargas's ban list ({ban['accounts']} bot accounts came from it). Refused at the door."
        return {"id": None, "ticket": None, "action": "block", "banned": True, "score": 100,
                "message": "Neigh. Your IP is banned by Sargas. The stable door is shut, bestie. 🚫🐴",
                "reasons": [why] if campaign else [], "parts": [{"key": "ip_ban", "label": "IP on the ban list", "x": 1,
                "weight": 0, "contribution": 0, "points": 0, "reason": why, "kind": "ban"}]}
    row = {"id": f"t-{secrets.token_hex(5)}", "created_at": time.time(), "email": item.email.strip(),
           "username": item.business.strip(), "ip": ip, "asn": "", "asn_org": "",
           "user_agent": request.headers.get("user-agent", "")[:300], "device_id": item.device_id.strip(),
           "fill_ms": "" if item.fill_ms is None else str(item.fill_ms),
           "honeypot": "1" if item.website.strip() else "", "webdriver": "1" if item.webdriver else ""}
    with _lock:
        if _con.execute("SELECT COUNT(*) FROM signups").fetchone()[0] >= MAX_LIVE_ROWS:
            _con.execute("DELETE FROM signups WHERE id IN (SELECT id FROM signups ORDER BY created_at LIMIT 1000)")
    result = judge(row, "attack" if campaign else "visitor", campaign)
    messages = {"allow": "You're in, bestie. Welcome to the herd. Go find your soulmare. 🐴",
                "review": "Sargas is side-eyeing you. Kinda sus. A human will check your vibe before you can swipe. 👀",
                "block": "Neigh. Sargas has seen your type. Bot behaviour detected, no cap. 🤖"}
    out = {"id": result["id"], "ticket": result["ticket"], "action": result["action"],
           "message": messages[result["action"]], "reasons": result["reasons"] if campaign else []}
    if SHOW_SCORE:
        out.update(token=result["token"], score=result["score"], parts=result["parts"])
    return out


@router.get("/api/trial/status")
def trial_status(id: str, token: str) -> dict:
    """One person's live bot score, for the page they signed up on. Needs the
    token handed out at signup, so nobody can look up someone else."""
    if not SHOW_SCORE:
        raise HTTPException(404, "Not available.")
    with _lock:
        r = _con.execute("SELECT * FROM signups WHERE id = ?", (id[:40],)).fetchone()
        version = _state["version"]
        total = _con.execute("SELECT COUNT(*) FROM signups").fetchone()[0]
    if r is None or not secrets.compare_digest(r["token"] or "", token[:64]):
        raise HTTPException(404, "Signup not found. Live signups are cleared between demos.")
    return {"ticket": r["ticket"], "score": r["score"], "score_at_signup": r["score_at_signup"],
            "action": r["action_now"], "action_at_signup": r["action_at_signup"],
            "parts": json.loads(r["parts"] or "[]"), "history": json.loads(r["history"] or "[]"),
            "version": version, "live_signups": total, "now": time.time()}


def _evaluation_summary() -> dict | None:
    path = ROOT / "data" / "signups" / "evaluation.json"
    try:
        ev = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    out = {}
    for name in ("standard", "hard"):
        sq = ev.get(name, {}).get("score")
        if sq:
            cut70 = next((c for c in sq["cutoffs"] if c["cut"] == 70), None)
            out[name] = {"auc": sq["auc"], "bots": sq["bots"], "people": sq["people"], "bins": sq["bins"],
                         "bots_total": sq["bots_total"], "people_total": sq["people_total"], "cut70": cut70}
    return out or None


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
        bans = [{"id": b["id"], "ip": _mask_ip(b["ip"]), "reason": b["reason"], "accounts": b["accounts"],
                 "refused": b["refused"], "enabled": bool(b["enabled"]), "since": b["created_at"],
                 "last_seen": b["last_seen"], "source": b["source"]}
                for b in _con.execute("SELECT * FROM bans ORDER BY created_at DESC").fetchall()]
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
    bins = list(range(0, 101, 10))
    score_hist = {src: [0] * 10 for src in ("attack", "visitor", "simulated")}
    for r in rows.values():
        if r["score"] is not None and r["source"] in score_hist:
            score_hist[r["source"]][min(int(r["score"]) // 10, 9)] += 1
    return {
        "version": version, "now": now, "uptime": now - _state["started"],
        "history_rows": len(HISTORY), "live_rows": len(rows), "recent_30min": len(recent),
        "scoreboard": scoreboard, "campaigns": campaigns, "timeline": timeline, "groups": groups[:6],
        "score_hist": score_hist, "score_bins": bins, "tested": _evaluation_summary(), "model": report.get("model"),
        "bans": bans, "ban_after": BAN_AFTER,
        "feed": [{"id": r["id"], "time": r["created_at"], "email": _mask(r["email"]), "source": r["source"],
                  "campaign": r["campaign"], "action": r["action_now"], "at_signup": r["action_at_signup"],
                  "risk": r["risk"], "reasons": json.loads(r["reasons"] or "[]")[:3],
                  "parts": json.loads(r["parts"] or "[]")[:3],
                  "ticket": r["ticket"], "score": r["score"], "score_at_signup": r["score_at_signup"],
                  "history": json.loads(r["history"] or "[]")[-12:]} for r in feed],
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
        _con.execute("DELETE FROM bans")
        _rejudge()
        _con.commit()
    return {"ok": True}


@router.get("/trial")
def trial_page() -> FileResponse:
    return FileResponse(STATIC / "trial.html", media_type="text/html")


@router.get("/guard")
def guard_page() -> FileResponse:
    return FileResponse(STATIC / "guard.html", media_type="text/html")


# ---------------------------------------------------------------- attack console
# The attack runs inside the server and posts to the public signup API over
# HTTP, exactly like the command-line attack script. Each launch sends a fixed
# number of signups and stops; nothing repeats on its own.

import sys as _sys  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

_sys.path.insert(0, str(ROOT / "scripts"))
import attack_demo  # noqa: E402

SELF_URL = os.environ.get("GUARD_SELF_URL", "http://127.0.0.1:8000")
CAMPAIGN_INFO = {
    "naive-bot": "A script posting straight to the signup API: throwaway inboxes, user12345 names, "
                 "fills the hidden field, never runs the page.",
    "alias-farm": "One Gmail inbox multiplied with dots and +tags, from a real-looking browser.",
    "stealth-farm": "Realistic names, a normal browser string, human-speed form filling, but only 3 "
                    "devices behind every account. Each signup looks fine on its own.",
    "humanlike": "Varies every detail and waits between signups. We expect this one to be hard to catch.",
}
_attack: dict = {"running": False, "stop": False, "campaign": None, "sent": 0, "total": 0, "log": [], "runs": 0}
_attack_lock = threading.Lock()


def _source_ip(campaign: str, k: int, rng: random.Random) -> str:
    """Where each console bot appears to come from, using documentation-only
    address ranges (RFC 5737), so nothing real is ever named. A naive bot sits
    on one cloud server; farms rotate residential proxies, which is why an IP
    ban alone cannot stop them."""
    if campaign == "naive-bot":
        return "203.0.113.66"
    if campaign == "alias-farm":
        return f"198.51.100.{20 + k % 3}"
    return f"{rng.choice(DEMO_NETS)}{rng.randrange(1, 255)}"


def _run_attack(campaign: str, speed: float) -> None:
    rng = random.Random()
    items = list(attack_demo.CAMPAIGNS[campaign](rng))
    with _attack_lock:
        _attack.update(running=True, stop=False, campaign=campaign, sent=0, total=len(items))
    try:
        for k, (body, ua, delay) in enumerate(items):
            if _attack["stop"]:
                break
            req = urllib.request.Request(SELF_URL + "/api/trial/signup", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "User-Agent": ua,
                                                  "X-Demo-Truth": f"{DEMO_KEY}:{campaign}",
                                                  "X-Forwarded-For": _source_ip(campaign, k, rng)})
            try:
                with urllib.request.urlopen(req, timeout=30) as res:
                    r = json.loads(res.read())
            except (urllib.error.URLError, ValueError) as exc:
                r = {"action": "error", "reasons": [str(exc)[:120]]}
            entry = {"t": time.time(), "campaign": campaign, "email": body["email"], "action": r.get("action"),
                     "ip": req.get_header("X-forwarded-for"), "banned": bool(r.get("banned")),
                     "score": r.get("score"), "ticket": r.get("ticket"),
                     "reason": (r.get("reasons") or [""])[0][:240]}
            with _attack_lock:
                _attack["sent"] += 1
                _attack["log"] = (_attack["log"] + [entry])[-200:]
            time.sleep(delay / max(speed, 0.1))
    finally:
        with _attack_lock:
            _attack.update(running=False, runs=_attack["runs"] + 1)


class AttackStart(BaseModel):
    campaign: str
    speed: float = Field(default=1.0, ge=0.25, le=5)


@router.post("/api/attack/start")
def attack_start(item: AttackStart, request: Request) -> dict:
    _check_key(request)
    if item.campaign not in attack_demo.CAMPAIGNS:
        raise HTTPException(400, f"Unknown campaign. Choose from {', '.join(attack_demo.CAMPAIGNS)}.")
    with _attack_lock:
        if _attack["running"]:
            raise HTTPException(409, f"{_attack['campaign']} is still running. Wait or stop it first.")
        _attack["running"] = True
    threading.Thread(target=_run_attack, args=(item.campaign, item.speed), daemon=True).start()
    return {"ok": True}


@router.post("/api/attack/stop")
def attack_stop(request: Request) -> dict:
    _check_key(request)
    _attack["stop"] = True
    return {"ok": True}


@router.post("/api/attack/clear-log")
def attack_clear(request: Request) -> dict:
    _check_key(request)
    with _attack_lock:
        _attack["log"] = []
    return {"ok": True}


@router.get("/api/attack/status")
def attack_status(request: Request) -> dict:
    _check_key(request)
    with _attack_lock:
        state = {k: _attack[k] for k in ("running", "campaign", "sent", "total", "runs")}
        state["log"] = list(reversed(_attack["log"][-60:]))
    sizes = {name: len(list(gen(random.Random(0)))) for name, gen in attack_demo.CAMPAIGNS.items()}
    state["campaigns"] = [{"name": n, "signups": sizes[n], "about": CAMPAIGN_INFO.get(n, "")}
                          for n in attack_demo.CAMPAIGNS]
    return state


@router.get("/attack")
def attack_page() -> FileResponse:
    return FileResponse(STATIC / "attack.html", media_type="text/html")


# ---------------------------------------------------------------- ban list

DEMO_NETS = ("192.0.2.", "198.51.100.", "203.0.113.")    # documentation ranges used by the console's bots


def _mask_ip(ip: str) -> str:
    """Console bots use documentation-only addresses and are shown in full;
    a real visitor's address is shown without its last part."""
    if ip.startswith(DEMO_NETS) or ip in {"127.0.0.1", "testclient"}:
        return ip
    if ip.count(".") == 3:
        return ip.rsplit(".", 1)[0] + ".•••"
    if ":" in ip:
        return ":".join(ip.split(":")[:3]) + ":•••"
    return "•••"


class BanToggle(BaseModel):
    id: int
    enabled: bool


@router.post("/api/guard/ban")
def ban_toggle(item: BanToggle, request: Request) -> dict:
    """Switch one ban on or off (open to anyone on the dashboard, by request)."""
    with _lock:
        cur = _con.execute("UPDATE bans SET enabled = ? WHERE id = ?", (1 if item.enabled else 0, item.id))
        _con.commit()
        _state["version"] += 1
    if not cur.rowcount:
        raise HTTPException(404, "No such ban.")
    return {"ok": True}


class BanReset(BaseModel):
    id: int


@router.post("/api/guard/ban/reset")
def ban_reset(item: BanReset) -> dict:
    """Forgive an IP completely: remove its ban and delete its earlier
    signups, so its next signup is judged from a clean slate."""
    with _lock:
        row = _con.execute("SELECT ip FROM bans WHERE id = ?", (item.id,)).fetchone()
        if row is None:
            raise HTTPException(404, "No such ban.")
        deleted = _con.execute("DELETE FROM signups WHERE ip = ?", (row["ip"],)).rowcount
        _con.execute("DELETE FROM bans WHERE id = ?", (item.id,))
        _rejudge()
        _update_bans()
        _con.commit()
    return {"ok": True, "signups_deleted": deleted}
