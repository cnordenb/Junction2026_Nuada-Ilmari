"""Measure the signup detector on many simulated signup streams.

The detector was designed against one stream (seed 7). This script checks it
on other random streams (seeds 1-5) and on "hard" streams whose attackers use
tricks the detector was not tuned on, and writes the results to
data/signups/evaluation.json for the dashboard's accuracy page.

Usage:
    python scripts/eval_signups.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402

from signup_guard import analyse, load_signups, score_quality  # noqa: E402
from swarm_common import is_positive_label  # noqa: E402

spec = importlib.util.spec_from_file_location("make_signup_data", ROOT / "data" / "make_signup_data.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

SEEDS = [1, 2, 3, 4, 5]
OUT = ROOT / "data" / "signups" / "evaluation.json"


def run(seed: int, hard: bool) -> dict:
    rows = gen.generate(seed, hard=hard)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "s.csv"
        import csv
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=gen.COLUMNS)
            w.writeheader()
            w.writerows(rows)
        su = load_signups(path, "label")
    su.frame["note"] = [r["note"] for r in rows]
    report = analyse(su, per_row=True)
    ev = report["evaluation"]
    return {"seed": seed, "hard": hard, "block": ev["block"], "block_or_review": ev["block_or_review"],
            "by_group": ev["by_group"], "truth": [is_positive_label(l) for l in su.labels],
            "score": report["score"]}


def total(results: list[dict], key: str) -> dict:
    tp = sum(r[key]["tp"] for r in results)
    fp = sum(r[key]["fp"] for r in results)
    fn = sum(r[key]["fn"] for r in results)
    tn = sum(r[key]["tn"] for r in results)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(100 * tp / (tp + fp), 1) if tp + fp else None,
            "recall": round(100 * tp / (tp + fn), 1) if tp + fn else None,
            "false_positive_rate": round(100 * fp / (fp + tn), 2) if fp + tn else None}


def groups(results: list[dict]) -> list[dict]:
    acc: dict[str, dict] = {}
    for r in results:
        for g in r["by_group"]:
            a = acc.setdefault(g["group"], {"group": g["group"], "abusive": g["abusive"], "signups": 0,
                                            "blocked": 0, "review": 0})
            for k in ("signups", "blocked", "review"):
                a[k] += g[k]
            a["score_sum"] = a.get("score_sum", 0) + g.get("mean_score", 0) * g["signups"]
    for a in acc.values():
        a["mean_score"] = round(a.pop("score_sum", 0) / a["signups"], 1) if a["signups"] else None
    return sorted(acc.values(), key=lambda g: (not g["abusive"], g["group"]))


def main() -> int:
    summary = {}
    for hard in (False, True):
        results = [run(s, hard) for s in SEEDS]
        name = "hard" if hard else "standard"
        summary[name] = {"seeds": SEEDS, "block": total(results, "block"),
                         "block_or_review": total(results, "block_or_review"), "by_group": groups(results),
                         "score": score_quality(np.concatenate([np.array(r["truth"]) for r in results]),
                                                np.concatenate([np.array(r["score"], dtype=float) for r in results]))}
        b, br = summary[name]["block"], summary[name]["block_or_review"]
        print(f"\n== {name} streams, seeds {SEEDS} ==")
        print(f"block:           precision {b['precision']}%  recall {b['recall']}%  FPR {b['false_positive_rate']}%  "
              f"(tp {b['tp']}, fp {b['fp']}, fn {b['fn']}, tn {b['tn']})")
        print(f"block or review: precision {br['precision']}%  recall {br['recall']}%  FPR {br['false_positive_rate']}%")
        sq = summary[name]["score"]
        print(f"bot score: AUC {sq['auc']}  (bots {sq['bots_total']}, people {sq['people_total']})")
        for c in sq["cutoffs"]:
            print(f"  score >= {c['cut']:>2}: precision {c['precision']}%  recall {c['recall']}%  FPR {c['false_positive_rate']}%")
        print(f"{'group':<26}{'signups':>8}{'blocked':>9}{'review':>8}{'mean score':>12}")
        for g in summary[name]["by_group"]:
            print(f"{g['group']:<26}{g['signups']:>8}{g['blocked']:>9}{g['review']:>8}{g['mean_score']:>12}")
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
