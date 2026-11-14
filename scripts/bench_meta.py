"""Which judges better: Sargas's algorithm, d1 over Sargas's evidence, or a blend?

Scores the forged signup log with the algorithm, then asks d1 (d1_meta.py) about
a balanced sample of bots and people, and compares on the same examples:

    algorithm   Sargas's bot score / 100
    d1_bot      d1's P(bot) given all the evidence (not the score)
    d1_kind     d1's probability that the signup is one of the three bot kinds
    blend       mean of algorithm and d1_bot

On the VPS:  docker compose ... exec -T -e APP_ROOT=/app app python - < scripts/bench_meta.py
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

_here = Path(globals().get("__file__", "")).resolve().parent.parent
ROOT = Path(os.environ["APP_ROOT"]) if os.environ.get("APP_ROOT") else (_here if (_here / "data").is_dir() else Path("/app"))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd  # noqa: E402

import d1_meta  # noqa: E402
import lfm_judge  # noqa: E402
from signup_guard import analyse, load_signups  # noqa: E402


def metrics(y, p, cut):
    y, p = np.asarray(y), np.asarray(p, dtype=float)
    pos, neg = p[y], p[~y]
    ranks = pd.Series(p).rank().to_numpy()
    auc = (ranks[y].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))
    flag = p >= cut
    tp, fp, fn = int((flag & y).sum()), int((flag & ~y).sum()), int((~flag & y).sum())
    return {"auc": round(float(auc), 3), "cut": cut,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3), "fpr": round(fp / len(neg), 3), "people_flagged": fp}


def main() -> int:
    url = os.environ.get("D1_URL")
    lfm_url = os.environ.get("LFM_URL")
    skip_d1 = os.environ.get("SKIP_D1") == "1"
    n = int(os.environ.get("BENCH_N", "60"))
    if not url:
        print("Set D1_URL.", file=sys.stderr)
        return 2
    path = ROOT / "data" / "signups" / "demo_signups.csv"
    su = load_signups(path, "label")
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    rep = analyse(su, per_row=True, sample=0)
    groups = {c["id"]: c for c in rep["clusters"]}
    rng = random.Random(7)
    labels = raw["label"].tolist()
    notes = raw["note"].tolist()
    bots = [i for i, l in enumerate(labels) if l != "organic"]
    # People: half ordinary, half the hard innocent look-alikes (traps).
    traps = [i for i, l in enumerate(labels) if l == "organic" and notes[i] != "background"]
    plain = [i for i, l in enumerate(labels) if l == "organic" and notes[i] == "background"]
    idx = rng.sample(bots, n) + rng.sample(traps, n // 2) + rng.sample(plain, n - n // 2)
    y, alg, d1b, d1k, d1r, kinds, groups_of, lfm, lfm_kinds = [], [], [], [], [], [], [], [], []
    t0 = time.time()
    for i in idx:
        g = groups.get(rep["cluster_of"][i])
        state = d1_meta.evidence_state({"email": su.frame.at[i, "email"], "username": su.frame.at[i, "username"]},
                                       rep["score_parts"][i], g)
        a = {"p_bot": 0.5, "p_bot_kind": 0.5, "risk": 0.5, "kind": "-"} if skip_d1 else d1_meta.ask(url, state)
        if lfm_url:
            j = lfm_judge.judge(lfm_url, lfm_judge.evidence_state(
                {"email": su.frame.at[i, "email"], "username": su.frame.at[i, "username"]}, rep["score_parts"][i], g))
            lfm.append(j["p_bot"]); lfm_kinds.append(j["kind"])
        y.append(labels[i] != "organic")
        alg.append(rep["score"][i] / 100)
        d1b.append(a["p_bot"]); d1k.append(a["p_bot_kind"]); d1r.append(a["risk"]); kinds.append(a["kind"])
        groups_of.append(labels[i] if labels[i] != "organic" else notes[i])
    sec = (time.time() - t0) / len(idx)
    y = np.array(y)
    blend = (np.array(alg) + np.array(d1b)) / 2
    out = {"examples": len(idx), "bots": int(y.sum()), "people": int((~y).sum()),
           "people_mix": "half ordinary signups, half traps (class, company, families, VPN, newsletter rush)",
           "seconds_per_example": round(sec, 2),
           "judges": {"algorithm (score >= 60)": metrics(y, alg, 0.6), "d1_bot (P >= 0.5)": metrics(y, d1b, 0.5),
                      "d1_kind (P >= 0.5)": metrics(y, d1k, 0.5), "d1_risk (>= 0.5)": metrics(y, d1r, 0.5),
                      "blend (>= 0.55)": metrics(y, blend, 0.55),
                      **({"lfm3 (verdict >= probably_bot)": metrics(y, lfm, 0.75),
                          "blend algorithm + lfm3 (>= 0.6)": metrics(y, (np.array(alg) + np.array(lfm)) / 2, 0.6)} if lfm else {})},
           "by_group": {}}
    for gname in sorted(set(groups_of)):
        m = [k for k, g in enumerate(groups_of) if g == gname]
        out["by_group"][gname] = {"n": len(m), "algorithm_mean": round(float(np.mean([alg[k] for k in m])), 2),
                                  "d1_bot_mean": round(float(np.mean([d1b[k] for k in m])), 2),
                                  **({"lfm3_mean": round(float(np.mean([lfm[k] for k in m])), 2),
                                      "lfm3_top_kind": max(set(lfm_kinds[k] for k in m), key=lambda kk: sum(lfm_kinds[j] == kk for j in m))} if lfm else {}),
                                  "d1_top_kind": max(set(kinds[k] for k in m), key=lambda kk: sum(kinds[j] == kk for j in m))}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
