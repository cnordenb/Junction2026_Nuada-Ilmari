"""Shared helpers for the swarm-detection scripts.

Loading a dataset of posts or comments, parsing timestamps and durations, and
normalising text before comparison.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
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
ACCOUNT_CANDIDATES = [
    "account", "account_id", "author", "author_id", "user", "user_id", "userid", "username",
    "user_name", "screen_name", "handle", "external_author_id",
]

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
    accounts: list[str] | None = None  # "" where the account is unknown
    account_col: str | None = None
    warnings: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.texts)


def _format_of(path: Path) -> str:
    """File format by suffix, or by the first byte when the suffix is unknown."""
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv", ".txt", ".json", ".jsonl", ".ndjson"}:
        return suffix
    head = path.open("rb").read(2048).lstrip()[:1]
    return {b"[": ".json", b"{": ".jsonl"}.get(head, ".csv")


def _read_json_lines(path: Path) -> pd.DataFrame:
    with path.open(encoding="utf-8-sig", errors="replace") as fh:
        return pd.DataFrame([json.loads(line) for line in fh if line.strip()])


def _read_json(path: Path) -> pd.DataFrame:
    with path.open(encoding="utf-8-sig", errors="replace") as fh:
        data = json.load(fh)
    if isinstance(data, dict):  # {"posts": [...]} style wrappers
        lists = [v for v in data.values() if isinstance(v, list)]
        if not lists:
            raise ValueError("JSON file must contain a list of objects.")
        data = max(lists, key=len)
    return pd.DataFrame(data)


def _read_delimited(path: Path, sep: str) -> pd.DataFrame:
    return pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False,
                       encoding="utf-8-sig", encoding_errors="replace", on_bad_lines="skip")


_READERS = {
    ".jsonl": _read_json_lines, ".ndjson": _read_json_lines, ".json": _read_json,
    ".tsv": lambda path: _read_delimited(path, "\t"),
}


def read_table(path: str | Path) -> pd.DataFrame:
    """Read CSV, TSV, JSON (array of objects) or JSON Lines; every cell as text."""
    path = Path(path)
    reader = _READERS.get(_format_of(path), lambda p: _read_delimited(p, ","))
    frame = reader(path)
    if frame.empty or not len(frame.columns):
        raise ValueError("The dataset has no rows.")
    frame.columns = [str(c) for c in frame.columns]
    return frame.astype(object).where(frame.notna(), "").astype(str)


def _exact(lower: dict[str, str], candidates: list[str], exclude: str | None = None) -> str | None:
    """First candidate that is a column name (other than `exclude`)."""
    return next((lower[c] for c in candidates if c in lower and lower[c] != exclude), None)


def _loose(lower: dict[str, str], candidates: list[str], exclude: str | None) -> str | None:
    """First column whose name contains a candidate."""
    return next((original for cand in candidates for name, original in lower.items()
                 if cand in name and original != exclude), None)


def guess_columns(columns: list[str]) -> dict[str, str | None]:
    """Best guess for the content, time, id and account columns by name."""
    lower = {c.lower().strip(): c for c in columns}
    time = _exact(lower, TIME_CANDIDATES) or _loose(lower, TIME_CANDIDATES, None)
    text = _exact(lower, TEXT_CANDIDATES, time) or _loose(lower, TEXT_CANDIDATES, time)
    # Id and account columns are matched by exact name only: a loose match
    # ("user" in "user_agent") would silently pick the wrong column.
    return {"text": text, "time": time, "id": _exact(lower, ID_CANDIDATES),
            "account": _exact(lower, ACCOUNT_CANDIDATES)}


def _choose_columns(columns: list[str], asked: dict[str, str | None], require_time: bool) -> dict[str, str | None]:
    """The column to use for each role: the one asked for, else a guess for
    content, time and id. Raises when a named column is missing or a required
    role has no column."""
    guess = guess_columns(columns)
    chosen = {
        "content": asked["content"] or guess["text"],
        "time": asked["time"] or guess["time"],
        "id": asked["id"] or guess["id"],
        "label": asked["label"],
        "account": guess["account"] if asked["account"] == "auto" else asked["account"],
    }
    _check_columns(columns, chosen, ("content", "time") if require_time else ("content",))
    return chosen


def _check_columns(columns: list[str], chosen: dict[str, str | None], required: tuple[str, ...]) -> None:
    listing = ", ".join(columns)
    for role, col in chosen.items():
        if col and col not in columns:
            raise ValueError(f"No column named {col!r} for {role}. Columns: {listing}")
    for role in required:
        if not chosen[role]:
            what = {"content": "the content", "time": "the time posted"}[role]
            raise ValueError(f"Could not tell which column holds {what}. Columns: {listing}")


def _column(frame: pd.DataFrame, col: str | None) -> list[str] | None:
    return frame[col].tolist() if col else None


def _kept(values: list | None, idx: np.ndarray) -> list | None:
    return None if values is None else [values[i] for i in idx]


def _drop_warnings(dataset: Dataset, max_rows: int | None) -> list[str]:
    notes = []
    if dataset.truncated_from:
        notes.append(f"The file has {dataset.truncated_from:,} rows; only the first {max_rows:,} were analysed.")
    if dataset.dropped_empty:
        notes.append(f"{dataset.dropped_empty:,} rows with empty content were skipped.")
    if dataset.dropped_no_time:
        notes.append(f"{dataset.dropped_no_time:,} rows were skipped because the time in column "
                     f"{dataset.time_col!r} could not be read.")
    return notes


def load_dataset(path: str | Path, text_col: str | None = None, time_col: str | None = None,
                 id_col: str | None = None, label_col: str | None = None,
                 max_rows: int | None = None, require_time: bool = True,
                 account_col: str | None = None) -> Dataset:
    """Load posts from a file. Rows with empty content are dropped, and rows
    with an unreadable time are dropped when times are required; both are
    counted so the caller can report them. `account_col` is optional; pass
    "auto" to use a column with a standard name (author, user_id, ...) if
    there is one."""
    frame = read_table(path)
    columns = list(frame.columns)
    col = _choose_columns(columns, {"content": text_col, "time": time_col, "id": id_col,
                                    "label": label_col, "account": account_col}, require_time)
    rows_read = len(frame)
    truncated = bool(max_rows) and rows_read > max_rows
    if truncated:
        frame = frame.iloc[:max_rows]

    texts = frame[col["content"]].tolist()
    times = parse_times(frame[col["time"]]) if col["time"] else np.full(len(frame), np.nan)
    accounts = _column(frame, col["account"])
    has_text = np.array([bool(t.strip()) for t in texts])
    has_time = ~np.isnan(times) if require_time else np.ones(len(frame), dtype=bool)
    idx = np.flatnonzero(has_text & has_time)
    dataset = Dataset(
        ids=_kept(_column(frame, col["id"]) or [str(i + 1) for i in range(len(frame))], idx),
        texts=_kept(texts, idx),
        times=times[idx],
        text_col=col["content"], time_col=col["time"], columns=columns,
        rows_read=rows_read,
        dropped_empty=int((~has_text).sum()),
        dropped_no_time=int((has_text & ~has_time).sum()),
        truncated_from=rows_read if truncated else None,
        labels=_kept(_column(frame, col["label"]), idx),
        accounts=_kept(accounts and [a.strip() for a in accounts], idx),
        account_col=col["account"],
    )
    dataset.warnings.extend(_drop_warnings(dataset, max_rows))
    if not len(dataset):
        raise ValueError("No usable rows: every row had empty content or an unreadable time.")
    return dataset


def is_positive_label(label: str) -> bool:
    return str(label).strip().lower() not in NEGATIVE_LABELS


def clip(text: object, width: int) -> str:
    """One line, cut to `width` characters with an ellipsis."""
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 1] + "…"


def pair_dataset_parser(description: str, pair_args: tuple[str, str], pair_help: str, dataset_help: str):
    """The command line the two score scripts share: `pair X Y` scores two
    values, `dataset FILE` scores a file. Returns (parser, pair, dataset) so
    each script can add its own options."""
    parser = argparse.ArgumentParser(description=description)
    sub = parser.add_subparsers(dest="command", required=True)
    pair = sub.add_parser("pair", help=pair_help)
    for name in pair_args:
        pair.add_argument(name)
    data = sub.add_parser("dataset", help=dataset_help)
    data.add_argument("path")
    data.add_argument("--max-rows", type=int)
    data.add_argument("--out", help="write per-post scores to this CSV file")
    data.add_argument("--json", action="store_true", help="print JSON instead of text")
    return parser, pair, data


def run_cli(main) -> int:
    """Run a script's main(); errors a user can fix become one line on stderr and exit code 1."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        return main()
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _ratio(part: int, whole: int) -> float | None:
    # 6 places, so a later round to 0.1% is not a second rounding of a rounded value.
    return round(part / whole, 6) if whole else None


def confusion(flagged: np.ndarray, truth: np.ndarray) -> dict:
    """Counts and rates of a yes/no call (`flagged`) against the answer key (`truth`)."""
    tp, fp = int((flagged & truth).sum()), int((flagged & ~truth).sum())
    fn, tn = int((~flagged & truth).sum()), int((~flagged & ~truth).sum())
    return {"true_positives": tp, "false_positives": fp, "false_negatives": fn, "true_negatives": tn,
            "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn),
            "false_positive_rate": _ratio(fp, fp + tn)}
