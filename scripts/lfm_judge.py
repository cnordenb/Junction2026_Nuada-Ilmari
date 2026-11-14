"""LFM3-VL-2B as an AI second opinion on a signup.

Sargas's evidence (every factor that fired, the linked group's shared details,
but never Sargas's own score) goes to Liquid AI's LFM3-VL-2B running in
llama.cpp's server. It answers with a JSON object forced by a schema: a one-line
reason first, then a verdict on a 5-step scale and the kind of signup.

Prompting notes (see docs/DEVLOG.md for the trials):
  * Native thinking is switched off. With it on, the model thought for 600-1,400
    tokens (15-20 s) and then gave every case P = 0.95.
  * A label scale beats a free probability: small models pick a label well and
    invent numbers badly.
  * Three worked examples in the system prompt calibrate it, and the prompt
    spells out the innocent explanations (families, schools, VPN users).
"""
from __future__ import annotations

import json
import urllib.request

VERDICTS = {"person": 0.0, "probably_person": 0.25, "unsure": 0.5, "probably_bot": 0.75, "bot": 1.0}
KINDS = ["person", "shared_device", "organisation", "simple_script", "account_farm", "humanlike_bot"]

SCHEMA = {"type": "object", "properties": {
    "reason": {"type": "string", "maxLength": 220},
    "verdict": {"type": "string", "enum": list(VERDICTS)},
    "kind": {"type": "string", "enum": KINDS}},
    "required": ["reason", "verdict", "kind"]}

SYSTEM = """You judge free-tier signups. Weigh the evidence our rules found. Innocent explanations are common:
families share devices, schools and companies share one IP and email domain, VPN users exist.
"lowers suspicion" evidence points to a real person. No evidence at all means nothing unusual: a person.
Strong bot evidence: throwaway inbox, hidden field filled, no mouse/typing, robotic movement, one device behind many accounts, one email template across a group.

Examples:
{"evidence": []} -> {"reason": "No unusual evidence.", "verdict": "person", "kind": "person"}
{"evidence": [{"factor": "Device reused", "strength": 0.25}]} -> {"reason": "Two accounts on one device fits a family.", "verdict": "probably_person", "kind": "shared_device"}
{"evidence": [{"factor": "Throwaway inbox", "strength": 1}, {"factor": "Automation browser", "strength": 1}]} -> {"reason": "Throwaway inbox from an automation browser.", "verdict": "bot", "kind": "simple_script"}
Reply with one JSON object only."""


def evidence_state(signup: dict, parts: list[dict], group: dict | None) -> dict:
    state = {"signup": {"email": signup.get("email", ""), "name": signup.get("username", "")},
             "evidence": [{"factor": p["label"], "strength": round(float(p["x"]), 2),
                           **({"direction": "lowers suspicion"} if p["weight"] < 0 else {}),
                           "detail": (p.get("reason") or "")[:140]} for p in parts]}
    if group:
        state["linked_group"] = {"signups_in_group": group.get("size"), "shared": list(group.get("evidence", []))[:4],
                                 "timing": group.get("timing", "")}
    return state


def judge(url: str, state: dict, timeout: float = 60) -> dict:
    body = {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(state)}],
            "temperature": 0, "max_tokens": 160, "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"name": "verdict", "schema": SCHEMA}}}
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        out = json.loads(json.loads(res.read())["choices"][0]["message"]["content"])
    return {"p_bot": VERDICTS[out["verdict"]], "verdict": out["verdict"], "kind": out["kind"], "reason": out["reason"][:220]}
