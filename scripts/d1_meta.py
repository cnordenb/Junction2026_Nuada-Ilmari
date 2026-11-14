"""d1 as a second judge over all of Sargas's evidence.

Sargas turns each signup into factors (0 to 1) and a group verdict. This module
hands that evidence, but not Sargas's own score, to Liquid AI's d1-omni-600M
decision model and asks it named questions in one pass:

    bot     yes/no, with both sides defined: made by a script, bot or account
            farm, or by a real person (including families, schools, companies)
    kind    which of six kinds of signup this is, each described
    risk    how much harm letting this account in would do, on a 3-level scale

d1 returns calibrated probabilities directly (no generated text to parse).
"""
from __future__ import annotations

import json
import urllib.request

KINDS = {
    "person": "One real person signing up normally",
    "shared_device": "A family or flatmates sharing one phone or laptop",
    "organisation": "A school class or company team signing up together",
    "simple_script": "A simple script: throwaway inboxes, hidden field filled, automation browser",
    "account_farm": "An account farm: many accounts from few devices, one email template, unnatural timing",
    "humanlike_bot": "A careful bot that copies real people and varies every detail",
}
BOT_KINDS = ("simple_script", "account_farm", "humanlike_bot")

QUESTIONS = {
    "bot": {"type": "noul",
            "instructions": "Weighing all the evidence, was this account created by a bot, a script or an account farm?",
            "criteria": {"true": "Created by a script, bot or account farm",
                         "false": "Created by a real person, including families, schools and companies"}},
    "kind": {"type": "choice", "instructions": "Which kind of signup is this?", "criteria": KINDS},
    "risk": {"type": "score", "instructions": "How much harm would letting this account onto a free tier do?",
             "criteria": ["None: a genuine user", "Some: worth a second look", "High: part of abuse"]},
}


def evidence_state(signup: dict, parts: list[dict], group: dict | None) -> dict:
    """What d1 sees: the signup, every factor that fired with its value and
    reason, and the linked group's shared details. Never Sargas's score."""
    state = {
        "signup": {"email": signup.get("email", ""), "name": signup.get("username", "")},
        "evidence": [{"factor": p["label"], "strength": round(float(p["x"]), 2),
                      "direction": "lowers suspicion" if p["weight"] < 0 else "raises suspicion",
                      "detail": p.get("reason", "")[:160]} for p in parts],
        "note": "Strength runs from 0 to 1. No evidence listed means nothing unusual was found.",
    }
    if group:
        state["linked_group"] = {"signups_in_group": group.get("size"), "shared": group.get("evidence", [])[:4],
                                 "timing": group.get("timing", "")}
    return state


def ask(url: str, state: dict, timeout: float = 20) -> dict:
    body = json.dumps({"state": state, "questions": QUESTIONS}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/systemone", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        a = json.loads(res.read())["answers"]
    probs = a["kind"].get("probabilities") or {}
    if isinstance(probs, list):                     # option order, as documented
        probs = dict(zip(KINDS, probs))
    return {"p_bot": float(a["bot"]["noul"]),
            "kind": a["kind"].get("choice"),
            "p_bot_kind": float(sum(probs.get(k, 0) for k in BOT_KINDS)),
            "risk": float(a["risk"]["score"]) / (len(QUESTIONS["risk"]["criteria"]) - 1)}
