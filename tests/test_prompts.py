"""Tests for the d1 decision-model prompts and their plumbing.

The model itself is benchmarked by scripts/bench_d1.py (results in
data/bench/d1_benchmark.json). These tests run without the model; the last one
runs a small labelled regression set when D1_URL points at a live server.

Run from the repository root:  python -m pytest
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from signup_guard import FACTORS, d1_factor  # noqa: E402


def test_production_prompts_are_valid_d1_questions():
    from dashboard.live import D1_QUESTIONS
    assert D1_QUESTIONS, "no production prompts"
    for name, q in D1_QUESTIONS.items():
        assert q["type"] in {"noul", "choice", "score"}, name
        assert len(q["instructions"]) > 20 and q["instructions"].endswith("?"), name


def test_benchmark_variants_include_the_production_prompt():
    import bench_d1
    from dashboard.live import D1_QUESTIONS
    assert D1_QUESTIONS["email_machine"]["instructions"] == bench_d1.EMAIL_VARIANTS["prod_email_machine"]["instructions"]


def test_d1_factor_counts_only_above_one_half():
    assert d1_factor(json.dumps({"email_machine": 0.4})) is None
    x, reason = d1_factor(json.dumps({"email_machine": 0.9}))
    assert abs(x - 0.8) < 1e-9 and "0.90" in reason
    assert d1_factor("") is None and d1_factor("not json") is None


def test_d1_weight_is_modest():
    weight = next(w for k, _, w, _ in FACTORS if k == "d1_model")
    assert 0 < weight <= 1.5, "d1 alone must never be able to block a signup"


def test_ask_d1_fails_open_when_model_is_down(monkeypatch):
    import dashboard.live as live
    monkeypatch.setattr(live, "D1_URL", "http://127.0.0.1:9")   # nothing listens here
    monkeypatch.setattr(live, "D1_TIMEOUT", 0.5)
    assert live.ask_d1("user48213@mailinator.com", "x") == ""


# A small fixed regression set: if a prompt change makes these worse, the test fails.
REGRESSION = [
    (False, "aino.virtanen@gmail.com"), (False, "laura.koski@studio-laura.fi"), (False, "mikko92@hotmail.com"),
    (False, "j.smith@proton.me"), (False, "anna.korhonen@example.fi"), (False, "tomas.novak@seznam.cz"),
    (True, "user48213@mailinator.com"), (True, "xkq7zz91@yopmail.com"), (True, "j.o.hns.mithdeals+trial53@gmail.com"),
    (True, "paulkarlsson2948@outlook.com"), (True, "user77123@guerrillamail.com"), (True, "qwpz8811kk@example.net"),
]


@pytest.mark.skipif(not os.environ.get("D1_URL"), reason="needs a live d1 server (set D1_URL)")
def test_email_prompt_regression_set():
    from dashboard.live import D1_QUESTIONS
    url = os.environ["D1_URL"].rstrip("/") + "/v1/systemone"
    bots, people = [], []
    for is_bot, email in REGRESSION:
        body = json.dumps({"state": {"email": email}, "questions": {"q": D1_QUESTIONS["email_machine"]}}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        p = json.loads(urllib.request.urlopen(req, timeout=20).read())["answers"]["q"]["noul"]
        (bots if is_bot else people).append(p)
    pairs = [(b > h) + 0.5 * (b == h) for b in bots for h in people]
    auc = sum(pairs) / len(pairs)
    assert auc >= 0.7, f"email prompt AUC fell to {auc:.2f}"
