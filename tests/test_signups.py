"""Tests for the free-tier signup guard: helpers, the detector on the demo
stream, and the dashboard endpoints.

Run from the repository root:  python -m pytest
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from signup_guard import (Signups, analyse, canonical_inbox, is_automation, load_signups,  # noqa: E402
                          signup_signals, template)

DEMO = ROOT / "data" / "signups" / "demo_signups.csv"


# ---------------------------------------------------------------- helpers

def test_gmail_dots_and_plus_tags_reach_one_inbox():
    assert canonical_inbox("J.o.h.n.Doe+promo1@gmail.com") == "johndoe@gmail.com"
    assert canonical_inbox("johndoe@googlemail.com") == "johndoe@gmail.com"


def test_dots_matter_outside_gmail():
    assert canonical_inbox("john.doe@outlook.com") != canonical_inbox("johndoe@outlook.com")
    assert canonical_inbox("john+x@outlook.com") == "john@outlook.com"


def test_template_keeps_digit_counts():
    assert template("user48213") == "a9{5}"
    assert template("anna.virtanen") == "a.a"


def test_automation_browsers_are_recognised():
    assert is_automation("Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/139.0.0.0 Safari/537.36")
    assert is_automation("python-requests/2.32")
    assert not is_automation("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0.0.0 Safari/537.36")


def _frame(rows: list[dict]) -> pd.DataFrame:
    base = {"id": "", "time": 0.0, "email": "", "username": "", "ip": "", "asn": "", "asn_org": "",
            "user_agent": "", "device_id": ""}
    return pd.DataFrame([{**base, **r, "id": str(i)} for i, r in enumerate(rows)])


def test_signals_explain_themselves():
    frame = _frame([{"email": "user1@mailinator.com", "asn": "14061"},
                    {"email": "j.doe@gmail.com"}, {"email": "jdoe+2@gmail.com"},
                    {"email": "ok@example.org"}])
    signals = signup_signals(frame)
    assert {s["signal"] for s in signals[0]} == {"disposable", "hosting"}
    assert [s["signal"] for s in signals[1]] == ["inbox_reuse"]
    assert signals[3] == []
    assert all(s["reason"] for sig in signals for s in sig)


# ---------------------------------------------------------------- detector on the demo stream

@pytest.fixture(scope="module")
def demo_report():
    su = load_signups(DEMO, "label")
    su.frame["note"] = pd.read_csv(DEMO, dtype=str, keep_default_na=False)["note"].tolist()
    return analyse(su)


def _group(report, name):
    return next(g for g in report["evaluation"]["by_group"] if g["group"] == name)


def test_demo_blocks_no_real_people(demo_report):
    assert demo_report["evaluation"]["block"]["fp"] == 0


def test_demo_catches_planted_campaigns(demo_report):
    for name in ("abuse_tempmail_burst", "abuse_alias_farm", "abuse_proxy_farm", "abuse_daily_drip"):
        g = _group(demo_report, name)
        assert g["blocked"] >= 0.9 * g["signups"], name


def test_known_miss_stays_missed(demo_report):
    # If this starts passing, the generator or detector changed: update the docs.
    assert _group(demo_report, "abuse_slow_humanlike")["blocked"] == 0


def test_organisations_go_to_review_not_block(demo_report):
    for name in ("trap_classroom", "trap_team_onboarding"):
        g = _group(demo_report, name)
        assert g["blocked"] == 0 and g["review"] == g["signups"], name


def test_every_group_has_reasons(demo_report):
    for c in demo_report["clusters"]:
        assert c["why"] and c["timing"]
        assert c["action"] in {"block", "review", "allow"}


def test_device_farm_is_grouped_without_labels():
    t0 = 1_800_000_000.0
    rows = [{"time": t0 + i * 3600 * 7.3, "email": f"person{i}@gmail.com", "device_id": f"d{i}",
             "user_agent": f"UA {i % 40}"} for i in range(400)]
    rows += [{"time": t0 + 1000 + i * 30, "email": f"x{i}abc{i * 7}@outlook.com", "device_id": "farm",
              "user_agent": "UA farm"} for i in range(8)]
    frame = _frame(rows)
    report = analyse(Signups(frame, {}, len(frame)))
    actions = np.array(report["actions"])
    assert (actions[-8:] == "block").all()
    assert (actions[:400] == "allow").all()


# ---------------------------------------------------------------- dashboard

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from dashboard.app import app
    return TestClient(app)


def test_signup_page_and_lists(client):
    assert client.get("/signups").status_code == 200
    names = [d["name"] for d in client.get("/api/signups/datasets").json()]
    assert "demo_signups.csv" in names and "evaluation.json" not in names


def test_signup_analyze_endpoint(client):
    r = client.post("/api/signups/analyze", json={"dataset_id": "signups:demo_signups.csv", "label_col": "label"})
    assert r.status_code == 200
    body = r.json()
    assert "actions" not in body
    assert body["evaluation"]["block"]["fp"] == 0


def test_signup_analyze_rejects_paths(client):
    r = client.post("/api/signups/analyze", json={"dataset_id": "signups:../../etc/passwd"})
    assert r.status_code == 404


def test_live_farm_gets_blocked_and_sessions_are_separate(client):
    farmer, other = "a" * 32, "b" * 32
    last = None
    for i in range(6):
        last = client.post("/api/signups/live", json={"session": farmer, "email": f"user{4821 + i}@mailinator.com",
                                                      "username": f"user{4821 + i}", "device_id": "feedbeef"}).json()
    assert last["latest"]["action"] == "block"
    assert last["latest"]["reasons"]
    assert any(g["live_members"] >= 5 for g in last["groups"])
    mine = client.post("/api/signups/live", json={"session": other, "email": "anna.virtanen@example.fi",
                                                  "device_id": "0123456789abcdef"}).json()
    assert [s["email"] for s in mine["session"]] == ["anna.virtanen@example.fi"]
    assert mine["latest"]["action"] == "allow"
    client.delete(f"/api/signups/live?session={farmer}")
    client.delete(f"/api/signups/live?session={other}")
