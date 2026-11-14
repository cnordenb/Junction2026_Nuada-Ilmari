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
