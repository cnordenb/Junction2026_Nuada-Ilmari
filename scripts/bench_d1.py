"""Benchmark the d1 decision-model prompts on labelled data.

Every prompt variant is asked about every example, and scored on how well its
probability separates bots from people:

    AUC        chance a random bot gets a higher P than a random person (0.5 = coin flip)
    precision  share of examples with P >= 0.5 that are really bots
    recall     share of bots with P >= 0.5
    FPR        share of people with P >= 0.5 (people we would wrongly flag)

Datasets
    twitter    airt-ml/twitter-human-bots on Hugging Face (CC-BY-SA-3.0): real
               accounts labelled human or bot; we use the username and bio.
    signups    our forged signup logs (data/signups/demo_signups.csv): email and
               username, abuse campaigns against ordinary people and traps.

Needs a running llama.cpp server with d1 (D1_URL, e.g. http://llm:8080).
On the VPS:  docker compose ... exec -T app python - < scripts/bench_d1.py > data/bench/d1_benchmark.json

Usage:
    D1_URL=http://127.0.0.1:8080 python scripts/bench_d1.py --n 300
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

_here = Path(globals().get("__file__", "")).resolve().parent.parent
ROOT = Path(os.environ["APP_ROOT"]) if os.environ.get("APP_ROOT") else (_here if (_here / "data").is_dir() else Path("/app"))
TWITTER_CSV = ("https://huggingface.co/datasets/airt-ml/twitter-human-bots/resolve/main/"
               "twitter_human_bots_dataset.csv")

# Prompt variants. "prod_*" are the questions Sargas uses in production.
EMAIL_VARIANTS = {
    "prod_email_machine": {"type": "noul", "instructions": (
        "Does the part of the email before the @ look randomly generated or machine-made (random letters, user plus "
        "digits, name plus 4 digits, dots or +tags to fake a new address)?")},
    "email_bot_made": {"type": "noul", "instructions": "Was this email address most likely created by a bot to open many accounts?"},
    "email_real_person": {"type": "noul", "instructions": "Does this look like a real person's everyday email address?",
                          "invert": True},
}
NAME_VARIANTS = {
    "prod_name_not_pet": {"type": "noul", "instructions": (
        "Is the horse name not a playful pet name, but a username, a person's full name, an ID or spam?")},
    "name_machine": {"type": "noul", "instructions": (
        "Does the username look randomly generated or machine-made (random letters, a word plus many digits, an ID)?")},
    "account_bot": {"type": "noul", "instructions": "Is this account run by a bot or script rather than a person?"},
    "bio_spam": {"type": "noul", "instructions": "Does the profile text look like spam, advertising or automatically generated content?"},
}


def ask(url: str, state: dict, questions: dict, timeout: float = 20) -> dict:
    q = {k: {kk: vv for kk, vv in v.items() if kk != "invert"} for k, v in questions.items()}
    req = urllib.request.Request(url.rstrip("/") + "/v1/systemone", data=json.dumps({"state": state, "questions": q}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        answers = json.loads(res.read())["answers"]
    return {k: (1 - answers[k]["noul"]) if questions[k].get("invert") else answers[k]["noul"] for k in questions}


def metrics(y: np.ndarray, p: np.ndarray, cut: float = 0.5) -> dict:
    pos, neg = p[y], p[~y]
    ranks = pd.Series(p).rank().to_numpy()
    auc = float((ranks[y].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))) if len(pos) and len(neg) else None
    flag = p >= cut
    tp, fp, fn = int((flag & y).sum()), int((flag & ~y).sum()), int((~flag & y).sum())
    return {"auc": round(auc, 3) if auc is not None else None,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "fpr": round(fp / max(len(neg), 1), 3), "n_bots": int(len(pos)), "n_people": int(len(neg)),
            "mean_p_bots": round(float(pos.mean()), 3), "mean_p_people": round(float(neg.mean()), 3)}


def twitter_sample(n: int, rng: random.Random) -> list[tuple[bool, dict]]:
    raw = urllib.request.urlopen(TWITTER_CSV, timeout=120).read()
    df = pd.read_csv(io.BytesIO(raw), usecols=["screen_name", "description", "account_type"]).fillna("")
    out = []
    for label in ("bot", "human"):
        rows = df[df["account_type"] == label]
        for _, r in rows.sample(n=min(n, len(rows)), random_state=rng.randrange(10**6)).iterrows():
            out.append((label == "bot", {"username": str(r["screen_name"]), "bio": str(r["description"])[:280]}))
    return out


def signup_sample(n: int, rng: random.Random) -> list[tuple[bool, dict]]:
    df = pd.read_csv(ROOT / "data" / "signups" / "demo_signups.csv", dtype=str, keep_default_na=False)
    out = []
    for is_bot in (True, False):
        rows = df[(df["label"] != "organic") == is_bot]
        for _, r in rows.sample(n=min(n, len(rows)), random_state=rng.randrange(10**6)).iterrows():
            out.append((is_bot, {"email": r["email"], "username": r["username"], "group": r["label"] if is_bot else r["note"]}))
    return out


def run(url: str, examples: list[tuple[bool, dict]], variants: dict, state_keys: list[str]) -> tuple[dict, float]:
    y, cols = [], {k: [] for k in variants}
    t0 = time.time()
    for is_bot, ex in examples:
        state = {k: ex[k] for k in state_keys}
        ans = ask(url, state, variants)
        y.append(is_bot)
        for k in variants:
            cols[k].append(ans[k])
    y = np.array(y)
    raw = {"y": y, **{k: np.array(v) for k, v in cols.items()}}
    return {k: metrics(y, np.array(v)) for k, v in cols.items()}, (time.time() - t0) / max(len(examples), 1), raw


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=int(os.environ.get("BENCH_N", "200")), help="examples per class per dataset")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args([a for a in sys.argv[1:] if a != "-"])
    url = os.environ.get("D1_URL")
    if not url:
        print("Set D1_URL to the llama.cpp server running d1.", file=sys.stderr)
        return 2
    rng = random.Random(args.seed)
    report = {"model": "LiquidAI/d1-omni-600M-GGUF:Q8_0", "n_per_class": args.n, "seed": args.seed, "datasets": {}}

    tw = twitter_sample(args.n, rng)
    res, sec, raw_tw = run(url, tw, {k: v for k, v in NAME_VARIANTS.items()}, ["username", "bio"])
    report["datasets"]["twitter"] = {"source": "airt-ml/twitter-human-bots (CC-BY-SA-3.0)", "state": "username + bio",
                                     "seconds_per_example": round(sec, 3), "variants": res}

    su = signup_sample(args.n, rng)
    both = {**EMAIL_VARIANTS, **NAME_VARIANTS}
    res, sec, raw_su = run(url, su, both, ["email", "username"])
    report["datasets"]["signups"] = {"source": "forged signup logs (our own)", "state": "email + username",
                                     "seconds_per_example": round(sec, 3), "variants": res}
    # Mixed: both datasets together, for the variants asked on both.
    y = np.concatenate([raw_tw["y"], raw_su["y"]])
    report["datasets"]["mixed"] = {"source": "twitter + signups, equal parts", "state": "both",
                                   "variants": {k: metrics(y, np.concatenate([raw_tw[k], raw_su[k]])) for k in NAME_VARIANTS}}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
