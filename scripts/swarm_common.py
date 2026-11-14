"""Shared helpers for the swarm-detection scripts.

Loading a dataset of posts or comments, parsing timestamps and durations, and
normalising text before comparison.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

TEXT_CANDIDATES = [
    "content", "text", "body", "message", "comment", "comment_text", "full_text",
    "post", "tweet", "selftext", "title",
]
TIME_CANDIDATES = [
    "time_posted", "time posted", "posted_at", "timestamp", "created_at", "created_utc",
    "created", "publish_date", "published_at", "datetime", "date", "time",
]
ID_CANDIDATES = ["id", "post_id", "comment_id", "tweet_id"]

# Label values that mean "this post is not part of a swarm" when evaluating
# against ground truth.
NEGATIVE_LABELS = {"", "0", "0.0", "organic", "human", "false", "no", "none", "normal", "benign", "nan"}


# ---------------------------------------------------------------- text

class _NormTable(dict):
    """Lazy translate table: letters, digits and marks stay, emoji and other
    symbols become separate tokens, everything else becomes a space."""

    def __missing__(self, cp: int) -> str:
        ch = chr(cp)
        cat = unicodedata.category(ch)
        if 0xFE00 <= cp <= 0xFE0F:          # emoji variation selectors
            out = ""
        elif cat[0] in "LNM":
            out = ch
        elif cat == "So":
            out = f" {ch} "
        else:
            out = " "
        self[cp] = out
        return out


_NORM_TABLE = _NormTable()


def normalise(text: object) -> str:
    """Canonical form used for comparison: Unicode-normalised, case-folded,
    punctuation removed, whitespace collapsed. Two posts with the same
    normalised form count as identical."""
    folded = unicodedata.normalize("NFKC", str(text)).casefold()
    return " ".join(folded.translate(_NORM_TABLE).split())


# ---------------------------------------------------------------- time

_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(s|sec|m|min|h|hr|d|day)?s?\s*$", re.I)
_UNIT_SECONDS = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hr": 3600, "d": 86400, "day": 86400}


def parse_duration(value: str | float | int) -> float:
    """'30s', '10m', '2h', '1d' or a bare number of seconds -> seconds."""
    if isinstance(value, (int, float)):
        seconds = float(value)
    else:
        match = _DURATION.match(value)
        if not match:
            raise ValueError(f"Cannot read duration {value!r}. Use e.g. 30s, 10m, 2h or 1d.")
        seconds = float(match.group(1)) * _UNIT_SECONDS[(match.group(2) or "s").lower()]
    if seconds <= 0:
        raise ValueError("Duration must be greater than zero.")
    return seconds


def format_duration(seconds: float) -> str:
    seconds = abs(float(seconds))
    if seconds < 1:
        return "under 1 s"
    for unit, size in (("d", 86400), ("h", 3600), ("min", 60)):
        if seconds >= size:
            amount = seconds / size
            return f"{amount:.0f} {unit}" if amount >= 10 or amount == int(amount) else f"{amount:.1f} {unit}"
    return f"{seconds:.0f} s"


def parse_times(values) -> np.ndarray:
    """Timestamps -> seconds since 1970 UTC (NaN where unreadable).

    Accepts ISO 8601 and other common date strings (month first when
    ambiguous), and Unix epochs in seconds, milliseconds, microseconds or
    nanoseconds. Times without a zone are taken as UTC.
    """
    series = pd.Series(list(values), dtype="object").astype(str).str.strip()
    out = np.full(len(series), np.nan)
    numeric = pd.to_numeric(series, errors="coerce")
    is_num = numeric.notna().to_numpy()
    if is_num.any():
        v = numeric.to_numpy(dtype=float)[is_num]
        mag = np.abs(v)
        v = np.where(mag >= 1e17, v / 1e9, np.where(mag >= 1e14, v / 1e6, np.where(mag >= 1e11, v / 1e3, v)))
        out[is_num] = v
    rest = ~is_num & (series != "").to_numpy()
    if rest.any():
        parsed = pd.to_datetime(series[rest], errors="coerce", utc=True, format="mixed")
        epoch = pd.Timestamp("1970-01-01", tz="UTC")
        out[rest] = (parsed - epoch).dt.total_seconds().to_numpy()
    return out


def parse_time(value: str | float | int) -> float:
    t = parse_times([value])[0]
    if np.isnan(t):
        raise ValueError(f"Cannot read time {value!r}.")
    return float(t)


def to_iso(t: float | None) -> str | None:
    if t is None or np.isnan(t):
        return None
    return datetime.fromtimestamp(float(t), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- dataset

@dataclass
class Dataset:
    ids: list[str]
    texts: list[str]
    times: np.ndarray                 # epoch seconds; NaN only when times were not required
    text_col: str
    time_col: str | None
    columns: list[str]
    rows_read: int
    dropped_empty: int = 0
    dropped_no_time: int = 0
    truncated_from: int | None = None  # original row count if max_rows cut the file
    labels: list[str] | None = None
    warnings: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.texts)


def read_table(path: str | Path) -> pd.DataFrame:
    """Read CSV, TSV, JSON (array of objects) or JSON Lines; every cell as text."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in {".csv", ".tsv", ".txt", ".json", ".jsonl", ".ndjson"}:
        head = path.open("rb").read(2048).lstrip()
        suffix = ".json" if head[:1] == b"[" else ".jsonl" if head[:1] == b"{" else ".csv"
    if suffix in {".jsonl", ".ndjson"}:
        with path.open(encoding="utf-8-sig", errors="replace") as fh:
            records = [json.loads(line) for line in fh if line.strip()]
        frame = pd.DataFrame(records)
    elif suffix == ".json":
        with path.open(encoding="utf-8-sig", errors="replace") as fh:
            data = json.load(fh)
        if isinstance(data, dict):  # {"posts": [...]} style wrappers
            lists = [v for v in data.values() if isinstance(v, list)]
            if not lists:
                raise ValueError("JSON file must contain a list of objects.")
            data = max(lists, key=len)
        frame = pd.DataFrame(data)
    else:
        sep = "\t" if suffix == ".tsv" else ","
        frame = pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False,
                            encoding="utf-8-sig", encoding_errors="replace", on_bad_lines="skip")
    if frame.empty or not len(frame.columns):
        raise ValueError("The dataset has no rows.")
    frame.columns = [str(c) for c in frame.columns]
    return frame.astype(object).where(frame.notna(), "").astype(str)


def guess_columns(columns: list[str]) -> dict[str, str | None]:
    """Best guess for the content, time and id columns by name."""
    lower = {c.lower().strip(): c for c in columns}

    def pick(candidates: list[str], exclude: str | None = None) -> str | None:
        for cand in candidates:
            if cand in lower and lower[cand] != exclude:
                return lower[cand]
        for cand in candidates:
            for name, original in lower.items():
                if cand in name and original != exclude:
                    return original
        return None

    time = pick(TIME_CANDIDATES)
    text = pick(TEXT_CANDIDATES, exclude=time)
    id_col = next((lower[c] for c in ID_CANDIDATES if c in lower), None)
    return {"text": text, "time": time, "id": id_col}


def load_dataset(path: str | Path, text_col: str | None = None, time_col: str | None = None,
                 id_col: str | None = None, label_col: str | None = None,
                 max_rows: int | None = None, require_time: bool = True) -> Dataset:
    """Load posts from a file. Rows with empty content are dropped, and rows
    with an unreadable time are dropped when times are required; both are
    counted so the caller can report them."""
    frame = read_table(path)
    columns = list(frame.columns)
    guess = guess_columns(columns)
    text_col = text_col or guess["text"]
    time_col = time_col or guess["time"]
    id_col = id_col or guess["id"]
    for name, col in (("content", text_col), ("time", time_col), ("id", id_col), ("label", label_col)):
        if col and col not in frame.columns:
            raise ValueError(f"No column named {col!r} for {name}. Columns: {', '.join(columns)}")
    if not text_col:
        raise ValueError(f"Could not tell which column holds the content. Columns: {', '.join(columns)}")
    if require_time and not time_col:
        raise ValueError(f"Could not tell which column holds the time posted. Columns: {', '.join(columns)}")

    rows_read = len(frame)
    truncated_from = None
    if max_rows and rows_read > max_rows:
        truncated_from = rows_read
        frame = frame.iloc[:max_rows]

    ids = frame[id_col].tolist() if id_col else [str(i + 1) for i in range(len(frame))]
    texts = frame[text_col].tolist()
    times = parse_times(frame[time_col]) if time_col else np.full(len(frame), np.nan)
    labels = frame[label_col].tolist() if label_col else None

    has_text = np.array([bool(t.strip()) for t in texts])
    has_time = ~np.isnan(times) if require_time else np.ones(len(frame), dtype=bool)
    keep = has_text & has_time
    idx = np.flatnonzero(keep)
    dataset = Dataset(
        ids=[ids[i] for i in idx],
        texts=[texts[i] for i in idx],
        times=times[idx],
        text_col=text_col, time_col=time_col, columns=columns,
        rows_read=rows_read,
        dropped_empty=int((~has_text).sum()),
        dropped_no_time=int((has_text & ~has_time).sum()),
        truncated_from=truncated_from,
        labels=[labels[i] for i in idx] if labels is not None else None,
    )
    if truncated_from:
        dataset.warnings.append(
            f"The file has {truncated_from:,} rows; only the first {max_rows:,} were analysed.")
    if dataset.dropped_empty:
        dataset.warnings.append(f"{dataset.dropped_empty:,} rows with empty content were skipped.")
    if dataset.dropped_no_time:
        dataset.warnings.append(
            f"{dataset.dropped_no_time:,} rows were skipped because the time in column "
            f"{time_col!r} could not be read.")
    if not len(dataset):
        raise ValueError("No usable rows: every row had empty content or an unreadable time.")
    return dataset


def is_positive_label(label: str) -> bool:
    return str(label).strip().lower() not in NEGATIVE_LABELS
