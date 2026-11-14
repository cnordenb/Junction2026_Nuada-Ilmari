"""Temporal synchrony score for posts and comments.

    100 = posted at exactly the same time
      0 = far apart, with no discernible timing pattern

Two posts: the score halves for every half-life of time between them
(default 10 minutes), so 0 s apart = 100, 10 min = 50, 1 h = 1.6.

A group of posts gets four raw measurements, each 0-100:
    burst    each post's closeness to the nearest other post in the group,
             averaged (the two-post score, generalised)
    regular  near-constant gaps between posts, like a timer (needs 8+ posts)
    hourly   posts land on the same minute of the hour (needs 8+ posts over 2+ hours)
    daily    posts land on the same time of day (needs 8+ posts over 2+ days)

A busy dataset makes any group look synchronised, so each measurement is
compared with random groups of the same size drawn from the whole dataset.
The group's score is how far it rises above the "chance level", the value
only 1 in 1,000 of those random groups reach; a group that looks like
chance scores 0. The reported score is the highest of the four, and names
the pattern it came from.

Usage:
    python scripts/sync_score.py pair "2026-11-14 10:00:00" "2026-11-14 10:04:30"
    python scripts/sync_score.py dataset data/posts.csv --half-life 10m
    python scripts/sync_score.py dataset data/posts.csv --ids 17,42,99,512
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np
from scipy.stats import poisson

from swarm_common import (Dataset, format_duration, load_dataset, pair_dataset_parser, parse_duration,
                          parse_time, run_cli, to_iso)

DEFAULT_HALF_LIFE = 600.0
PERIODS = {"hourly": 3600.0, "daily": 86400.0}
COMPONENTS = ("burst", "regular", "hourly", "daily")
MIN_PATTERN_POSTS = 8        # smaller groups hit a "pattern" by luck too easily; they get burst only
N_RANDOM = 4000              # random groups per baseline (fewer for very large groups)
MAX_NULL_CELLS = 4_000_000   # cap on random groups x group size
# "Chance level": the value only 1 in 1,000 random groups reach. Strict on
# purpose, because a dataset can hold hundreds of clusters and each one is
# tested on four measurements; a lenient level would flag some by luck.
BASELINE_PERCENTILE = 99.9


def pair_sync(t1: float, t2: float, half_life: float = DEFAULT_HALF_LIFE) -> float:
    """Synchrony of two timestamps (epoch seconds): 100 at the same instant,
    halving for every half-life between them."""
    return 100.0 * 0.5 ** (abs(float(t1) - float(t2)) / half_life)


def raw_components(times: np.ndarray, half_life: float) -> dict[str, np.ndarray]:
    """Raw measurements for many groups at once. `times` is (groups, n) with
    each row sorted. Returns one array of length `groups` per component."""
    groups, n = times.shape
    out = {name: np.zeros(groups) for name in COMPONENTS}
    if n < 2:
        return out
    gaps = np.diff(times, axis=1)
    far = np.full((groups, 1), np.inf)
    nearest = np.minimum(np.hstack([far, gaps]), np.hstack([gaps, far]))
    out["burst"] = 100.0 * np.mean(0.5 ** (nearest / half_life), axis=1)
    if n >= MIN_PATTERN_POSTS:
        mean = gaps.mean(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            variation = np.where(mean > 0, gaps.std(axis=1) / mean, np.inf)
        out["regular"] = 100.0 * np.clip(1.0 - variation, 0.0, 1.0)
        span = times[:, -1] - times[:, 0]
        for name, period in PERIODS.items():
            angle = 2.0 * np.pi * (times % period) / period
            concentration = np.abs(np.exp(1j * angle).mean(axis=1))
            out[name] = np.where(span >= 2 * period, 100.0 * concentration, 0.0)
    return out


def _bucket(n: int) -> int:
    """Group sizes above 30 share a baseline with nearby sizes."""
    if n <= 30:
        return n
    return int(round(30 * 1.2 ** round(math.log(n / 30) / math.log(1.2))))


class SyncScorer:
    """Scores groups of timestamps against a background timeline.

    `background` is every post time in the dataset. Without it (or when the
    group is most of the dataset) there is nothing to compare bursts with, so
    the burst score is reported as measured, and the pattern scores are
    compared with timestamps scattered evenly over the group's own time span.
    """

    def __init__(self, background: np.ndarray | None = None, half_life: float = DEFAULT_HALF_LIFE,
                 n_random: int = N_RANDOM, seed: int = 0):
        self.background = None if background is None else np.sort(np.asarray(background, dtype=float))
        self.half_life = float(half_life)
        self.n_random = n_random
        self.rng = np.random.default_rng(seed)
        self._cache: dict[int, dict[str, np.ndarray]] = {}

    def _dataset_null(self, n: int) -> dict[str, np.ndarray] | None:
        bg = self.background
        if bg is None or n < 2 or len(bg) < 2 * n:
            return None
        size = _bucket(n)
        if len(bg) < 2 * size:
            size = n
        if size not in self._cache:
            rows = self._rows(size)
            # Draw with replacement (fast), then redraw the few rows that
            # picked the same post twice so every group has distinct posts.
            idx = np.sort(self.rng.integers(0, len(bg), size=(rows, size)), axis=1)
            for r in np.flatnonzero((np.diff(idx, axis=1) == 0).any(axis=1)):
                idx[r] = np.sort(self.rng.choice(len(bg), size, replace=False))
            self._cache[size] = raw_components(bg[idx], self.half_life)
        return self._cache[size]

    def _rows(self, size: int) -> int:
        return int(np.clip(MAX_NULL_CELLS // size, 500, self.n_random))

    def score(self, times) -> dict:
        t = np.sort(np.asarray(times, dtype=float))
        t = t[~np.isnan(t)]
        n = len(t)
        result = {"n": n, "sync": 0.0, "pattern": None, "raw": dict.fromkeys(COMPONENTS, 0.0),
                  "baseline": dict.fromkeys(COMPONENTS, 0.0), "adjusted": dict.fromkeys(COMPONENTS, 0.0),
                  "beats_random": None, "baseline_source": "none", "span_seconds": 0.0,
                  "median_gap_to_nearest": None, "mean_gap": None}
        if n < 2:
            return result
        gaps = np.diff(t)
        nearest = np.minimum(np.concatenate([[np.inf], gaps]), np.concatenate([gaps, [np.inf]]))
        result["span_seconds"] = float(t[-1] - t[0])
        result["median_gap_to_nearest"] = float(np.median(nearest))
        result["mean_gap"] = float(gaps.mean())
        raw = {k: float(v[0]) for k, v in raw_components(t[None, :], self.half_life).items()}

        null = self._dataset_null(n)
        if null is not None:
            result["baseline_source"] = "dataset"
        elif t[-1] > t[0]:
            # No usable background: compare pattern scores with evenly
            # scattered times over the same span; leave the burst score as is.
            scattered = np.sort(self.rng.uniform(t[0], t[-1], size=(self._rows(n), n)), axis=1)
            null = raw_components(scattered, self.half_life)
            null["burst"] = np.zeros(len(scattered))
            result["baseline_source"] = "own span"
        baseline = ({k: float(np.percentile(v, BASELINE_PERCENTILE)) for k, v in null.items()}
                    if null is not None else dict.fromkeys(COMPONENTS, 0.0))

        def adjust(value, base):
            return 100.0 * np.clip((value - base) / max(100.0 - base, 1e-9), 0.0, 1.0)

        adjusted = {k: float(adjust(raw[k], baseline[k])) for k in COMPONENTS}
        best = max(COMPONENTS, key=lambda k: adjusted[k])
        result.update(raw=raw, baseline=baseline, adjusted=adjusted, sync=adjusted[best],
                      pattern=best if adjusted[best] > 0 else None)
        if result["baseline_source"] == "dataset":
            null_sync = np.max([adjust(null[k], baseline[k]) for k in COMPONENTS], axis=0)
            result["beats_random"] = float(100.0 * np.mean(null_sync < result["sync"]))
        return result


def group_sync(times, half_life: float = DEFAULT_HALF_LIFE, background=None) -> dict:
    """Synchrony of a group of timestamps; see SyncScorer.score."""
    return SyncScorer(background, half_life).score(times)


def nearest_sync(times: np.ndarray, half_life: float = DEFAULT_HALF_LIFE) -> np.ndarray:
    """Per post: synchrony with the nearest other post in the same list."""
    times = np.asarray(times, dtype=float)
    if len(times) < 2:
        return np.zeros(len(times))
    order = np.argsort(times, kind="stable")
    gaps = np.diff(times[order])
    nearest = np.minimum(np.concatenate([[np.inf], gaps]), np.concatenate([gaps, [np.inf]]))
    out = np.empty(len(times))
    out[order] = 100.0 * 0.5 ** (nearest / half_life)
    return out


def find_bursts(times: np.ndarray, bin_seconds: float, alpha: float = 0.001, max_bins: int = 20000) -> list[dict]:
    """Time windows with far more posts than the dataset's usual rate.

    The timeline is cut into bins; the usual rate is the median bin count
    (or the mean when most bins are empty). A bin is unusual when a Poisson
    process at the usual rate would reach its count with probability below
    alpha divided by the number of bins. Neighbouring unusual bins are merged.
    """
    times = np.sort(np.asarray(times, dtype=float))
    if len(times) < 5 or times[-1] == times[0]:
        return []
    span = times[-1] - times[0]
    bin_seconds = max(bin_seconds, span / max_bins)
    n_bins = int(span // bin_seconds) + 1
    counts = np.bincount(((times - times[0]) // bin_seconds).astype(np.int64), minlength=n_bins)
    usual = float(np.median(counts)) or float(counts.mean())
    hot = poisson.sf(counts - 1, usual) < alpha / n_bins
    bursts, k = [], 0
    while k < n_bins:
        if not hot[k]:
            k += 1
            continue
        end = k
        while end + 1 < n_bins and hot[end + 1]:
            end += 1
        n_posts = int(counts[k:end + 1].sum())
        bursts.append({"start": float(times[0] + k * bin_seconds),
                       "end": float(times[0] + (end + 1) * bin_seconds),
                       "posts": n_posts, "expected": round(usual * (end - k + 1), 1)})
        k = end + 1
    bursts.sort(key=lambda b: -b["posts"] / max(b["expected"], 0.1))
    return bursts


# ---------------------------------------------------------------- CLI

PATTERN_TEXT = {
    "burst": "posts are bunched close together in time",
    "regular": "posts arrive at near-constant intervals",
    "hourly": "posts land on the same minute of the hour",
    "daily": "posts land on the same time of day",
    None: "no timing pattern beyond chance",
}
BASELINE_TEXT = {
    "dataset": "  More synchronised than {beats_random:.1f}% of random groups of the same size from this dataset.",
    "own span": "  Nothing to compare bursts with, so burst is as measured; the pattern scores are "
                "compared with evenly scattered times.",
}


def _round(d: dict) -> dict:
    return {k: round(v, 1) if isinstance(v, float) else v for k, v in d.items()}


def _parser() -> argparse.ArgumentParser:
    parser, pair, data = pair_dataset_parser(
        "Temporal synchrony score: 100 = same instant, 0 = far apart with no pattern.",
        ("t1", "t2"), "score two timestamps", "score the timing of a dataset, or of selected posts within it")
    data.add_argument("--time-col", help="time column (guessed if omitted)")
    data.add_argument("--text-col")
    data.add_argument("--ids", help="comma-separated post ids: score this group against the rest of the dataset")
    for p in (pair, data):
        p.add_argument("--half-life", default="10m", help="time gap at which two posts score 50 (default 10m)")
    return parser


def _selected(ds: Dataset, ids: str) -> np.ndarray:
    """Positions of the posts whose ids are listed, comma-separated."""
    wanted = {s.strip() for s in ids.split(",") if s.strip()}
    chosen = np.array([i for i, post_id in enumerate(ds.ids) if post_id in wanted], dtype=np.int64)
    missing = wanted - {ds.ids[i] for i in chosen}
    if missing:
        raise ValueError(f"Ids not found in the dataset: {', '.join(sorted(missing)[:10])}")
    return chosen


def _json_report(ds: Dataset, half_life: float, group: dict, bursts: list[dict]) -> str:
    parts = ("raw", "baseline", "adjusted")
    return json.dumps({
        "posts": len(ds), "half_life_seconds": half_life,
        "first_time": to_iso(ds.times.min()), "last_time": to_iso(ds.times.max()),
        "group": {**_round({k: v for k, v in group.items() if k not in parts}),
                  **{k: _round(group[k]) for k in parts}},
        "bursts": [{**b, "start": to_iso(b["start"]), "end": to_iso(b["end"])} for b in bursts[:20]],
        "warnings": ds.warnings,
    }, indent=2)


def _print_group(group: dict, selected: int | None, n_posts: int) -> None:
    if selected is not None:
        print(f"\nSynchrony of {selected} selected posts: {group['sync']:.1f} / 100 - {PATTERN_TEXT[group['pattern']]}.")
    else:
        print(f"\nBackground timing of all {n_posts:,} posts. This is the dataset's normal level, not a sign of "
              f"coordination; a busy timeline scores high on burst. Use --ids to score a group against it.")
    if group["baseline_source"] in BASELINE_TEXT:
        print(BASELINE_TEXT[group["baseline_source"]].format(**group))
    print("  component   measured   chance level   score")
    for k in COMPONENTS:
        print(f"  {k:<10} {group['raw'][k]:9.1f} {group['baseline'][k]:14.1f} {group['adjusted'][k]:7.1f}")


def _print_bursts(bursts: list[dict]) -> None:
    if not bursts:
        print("\nNo unusually busy windows found.")
        return
    print(f"\nUnusually busy windows ({len(bursts)} found, strongest first):")
    for b in bursts[:10]:
        print(f"  {to_iso(b['start'])} to {to_iso(b['end'])}: {b['posts']} posts, about {b['expected']:g} expected")


def _write_scores(path: str, ds: Dataset, half_life: float) -> None:
    import pandas as pd
    pd.DataFrame({"id": ds.ids, "time": [to_iso(t) for t in ds.times],
                  "sync_with_nearest_post": nearest_sync(ds.times, half_life).round(1)}).to_csv(path, index=False)


def _dataset_command(args: argparse.Namespace, half_life: float) -> None:
    ds = load_dataset(args.path, args.text_col, args.time_col, max_rows=args.max_rows)
    chosen = _selected(ds, args.ids) if args.ids else None
    group = SyncScorer(ds.times, half_life).score(ds.times if chosen is None else ds.times[chosen])
    bursts = find_bursts(ds.times, half_life)
    if args.out:
        _write_scores(args.out, ds, half_life)
    if args.json:
        print(_json_report(ds, half_life, group, bursts))
        return
    for w in ds.warnings:
        print(f"note: {w}")
    print(f"{len(ds):,} posts from {to_iso(ds.times.min())} to {to_iso(ds.times.max())} "
          f"(column {ds.time_col!r}), half-life {format_duration(half_life)}.")
    _print_group(group, None if chosen is None else len(chosen), len(ds))
    _print_bursts(bursts)
    if args.out:
        print(f"\nPer-post scores written to {args.out}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    half_life = parse_duration(args.half_life)
    if args.command == "pair":
        print(f"{pair_sync(parse_time(args.t1), parse_time(args.t2), half_life):.1f}")
    else:
        _dataset_command(args, half_life)
    return 0


if __name__ == "__main__":
    sys.exit(run_cli(main))