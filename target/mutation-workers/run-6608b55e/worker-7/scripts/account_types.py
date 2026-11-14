"""Account behaviour types, for datasets that say which account wrote each post.

Each account gets four signals, 0-100, and a type derived from them. The
type describes how the account behaves in this dataset. It is not a verdict
on who runs it: scheduling tools, news feeds and people with routines can
all look automated.

Signals
    schedule    posts follow a timer, the same minute of the hour, or the
                same time of day, far beyond chance (needs 8+ posts)
    no_pause    active around the clock: no daily quiet period (needs 30+
                posts over 3+ days). People sleep; a longest daily gap of 8
                hours or more scores 0, 2 hours or less scores 100.
    repetition  the account's own posts repeat each other: mean pairwise
                text similarity (needs 3+ posts long enough to compare)
    swarm       share of the account's posts that sit in flagged groups

Types, first match wins
    automated          schedule or no_pause is 50+
    repetitive         repetition is at or above the similarity threshold
    swarm_participant  3+ posts, and half or more are in flagged groups
    single_purpose     1-2 posts, all of them in flagged groups
    occasional         some posts in flagged groups, less than half
    no_signals         3+ posts and none of the above
    too_few            1-2 posts, none flagged: nothing to judge

This module is used by detect_swarm.py; it has no command line of its own.
"""
from __future__ import annotations

import numpy as np

from similarity_score import SimilarityIndex
from swarm_common import confusion, format_duration, is_positive_label, to_iso
from sync_score import MIN_PATTERN_POSTS, SyncScorer

MIN_POSTS = 3                 # fewer posts than this: no behaviour to judge
SIGNAL_ON = 50.0              # schedule / no_pause / swarm count as present from here
NO_PAUSE_MIN_POSTS = 30
NO_PAUSE_MIN_DAYS = 3
QUIET_HUMAN_HOURS, QUIET_BOT_HOURS = 8.0, 2.0
MAX_REPORTED = 500            # accounts listed in the report (all are counted)
MAX_TIMES = 400               # post times per account sent along for charts

TYPE_ORDER = ["automated", "repetitive", "swarm_participant", "single_purpose", "occasional",
              "no_signals", "too_few"]
FLAGGED_TYPES = set(TYPE_ORDER[:4])
TYPE_LABEL = {
    "automated": "Automated-looking",
    "repetitive": "Repetitive",
    "swarm_participant": "Swarm participant",
    "single_purpose": "Single-purpose",
    "occasional": "Occasional participant",
    "no_signals": "No signals",
    "too_few": "Too few posts to judge",
}
TYPE_MEANING = {
    "automated": "Posts on a schedule or around the clock, the way a script or scheduling tool does.",
    "repetitive": "Keeps posting near-copies of its own posts.",
    "swarm_participant": "At least half of its posts are in flagged groups.",
    "single_purpose": "Has only one or two posts, and all of them are in flagged groups.",
    "occasional": "A few of its posts are in flagged groups; most are not.",
    "no_signals": "Enough posts to judge, and nothing unusual.",
    "too_few": "One or two posts, none flagged. Nothing to judge.",
}
PATTERN_PHRASE = {"regular": "at near-constant intervals", "hourly": "at the same minute of the hour",
                  "daily": "at the same time of day"}


def longest_daily_quiet_hours(times: np.ndarray) -> float:
    """Longest stretch of the 24-hour clock in which the account never posted."""
    clock = np.sort(np.asarray(times, dtype=float) % 86400.0)
    if len(clock) < 2:
        return 24.0
    gaps = np.diff(np.concatenate([clock, [clock[0] + 86400.0]]))
    return float(gaps.max() / 3600.0)


def classify(n_posts: int, flagged_posts: int, signals: dict, repetition_threshold: float) -> str:
    if max(signals["schedule"], signals["no_pause"]) >= SIGNAL_ON:
        return "automated"
    if signals["repetition"] >= repetition_threshold:
        return "repetitive"
    if n_posts < MIN_POSTS:
        return _classify_few(n_posts, flagged_posts)
    if signals["swarm"] >= SIGNAL_ON:
        return "swarm_participant"
    return "occasional" if flagged_posts else "no_signals"


def _classify_few(n_posts: int, flagged_posts: int) -> str:
    """Accounts with one or two posts: judged only through the groups they post in."""
    if flagged_posts == n_posts:
        return "single_purpose"
    return "occasional" if flagged_posts else "too_few"


def _span_days(t: np.ndarray) -> float:
    return (t[-1] - t[0]) / 86400.0


def _no_pause(t: np.ndarray) -> tuple[float, float | None]:
    """(signal, longest daily quiet period in hours); (0, None) with too little to go on."""
    if len(t) < NO_PAUSE_MIN_POSTS or _span_days(t) < NO_PAUSE_MIN_DAYS:
        return 0.0, None
    quiet = longest_daily_quiet_hours(t)
    signal = np.clip((QUIET_HUMAN_HOURS - quiet) / (QUIET_HUMAN_HOURS - QUIET_BOT_HOURS), 0.0, 1.0)
    return 100.0 * float(signal), quiet


def _schedule_reason(pattern: str, t: np.ndarray, signal: float) -> str:
    every = f" (about every {format_duration(float(np.diff(t).mean()))})" if pattern == "regular" else ""
    return f"Posts {PATTERN_PHRASE[pattern]}{every}: schedule signal {signal:.0f} across {len(t)} posts."


def _groups_reason(flagged_posts: int, n: int, group_ids: list[int]) -> str:
    plural = "s" if len(group_ids) > 1 else ""
    return f"{flagged_posts} of its {n} posts are in flagged group{plural} {', '.join(map(str, group_ids))}."


class _Profiler:
    """Works out one account's signals, type and reasons from its posts."""

    def __init__(self, times: np.ndarray, index: SimilarityIndex, inverse: np.ndarray,
                 flagged_group: np.ndarray, scorer: SyncScorer, threshold: float, min_chars: int):
        self.times, self.index, self.inverse = times, index, inverse
        self.flagged_group, self.scorer, self.threshold = flagged_group, scorer, threshold
        self.long_enough = index.lengths[inverse] >= min_chars
        self.scratch = np.zeros(len(index.unique), dtype=np.int64)

    def schedule(self, t: np.ndarray) -> tuple[float, str | None]:
        """(signal, name of the timing pattern behind it)."""
        if len(t) < MIN_PATTERN_POSTS:
            return 0.0, None
        adjusted = self.scorer.score(t)["adjusted"]
        best = max(PATTERN_PHRASE, key=lambda k: adjusted[k])
        return adjusted[best], best if adjusted[best] > 0 else None

    def repetition(self, posts: np.ndarray) -> tuple[float, int]:
        """(mean similarity among the account's own posts, how many were long enough to compare)."""
        comparable = posts[self.long_enough[posts]]
        if len(comparable) < MIN_POSTS:
            return 0.0, len(comparable)
        members, counts = np.unique(self.inverse[comparable], return_counts=True)
        self.scratch[members] = counts
        score = self.index.cohesion(members, self.scratch)[0]
        self.scratch[members] = 0
        return score, len(comparable)

    def row(self, name: str, posts: np.ndarray) -> dict:
        posts = posts[np.argsort(self.times[posts], kind="stable")]
        t, n = self.times[posts], len(posts)
        group_ids = sorted({int(g) for g in self.flagged_group[posts] if g > 0})
        flagged_posts = int((self.flagged_group[posts] > 0).sum())
        schedule, pattern = self.schedule(t)
        no_pause, quiet = _no_pause(t)
        repetition, n_comparable = self.repetition(posts)
        signals = {"schedule": schedule, "no_pause": no_pause, "repetition": repetition,
                   "swarm": 100.0 * flagged_posts / n}
        kind = classify(n, flagged_posts, signals, self.threshold)
        found = [
            (schedule >= SIGNAL_ON, lambda: _schedule_reason(pattern, t, schedule)),
            (no_pause >= SIGNAL_ON, lambda: f"Active around the clock: its longest daily quiet period is "
                                            f"{quiet:.1f} hours across {_span_days(t):.0f} days."),
            (repetition >= self.threshold, lambda: f"Its own posts repeat each other: average similarity "
                                                   f"{repetition:.0f} across {n_comparable} posts."),
            (flagged_posts > 0, lambda: _groups_reason(flagged_posts, n, group_ids)),
        ]
        return {
            "id": str(name), "type": kind, "posts": n, "flagged_posts": flagged_posts, "groups": group_ids,
            "signals": {k: round(float(v), 1) for k, v in signals.items()},
            "pattern": pattern, "quiet_hours": None if quiet is None else round(quiet, 1),
            "first_time": to_iso(t[0]), "last_time": to_iso(t[-1]),
            "reasons": [make() for present, make in found if present] or [TYPE_MEANING[kind]],
            "_posts": posts,
        }


_RANK = {k: i for i, k in enumerate(TYPE_ORDER)}


def _sort_key(row: dict) -> tuple:
    return _RANK[row["type"]], -max(row["signals"].values()), -row["posts"], row["id"]


def _evaluate(rows: list[dict], truth: np.ndarray | None) -> dict | None:
    """Account-level accuracy: an account is real when most of its posts are labelled as swarm."""
    if truth is None:
        return None
    flagged = np.array([r["type"] in FLAGGED_TYPES for r in rows], dtype=bool)
    real = np.array([truth[r["_posts"]].mean() >= 0.5 for r in rows], dtype=bool)
    return confusion(flagged, real)


def profile_accounts(accounts: list[str], times: np.ndarray, index: SimilarityIndex, inverse: np.ndarray,
                     flagged_group: np.ndarray, scorer: SyncScorer, threshold: float, min_chars: int,
                     make_post, labels: list[str] | None = None, sample: int = 5) -> dict:
    """Profile every account. `flagged_group[p]` is the id of the flagged
    group post p belongs to, or 0. `make_post(p)` builds the post record used
    for examples. Returns a JSON-serialisable report section."""
    names, account_of = np.unique(np.asarray(accounts, dtype=object), return_inverse=True)
    order = np.argsort(account_of, kind="stable")
    bounds = np.searchsorted(account_of[order], np.arange(len(names) + 1))
    profiler = _Profiler(times, index, inverse, flagged_group, scorer, threshold, min_chars)
    rows = [profiler.row(name, order[bounds[a]:bounds[a + 1]])
            for a, name in enumerate(names) if name]      # "" = no account recorded
    rows.sort(key=_sort_key)
    type_counts = {k: sum(r["type"] == k for r in rows) for k in TYPE_ORDER}
    truth = None if labels is None else np.array([is_positive_label(l) for l in labels])
    evaluation = _evaluate(rows, truth)

    # Examples and chart data only for the accounts that are listed.
    for k, r in enumerate(rows):
        posts = r.pop("_posts")
        if k < MAX_REPORTED:
            flagged_first = posts[np.argsort(flagged_group[posts] == 0, kind="stable")]
            r["sample_posts"] = [make_post(p) for p in flagged_first[:sample]]
            r["times"] = [int(x) for x in times[posts][:MAX_TIMES]]

    return {
        "n_accounts": len(rows), "posts_without_account": sum(1 for a in accounts if not a),
        "flagged_accounts": sum(type_counts[k] for k in FLAGGED_TYPES),
        "type_counts": type_counts,
        "types": [{"key": k, "label": TYPE_LABEL[k], "meaning": TYPE_MEANING[k], "flagged": k in FLAGGED_TYPES}
                  for k in TYPE_ORDER],
        "accounts": rows[:MAX_REPORTED], "accounts_omitted": max(0, len(rows) - MAX_REPORTED),
        "evaluation": evaluation,
    }