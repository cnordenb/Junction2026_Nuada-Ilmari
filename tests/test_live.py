"""Tests for the live demo: trial signups, the guard dashboard state, and the
attack script's campaigns.

Run from the repository root:  python -m pytest
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("GUARD_DB", str(Path(tempfile.mkdtemp()) / "guard.sqlite"))
os.environ.setdefault("GUARD_DEMO_KEY", "test-key")
os.environ.setdefault("GUARD_SIM_EVERY", "0")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from dashboard.app import app
    with TestClient(app) as c:
        c.post("/api/guard/reset", headers={"X-Demo-Key": os.environ["GUARD_DEMO_KEY"]})
        yield c


def signup(client, email, truth=None, **extra):
    headers = {"X-Demo-Truth": f"{os.environ['GUARD_DEMO_KEY']}:{truth}"} if truth else {}
    body = {"email": email, "device_id": extra.pop("device_id", ""), "fill_ms": extra.pop("fill_ms", 8000), **extra}
    return client.post("/api/trial/signup", json=body, headers=headers).json()


def test_pages_and_subdomains(client):
    assert client.get("/trial").status_code == 200
    assert client.get("/guard").status_code == 200
    assert "Ruska Bookings" in client.get("/", headers={"host": "trial.example.com"}).text
    assert "Free-Tier Guard" in client.get("/", headers={"host": "guard.example.com"}).text


def test_ordinary_visitor_is_allowed_and_gets_no_reasons(client):
    r = signup(client, "aino.virtanen@example.fi", device_id="1111aaaa2222bbbb", business="Studio Aino")
    assert r["action"] == "allow"
    assert r["reasons"] == []          # reasons are never shown to people who might be attackers


def test_naive_bot_is_blocked_by_its_own_signals(client):
    r = signup(client, "user48213@mailinator.com", truth="naive", website="http://spam.example", fill_ms=0)
    assert r["action"] == "block"
    assert any("hidden form field" in x for x in r["reasons"])


def test_device_farm_is_caught_and_earlier_accounts_suspended(client):
    results = [signup(client, f"lukas{name}{4000 + i * 37}@outlook.com", truth="farm", device_id="farmdevice0000001")
               for i, name in enumerate(["schmidt", "rossi", "laine", "novak", "hansen", "silva", "jones"])]
    assert results[-1]["action"] == "block"
    state = client.get("/api/guard/state").json()
    farm = state["campaigns"]["farm"]
    assert farm["total"] == 7 and farm["allow"] == 0
    assert state["scoreboard"]["attack"]["caught_later"] >= 1
    assert any(g["attack"] >= 5 for g in state["groups"])


def test_state_masks_emails(client):
    feed = client.get("/api/guard/state").json()["feed"]
    assert feed and all("•••" in r["email"] for r in feed)
    assert not any("virtanen" in r["email"] for r in feed)


def test_truth_header_needs_the_key(client):
    client.post("/api/trial/signup", json={"email": "someone@example.org", "fill_ms": 9000},
                headers={"X-Demo-Truth": "wrong-key:fake"})
    assert "fake" not in client.get("/api/guard/state").json()["campaigns"]


def test_reset_needs_the_key(client):
    assert client.post("/api/guard/reset").status_code == 403


def test_attack_campaigns_generate_valid_signups():
    import random
    import attack_demo
    rng = random.Random(1)
    for name, campaign in attack_demo.CAMPAIGNS.items():
        items = list(campaign(rng))
        assert items, name
        for body, ua, delay in items:
            assert "@" in body["email"] and ua and delay > 0
