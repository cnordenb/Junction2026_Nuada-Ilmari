"""Swarm detection dashboard: one web page plus a small JSON API.

Run locally:
    uvicorn dashboard.app:app --reload
then open http://127.0.0.1:8000

The server never opens a path supplied by the browser. A dataset is either a
file in the data folder, chosen by name from a listing, or an upload stored
under a random name.
"""
from __future__ import annotations

import os
import re
import secrets
import sys
import tempfile
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from detect_swarm import DEFAULT_MIN_SIZE, analyse  # noqa: E402
from similarity_score import DEFAULT_THRESHOLD, semantic_available  # noqa: E402
from swarm_common import guess_columns, load_dataset, parse_duration, read_table  # noqa: E402

DATA_DIR = Path(os.environ.get("SWARM_DATA_DIR", ROOT / "data"))
UPLOAD_DIR = Path(os.environ.get("SWARM_UPLOAD_DIR", Path(tempfile.gettempdir()) / "swarm_uploads"))
MAX_UPLOAD_BYTES = int(os.environ.get("SWARM_MAX_UPLOAD_MB", "30")) * 1024 * 1024
MAX_ROWS = int(os.environ.get("SWARM_MAX_ROWS", "20000"))
MAX_CONCURRENT = int(os.environ.get("SWARM_MAX_CONCURRENT", "2"))
ALLOW_SEMANTIC = os.environ.get("SWARM_ALLOW_SEMANTIC", "1") != "0"
UPLOAD_TTL_SECONDS = 2 * 3600
SUFFIXES = (".csv", ".tsv", ".json", ".jsonl", ".ndjson")
UPLOAD_NAME = re.compile(r"^[0-9a-f]{32}\.(csv|tsv|json|jsonl|ndjson)$")
MAX_CELL = 1000                      # characters of post content sent to the browser

app = FastAPI(title="Swarm detector", docs_url=None, redoc_url=None)
_busy = threading.BoundedSemaphore(MAX_CONCURRENT)
_upload_names: dict[str, str] = {}   # stored file name -> name the user gave


def _server_files() -> list[Path]:
    if not DATA_DIR.is_dir():
        return []
    return sorted(p for p in DATA_DIR.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES)


def _resolve(dataset_id: str) -> tuple[Path, str]:
    """Dataset id -> (path, display name). Only names from the server listing
    or well-formed upload names are accepted, so no path can be smuggled in."""
    kind, _, name = dataset_id.partition(":")
    if kind == "server":
        for path in _server_files():
            if path.name == name:
                return path, name
    elif kind == "upload" and UPLOAD_NAME.match(name):
        path = UPLOAD_DIR / name
        if path.is_file():
            return path, _upload_names.get(name, "uploaded file")
    raise HTTPException(404, "Dataset not found. Uploaded files are removed after two hours; upload it again.")


def _purge_uploads() -> None:
    if not UPLOAD_DIR.is_dir():
        return
    cutoff = time.time() - UPLOAD_TTL_SECONDS
    for path in UPLOAD_DIR.iterdir():
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
            _upload_names.pop(path.name, None)


def _info(dataset_id: str) -> dict:
    path, name = _resolve(dataset_id)
    try:
        frame = read_table(path)
    except Exception as exc:  # unreadable file: say so instead of a 500
        raise HTTPException(400, f"Could not read {name}: {exc}") from exc
    columns = list(frame.columns)
    preview = [{c: str(v)[:200] for c, v in row.items()} for row in frame.head(5).to_dict("records")]
    return {"id": dataset_id, "name": name, "rows": len(frame), "columns": columns,
            "guess": guess_columns(columns), "preview": preview, "max_rows": MAX_ROWS}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html", media_type="text/html")


@app.get("/api/config")
def config() -> dict:
    return {"max_rows": MAX_ROWS, "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
            "semantic_available": ALLOW_SEMANTIC and semantic_available(),
            "defaults": {"threshold": DEFAULT_THRESHOLD, "half_life": "10m", "min_size": DEFAULT_MIN_SIZE}}


@app.get("/api/datasets")
def datasets() -> list[dict]:
    return [{"id": f"server:{p.name}", "name": p.name, "bytes": p.stat().st_size} for p in _server_files()]


@app.get("/api/datasets/info")
def dataset_info(id: str) -> dict:
    return _info(id)


@app.post("/api/datasets")
async def upload(request: Request, name: str = "upload.csv") -> dict:
    suffix = Path(name).suffix.lower()
    if suffix not in SUFFIXES:
        raise HTTPException(400, "Unsupported file type. Use CSV, TSV, JSON or JSON Lines.")
    too_big = HTTPException(413, f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if int(request.headers.get("content-length") or 0) > MAX_UPLOAD_BYTES:
        raise too_big
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise too_big
        chunks.append(chunk)
    if not size:
        raise HTTPException(400, "The file is empty.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    _purge_uploads()
    stored = f"{secrets.token_hex(16)}{suffix}"
    (UPLOAD_DIR / stored).write_bytes(b"".join(chunks))
    _upload_names[stored] = Path(name).name[:120]
    try:
        return _info(f"upload:{stored}")
    except HTTPException:
        (UPLOAD_DIR / stored).unlink(missing_ok=True)
        raise


class Seed(BaseModel):
    content: str = Field(max_length=5000)
    time: str | None = Field(default=None, max_length=40)


class AnalyzeRequest(BaseModel):
    dataset_id: str
    text_col: str | None = None
    time_col: str | None = None
    label_col: str | None = None
    seeds: list[Seed] = Field(default_factory=list, max_length=50)
    threshold: float = Field(default=DEFAULT_THRESHOLD, ge=20, le=100)
    half_life: str = "10m"
    min_size: int = Field(default=DEFAULT_MIN_SIZE, ge=2, le=10000)
    semantic: bool = False


def _trim(post: dict) -> dict:
    if len(post["content"]) > MAX_CELL:
        post = {**post, "content": post["content"][:MAX_CELL] + "…"}
    return post


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    path, name = _resolve(req.dataset_id)
    if req.semantic and not (ALLOW_SEMANTIC and semantic_available()):
        raise HTTPException(400, "Semantic mode is not installed on this server.")
    if not _busy.acquire(blocking=False):
        raise HTTPException(429, "The server is busy with other analyses. Try again in a minute.")
    started = time.time()
    try:
        ds = load_dataset(path, req.text_col or None, req.time_col or None,
                          label_col=req.label_col or None, max_rows=MAX_ROWS)
        report = analyse(ds, [s.model_dump() for s in req.seeds], threshold=req.threshold,
                         half_life=parse_duration(req.half_life), min_size=req.min_size,
                         semantic=req.semantic, sample=25)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        _busy.release()
    for cluster in report["clusters"]:
        cluster["posts"] = [_trim(p) for p in cluster["posts"]]
    if report["seeds"]:
        report["seeds"]["matches"] = [_trim(p) for p in report["seeds"]["matches"]]
    report["dataset"]["name"] = name
    report["elapsed_seconds"] = round(time.time() - started, 1)
    return report


# ================================================================ signup guard
# Free-tier signup abuse: batch analysis of signup files in data/signups/, the
# accuracy figures from scripts/eval_signups.py, and a live "try to sign up"
# check. Live signups are kept in memory per browser session only, so one
# visitor never sees another visitor's entries.

import hashlib  # noqa: E402
from collections import OrderedDict  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from signup_guard import analyse as analyse_signups, load_signups  # noqa: E402

SIGNUP_DIR = DATA_DIR / "signups"
DEMO_SIGNUPS = SIGNUP_DIR / "demo_signups.csv"
TRUST_PROXY = os.environ.get("SIGNUP_TRUST_PROXY", "0") == "1"
LIVE_MAX_SESSIONS, LIVE_MAX_PER_SESSION = 1000, 100
_live: "OrderedDict[str, dict]" = OrderedDict()
_live_lock = threading.Lock()
_demo_cache: dict = {}


def _signup_files() -> list[Path]:
    if not SIGNUP_DIR.is_dir():
        return []
    return sorted(p for p in SIGNUP_DIR.iterdir()
                  if p.is_file() and p.suffix.lower() in SUFFIXES and p.name != "evaluation.json")


def _resolve_signups(dataset_id: str) -> tuple[Path, str]:
    kind, _, name = dataset_id.partition(":")
    if kind == "signups":
        for path in _signup_files():
            if path.name == name:
                return path, name
    return _resolve(dataset_id)


@app.get("/signups")
def signups_page() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "signups.html", media_type="text/html")


@app.get("/api/signups/datasets")
def signup_datasets() -> list[dict]:
    return [{"id": f"signups:{p.name}", "name": p.name} for p in _signup_files()]


@app.get("/api/signups/evaluation")
def signup_evaluation() -> dict:
    path = SIGNUP_DIR / "evaluation.json"
    if not path.is_file():
        raise HTTPException(404, "No evaluation yet. Run scripts/eval_signups.py.")
    import json
    return json.loads(path.read_text(encoding="utf-8"))


class SignupAnalyzeRequest(BaseModel):
    dataset_id: str
    label_col: str | None = None


def _public_report(report: dict, name: str) -> dict:
    report.pop("actions", None)
    report["dataset"]["name"] = name
    return report


@app.post("/api/signups/analyze")
def signup_analyze(req: SignupAnalyzeRequest) -> dict:
    path, name = _resolve_signups(req.dataset_id)
    if not _busy.acquire(blocking=False):
        raise HTTPException(429, "The server is busy with other analyses. Try again in a minute.")
    started = time.time()
    try:
        su = load_signups(path, req.label_col or None, max_rows=MAX_ROWS)
        if req.label_col:
            frame = read_table(path)
            if "note" in frame.columns and len(frame) == len(su.frame):
                su.frame["note"] = frame["note"].tolist()
        report = analyse_signups(su)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        _busy.release()
    report = _public_report(report, name)
    report["elapsed_seconds"] = round(time.time() - started, 2)
    return report


class LiveSignup(BaseModel):
    session: str = Field(min_length=16, max_length=64, pattern=r"^[0-9a-f]+$")
    email: str = Field(min_length=3, max_length=200)
    username: str = Field(default="", max_length=100)
    device_id: str = Field(default="", max_length=64)


def _client_ip(request: Request) -> str:
    if TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else ""


def _demo_frame() -> pd.DataFrame:
    """The ordinary signups of the demo stream (planted abuse removed, so live
    test signups form their own groups), shifted so the stream ends now."""
    mtime = DEMO_SIGNUPS.stat().st_mtime
    if _demo_cache.get("mtime") != mtime:
        su = load_signups(DEMO_SIGNUPS, label_col="label" if "label" in read_table(DEMO_SIGNUPS).columns else None)
        frame = su.frame
        if su.labels is not None:
            frame = frame[[lab == "organic" for lab in su.labels]].reset_index(drop=True)
        _demo_cache.update(mtime=mtime, frame=frame, end=float(frame["time"].max()))
    frame = _demo_cache["frame"].copy()
    frame["time"] = frame["time"] + (time.time() - 60 - _demo_cache["end"])
    return frame


@app.post("/api/signups/live")
def signup_live(item: LiveSignup, request: Request) -> dict:
    if "@" not in item.email:
        raise HTTPException(400, "That does not look like an email address.")
    ip = _client_ip(request)
    entry = {"id": f"live-{secrets.token_hex(4)}", "time": time.time(), "email": item.email.strip(),
             "username": item.username.strip(), "ip": ip, "asn": "", "asn_org": "",
             "user_agent": request.headers.get("user-agent", "")[:300], "device_id": item.device_id.strip()}
    with _live_lock:
        now = time.time()
        for key in [k for k, v in _live.items() if now - v["seen"] > UPLOAD_TTL_SECONDS]:
            _live.pop(key)
        sess = _live.setdefault(item.session, {"rows": [], "seen": now})
        sess["seen"] = now
        _live.move_to_end(item.session)
        while len(_live) > LIVE_MAX_SESSIONS:
            _live.popitem(last=False)
        if len(sess["rows"]) >= LIVE_MAX_PER_SESSION:
            raise HTTPException(429, "This session has reached 100 test signups. Reset it to continue.")
        sess["rows"].append(entry)
        mine = list(sess["rows"])
    if not _busy.acquire(timeout=10):
        raise HTTPException(429, "The server is busy. Try again in a moment.")
    try:
        frame = pd.concat([_demo_frame(), pd.DataFrame(mine)], ignore_index=True)
        from signup_guard import Signups
        report = analyse_signups(Signups(frame, {}, len(frame)), sample=LIVE_MAX_PER_SESSION + 2000)
    finally:
        _busy.release()
    actions = report.pop("actions")
    offset = len(frame) - len(mine)
    results = [{"id": row["id"], "email": row["email"], "username": row["username"],
                "action": actions[offset + k]} for k, row in enumerate(mine)]
    # Which group, if any, each live signup joined (the analysis keeps member
    # indices internally; recompute membership by id from the full sample).
    live_ids = {r["id"] for r in mine}
    groups = []
    for c in report["clusters"]:
        members = [s["id"] for s in c.pop("signups") if s["id"] in live_ids]
        if members:
            groups.append({k: c[k] for k in ("id", "size", "action", "organisation", "evidence", "timing",
                                             "why", "first", "last")} | {"live_members": len(members)})
    from signup_guard import signup_signals
    reasons = [x["reason"] for x in signup_signals(frame)[-1]]
    return {"latest": {**results[-1], "reasons": reasons, "ip_seen": ip, "ua_seen": entry["user_agent"][:120]},
            "session": results, "groups": groups}


@app.delete("/api/signups/live")
def signup_live_reset(session: str) -> dict:
    with _live_lock:
        _live.pop(session, None)
    return {"ok": True}


# ================================================================ live demo (trial site + guard dashboard)
# Subdomains on the public server: trial.<domain> is the small-business site,
# guard.<domain> the live dashboard. Locally, use /trial and /guard.


import dashboard.live as live  # noqa: E402

app.include_router(live.router)


@app.on_event("startup")
def _start_live() -> None:
    live.start_background()


@app.middleware("http")
async def _subdomains(request: Request, call_next):
    host = request.headers.get("host", "").split(":")[0].lower()
    if request.url.path == "/":
        if host.startswith("trial."):
            return live.trial_page()
        if host.startswith("guard."):
            return live.guard_page()
    return await call_next(request)
