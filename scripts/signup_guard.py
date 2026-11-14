"""Find fake-account swarms in a stream of free-tier signups.

Two layers, both explained in plain language:

  1. Per-signup checks: throwaway inbox, several accounts on one inbox
     (Gmail dots and +tags), automation browser, datacenter or VPN network,
     one device behind many accounts.
  2. Swarm layer: signups that share rare details (device, inbox, email
     template, browser build, network) are linked into groups, and each
     group's timing is scored against random groups from the same stream with
     the team's synchrony scorer (sync_score.py). A group needs shared
     identity details or a hosting network *and* unusual timing, or high
     per-signup risk, before anything is blocked.

Actions: "block", "review" (ask a person, or show a challenge), "allow".
A shared school or company email domain is treated as an organisation
signing up together and sent to review, never blocked.

Usage:
    python scripts/signup_guard.py data/signups/demo_signups.csv
    python scripts/signup_guard.py data/signups/demo_signups.csv --label-col label
    python scripts/signup_guard.py data/signups/demo_signups.csv --json --out report.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.csgraph import connected_components

sys.path.insert(0, str(Path(__file__).resolve().parent))

from signup_lists import (AUTOMATION_UA, DOTS_IGNORED, FREE_PROVIDERS, HOSTING_ASNS,  # noqa: E402
                          PLUS_TAGS, disposable_domains)
from swarm_common import format_duration, is_positive_label, parse_times, read_table, to_iso  # noqa: E402
from sync_score import SyncScorer  # noqa: E402

FIELDS = {
    "time": ["created_at", "signup_time", "registered_at", "timestamp", "time", "date"],
    "email": ["email", "email_address", "mail"],
    "username": ["username", "user_name", "login", "handle", "name"],
    "ip": ["ip", "ip_address", "client_ip", "remote_addr"],
    "asn": ["asn", "as_number"],
    "asn_org": ["asn_org", "as_org", "isp", "network"],
    "user_agent": ["user_agent", "useragent", "ua", "browser"],
    "device_id": ["device_id", "fingerprint", "visitor_id", "device"],
    "id": ["id", "user_id", "account_id", "signup_id"],
}

# How much each kind of shared detail counts when linking two signups.
# Identity details are the ones a fake-account operator has to fabricate;
# network details are weak because offices, schools and VPNs share them.
TOKEN_WEIGHTS = {"device": 3.0, "inbox": 3.0, "edomain": 1.0, "etemplate": 1.2, "utemplate": 0.8,
                 "ua": 1.0, "ip": 1.0, "net": 0.8, "asn": 0.6}
COMMON_SHARE = 0.03          # details shared by more than 3% of signups are too common to be evidence
COMMON_MIN = 50
DEFAULT_LINK = 2.0           # total weight of shared details needed to link two signups
DEFAULT_MIN_SIZE = 5
DEFAULT_HALF_LIFE = 600.0

SIGNAL_POINTS = {"disposable": 45, "inbox_reuse": 50, "automation": 50, "hosting": 10,
                 "device_farm": 35, "no_fingerprint": 10,
                 # live signup form only
                 "honeypot": 60, "webdriver": 50, "fast_fill": 30}
FAST_FILL_SECONDS = 1.5
BLOCK_RISK, REVIEW_RISK = 60, 35
# Bot score (0-100) = the stronger of two pieces of evidence: the per-signup
# points, or the verdict of the group the signup belongs to. It is a ranking
# score with stated rules, not a calibrated probability.
GROUP_POINTS = {"block": 90, "review": 55, "organisation": 40}

CAVEATS = [
    "This flags patterns for a person to act on. Nothing here identifies who is behind an account.",
    "Network checks use small built-in lists of hosting providers and throwaway email services; a "
    "real deployment needs maintained lists.",
    "An attacker who varies every recorded detail and signs up at ordinary times is not caught "
    "(see abuse_slow_humanlike in the demo).",
    "Schools and companies signing up together share many details; they are sent to review, not blocked.",
    "All accuracy figures so far come from simulated signups written by the same team as the detector.",
]


# ---------------------------------------------------------------- loading

@dataclass
class Signups:
    frame: pd.DataFrame          # standard columns: id, time, email, username, ip, asn, asn_org, user_agent, device_id
    columns_used: dict
    rows_read: int
    labels: list[str] | None = None
    warnings: list[str] = field(default_factory=list)


def _pick(columns: list[str], names: list[str]) -> str | None:
    lower = {c.lower().strip(): c for c in columns}
    return next((lower[n] for n in names if n in lower), None)


def load_signups(path: str | Path, label_col: str | None = None, max_rows: int | None = None) -> Signups:
    raw = read_table(path)
    columns = list(raw.columns)
    used = {key: _pick(columns, names) for key, names in FIELDS.items()}
    if label_col and label_col not in raw.columns:
        raise ValueError(f"No column named {label_col!r}. Columns: {', '.join(columns)}")
    if not used["time"]:
        raise ValueError(f"Could not find the signup time column. Columns: {', '.join(columns)}")
    if not used["email"]:
        raise ValueError(f"Could not find the email column. Columns: {', '.join(columns)}")
    rows_read = len(raw)
    warnings = []
    if max_rows and rows_read > max_rows:
        raw = raw.iloc[:max_rows]
        warnings.append(f"The file has {rows_read:,} rows; only the first {max_rows:,} were analysed.")
    frame = pd.DataFrame({key: (raw[col] if col else "") for key, col in used.items() if key != "time"})
    if not used["id"]:
        frame["id"] = [str(i + 1) for i in range(len(raw))]
    frame["time"] = parse_times(raw[used["time"]])
    frame = frame.fillna("")
    for col in frame.columns:
        if col != "time":
            frame[col] = frame[col].astype(str).str.strip()
    keep = ~np.isnan(frame["time"].to_numpy()) & (frame["email"] != "")
    dropped = int((~keep).sum())
    if dropped:
        warnings.append(f"{dropped:,} rows were skipped because the time or email was missing or unreadable.")
    labels = raw[label_col].astype(str).tolist() if label_col else None
    if labels is not None:
        labels = [labels[i] for i in np.flatnonzero(keep)]
    frame = frame[keep].reset_index(drop=True)
    if frame.empty:
        raise ValueError("No usable rows.")
    missing = [k for k in ("ip", "asn", "user_agent", "device_id") if not used[k]]
    if missing:
        warnings.append("Not in this file, so those checks were skipped: " + ", ".join(missing) + ".")
    return Signups(frame, used, rows_read, labels, warnings)


# ---------------------------------------------------------------- features

def split_email(email: str) -> tuple[str, str]:
    local, _, domain = email.strip().lower().rpartition("@")
    return local, domain


def canonical_inbox(email: str) -> str:
    """The inbox an address really reaches: Gmail ignores dots, and many
    providers ignore anything after '+'."""
    local, domain = split_email(email)
    if domain == "googlemail.com":
        domain = "gmail.com"
    if domain in PLUS_TAGS:
        local = local.split("+", 1)[0]
    if domain in DOTS_IGNORED:
        local = local.replace(".", "")
    return f"{local}@{domain}"


def template(text: str) -> str:
    """Shape of a name: letter runs become 'a', digit runs become '9' with
    their length, other characters stay. 'user48213' -> 'a9{5}'."""
    out = re.sub(r"[^\W\d_]+", "a", text.lower())
    return re.sub(r"\d+", lambda m: f"9{{{len(m.group())}}}", out)


def subnet(ip: str) -> str:
    if ip.count(".") == 3:
        return ip.rsplit(".", 1)[0] + ".0/24"
    if ":" in ip:
        return ":".join(ip.split(":")[:3]) + "::/48"
    return ""


def is_automation(ua: str) -> bool:
    ua = ua.lower()
    return any(fragment in ua for fragment in AUTOMATION_UA)


def tokens_for(row: dict) -> list[tuple[str, str]]:
    local, domain = split_email(row["email"])
    tokens = [("inbox", canonical_inbox(row["email"])), ("edomain", domain),
              ("etemplate", f"{template(local)}@{domain}")]
    if row["username"]:
        tokens.append(("utemplate", template(row["username"])))
    if row["device_id"]:
        tokens.append(("device", row["device_id"]))
    if row["user_agent"]:
        tokens.append(("ua", row["user_agent"]))
    if row["ip"]:
        tokens.append(("ip", row["ip"]))
        if subnet(row["ip"]):
            tokens.append(("net", subnet(row["ip"])))
    if row["asn"]:
        tokens.append(("asn", row["asn"]))
    return tokens


def signup_signals(frame: pd.DataFrame) -> list[list[dict]]:
    """Per-signup checks. Each signal has points and a plain-language reason."""
    throwaway = disposable_domains()
    inbox = frame["email"].map(canonical_inbox)
    spellings = frame.groupby(inbox)["email"].transform(lambda s: s.str.lower().nunique())
    per_inbox = inbox.map(inbox.value_counts())
    device_counts = frame["device_id"].map(frame["device_id"].value_counts())
    has_fp_column = (frame["device_id"] != "").mean() >= 0.5
    out = []
    for i, row in enumerate(frame.to_dict("records")):
        signals = []
        _, domain = split_email(row["email"])
        if domain in throwaway:
            signals.append({"signal": "disposable", "points": SIGNAL_POINTS["disposable"],
                            "reason": f"Email is from a throwaway inbox service ({domain})."})
        if per_inbox.iat[i] > 1 and spellings.iat[i] > 1:
            signals.append({"signal": "inbox_reuse", "points": SIGNAL_POINTS["inbox_reuse"],
                            "reason": f"{per_inbox.iat[i]} accounts use spellings of one inbox "
                                      f"({inbox.iat[i]}); the provider ignores dots or +tags."})
        if row["user_agent"] and is_automation(row["user_agent"]):
            signals.append({"signal": "automation", "points": SIGNAL_POINTS["automation"],
                            "reason": "The browser identifies itself as an automation tool."})
        try:
            asn = int(float(row["asn"])) if row["asn"] else None
        except ValueError:
            asn = None
        if asn in HOSTING_ASNS:
            signals.append({"signal": "hosting", "points": SIGNAL_POINTS["hosting"],
                            "reason": f"Signed up from a datacenter or VPN network ({HOSTING_ASNS[asn]}). "
                                      "Privacy-minded people do this too, so on its own it is weak."})
        if row["device_id"] and device_counts.iat[i] >= DEFAULT_MIN_SIZE:
            signals.append({"signal": "device_farm", "points": SIGNAL_POINTS["device_farm"],
                            "reason": f"The same device created {device_counts.iat[i]} accounts."})
        elif row["device_id"] and device_counts.iat[i] >= 2:
            signals.append({"signal": "device_shared", "points": 5 * (int(device_counts.iat[i]) - 1),
                            "reason": f"This device has created {device_counts.iat[i]} accounts. Families share "
                                      "devices, so on its own this is weak."})
        if has_fp_column and not row["device_id"]:
            signals.append({"signal": "no_fingerprint", "points": SIGNAL_POINTS["no_fingerprint"],
                            "reason": "The browser did not run the device check on the signup page."})
        # Signals a live signup form can collect (absent from plain files).
        if str(row.get("honeypot", "")) in {"1", "true", "True"}:
            signals.append({"signal": "honeypot", "points": SIGNAL_POINTS["honeypot"],
                            "reason": "Filled in a hidden form field that people never see."})
        if str(row.get("webdriver", "")) in {"1", "true", "True"}:
            signals.append({"signal": "webdriver", "points": SIGNAL_POINTS["webdriver"],
                            "reason": "The browser reports it is remote-controlled (navigator.webdriver)."})
        fill = str(row.get("fill_ms", "")).strip()
        if fill:
            try:
                fill_s = float(fill) / 1000
            except ValueError:
                fill_s = None
            if fill_s is not None and fill_s < FAST_FILL_SECONDS:
                signals.append({"signal": "fast_fill", "points": SIGNAL_POINTS["fast_fill"],
                                "reason": f"The form was filled in {fill_s:.1f} s; people take several seconds."})
        out.append(signals)
    return out


# ---------------------------------------------------------------- bot score model
# bot score = 100 / (1 + e^-z),   z = BIAS + sum(weight_k * x_k)
# Every x_k is measured between 0 and 1, so the score moves gradually: a
# second account on one phone nudges it, a fifth pushes it hard. Weights are
# set by hand from what each factor means (not fitted), then checked on the
# forged logs (scripts/eval_signups.py). It is a ranking score with stated
# rules, not a calibrated probability.
BIAS = -4.0
FACTORS = [
    # key, label, weight, how x is measured
    ("throwaway", "Throwaway inbox", 3.0, "1 if the email domain is a throwaway inbox service"),
    ("same_inbox", "Same inbox, other spelling", 3.5, "(accounts on one real inbox - 1) / 3, capped at 1"),
    ("automation", "Automation browser", 4.0, "1 if the browser says it is an automation tool or remote-controlled"),
    ("hidden_field", "Hidden field filled", 5.0, "1 if the invisible form field was filled in"),
    ("fast_fill", "Form filled too fast", 2.0, "(3 s - time to fill) / 3 s, between 0 and 1"),
    ("device_reuse", "Device reused", 3.0, "(accounts from this device - 1) / 4, capped at 1"),
    ("no_device_check", "Device check missing", 1.0, "1 if the page's device check never ran"),
    ("datacenter", "Datacenter / VPN network", 0.8, "1 if the network is a cloud, hosting or VPN provider"),
    ("machine_name", "Machine-made name", 0.8, "(digits at the end of the email name - 1) / 4, capped at 1"),
    # Behaviour on the signup page (live form only; absent from plain files).
    ("no_human_input", "No mouse, touch or typing", 1.5, "1 if the page ran but saw no mouse movement, touch or key press"),
    ("robotic_motion", "Robotic movement or typing", 2.0, "straight-line, constant-speed pointer paths, or perfectly even typing (0 to 1)"),
    ("human_motion", "Natural movement and typing", -1.5, "wobbly, paused pointer or touch movement and irregular typing (0 to 1)"),
    ("d1_model", "AI model (d1): looks machine-made", 1.5, "Liquid AI d1-omni-600M: the larger of P(email looks machine-made) and P(horse name is a username, full name or spam), counted above 0.5 and rescaled to 0-1"),
    ("near_server", "Latency too low for a person", 0.5, "1 if the page's background ping took under 4 ms (a machine next to our server)"),
    ("swarm_size", "Size of linked group", 1.5, "(signups in the linked group - 4) / 10, capped at 1, times how well this signup matches the group"),
    ("shared_identity", "Matches the group's shared details", 2.0, "weighted share of the group's shared details this signup has (device, inbox, throwaway, automation count most; email pattern, IP, network less)"),
    ("timing", "Group timing beats chance", 2.5, "group synchrony score / 100 (burst, timer, same minute, same time of day), times how well this signup matches the group"),
    ("organisation", "School or company group", -3.0, "1 if the group looks like one organisation signing up together"),
]
FACTOR_KEYS = [f[0] for f in FACTORS]
WEIGHTS = np.array([f[2] for f in FACTORS])
SCORE_BLOCK, SCORE_REVIEW = 60, 35
# How strongly each kind of shared detail ties one signup to its group.
EVIDENCE_WEIGHT = {"inbox": 1.0, "device": 1.0, "disposable": 1.0, "ua": 0.6, "etemplate": 0.4,
                   "ip": 0.5, "net": 0.4, "asn": 0.4}


GROUP_KEYS = {"swarm_size", "shared_identity", "timing", "organisation"}


def model_description() -> dict:
    return {"bias": BIAS, "block": SCORE_BLOCK, "review": SCORE_REVIEW,
            "factors": [{"key": k, "label": l, "weight": w, "measure": m, "group": k in GROUP_KEYS}
                        for k, l, w, m in FACTORS]}


def d1_factor(raw: str) -> tuple[float, str] | None:
    """The d1 decision model's answers, stored at signup time."""
    try:
        d = json.loads(raw) if raw else None
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    email_p, name_p = float(d.get("email_machine", 0) or 0), float(d.get("name_not_pet", 0) or 0)
    x = max(0.0, (max(email_p, name_p) - 0.5) / 0.5)
    if x <= 0:
        return None
    which = "the email looks machine-made" if email_p >= name_p else "the horse name looks like a username, a full name or spam"
    return x, f"The d1 AI model judged that {which} (P = {max(email_p, name_p):.2f})."


def behaviour_factors(raw: str) -> dict[str, tuple[float, str]]:
    """Behaviour summary from the signup page -> {factor: (x, reason)}.
    The page sends counts and statistics only, never the pointer path."""
    try:
        b = json.loads(raw) if raw else None
    except ValueError:
        b = None
    if not isinstance(b, dict):
        return {}
    num = lambda k: float(b.get(k) or 0) if isinstance(b.get(k), (int, float)) else 0.0
    moves, touches, keys = num("moves"), num("touches"), num("keys")
    straight, speed_cv, pauses, key_cv = num("straight"), num("speed_cv"), num("pauses"), num("key_cv")
    rtt = b.get("rtt") if isinstance(b.get("rtt"), (int, float)) else None
    out: dict[str, tuple[float, str]] = {}
    if moves + touches + keys == 0:
        out["no_human_input"] = (1.0, "The page saw no mouse movement, touch or key press: the form was filled by a script.")
    robotic_pointer = 0.0
    if moves >= 10:
        robotic_pointer = min(1, max(0, (straight - 0.85) / 0.15)) * min(1, max(0, (0.3 - speed_cv) / 0.3))
    robotic_keys = min(1, max(0, (0.12 - key_cv) / 0.12)) if keys >= 6 else 0.0
    robotic = max(robotic_pointer, robotic_keys)
    if robotic > 0:
        what = "pointer moved in straight lines at constant speed" if robotic_pointer >= robotic_keys else "keys were pressed at perfectly even intervals"
        out["robotic_motion"] = (robotic, f"The {what}, unlike a hand.")
    move_part = min(1, (moves + touches) / 40) * (1 if pauses >= 1 else 0.6) * (1 - robotic_pointer)
    type_part = min(1, max(0, (key_cv - 0.2) / 0.4)) if keys >= 4 else 0.0
    human = min(1.0, 0.6 * move_part + 0.4 * type_part)
    if human > 0:
        out["human_motion"] = (human, f"Natural input: {int(moves)} pointer moves, {int(touches)} touches, "
                                      f"{int(pauses)} pauses, uneven typing rhythm.")
    if rtt is not None and 0 <= rtt < 4:
        out["near_server"] = (1.0, f"The background ping took {rtt:.1f} ms, faster than any phone or home connection.")
    return out


def signup_factors(frame: pd.DataFrame) -> tuple[np.ndarray, list[dict]]:
    """Per-signup factors (the first nine). Returns x (n x 13, group columns
    left at 0) and, per signup, a reason for every factor above 0."""
    n = len(frame)
    x = np.zeros((n, len(FACTORS)))
    col = {k: i for i, k in enumerate(FACTOR_KEYS)}
    why: list[dict] = [{} for _ in range(n)]
    throwaway = disposable_domains()
    inbox = frame["email"].map(canonical_inbox)
    spellings = frame.groupby(inbox)["email"].transform(lambda s: s.str.lower().nunique())
    per_inbox = inbox.map(inbox.value_counts())
    device_counts = frame["device_id"].map(frame["device_id"].value_counts())
    has_fp_column = (frame["device_id"] != "").mean() >= 0.5
    for i, row in enumerate(frame.to_dict("records")):
        local, domain = split_email(row["email"])

        def put(key, value, reason):
            if value > 0:
                x[i, col[key]] = min(1.0, value)
                why[i][key] = reason

        if domain in throwaway:
            put("throwaway", 1, f"Email is from a throwaway inbox service ({domain}).")
        if per_inbox.iat[i] > 1 and spellings.iat[i] > 1:
            put("same_inbox", (per_inbox.iat[i] - 1) / 3,
                f"{per_inbox.iat[i]} accounts use spellings of one inbox ({inbox.iat[i]}); the provider ignores dots or +tags.")
        if (row["user_agent"] and is_automation(row["user_agent"])) or str(row.get("webdriver", "")) in {"1", "true", "True"}:
            put("automation", 1, "The browser identifies itself as an automation tool or reports it is remote-controlled.")
        if str(row.get("honeypot", "")) in {"1", "true", "True"}:
            put("hidden_field", 1, "Filled in a hidden form field that people never see.")
        fill = str(row.get("fill_ms", "")).strip()
        if fill:
            try:
                fill_s = float(fill) / 1000
                put("fast_fill", (3.0 - fill_s) / 3.0, f"The form was filled in {fill_s:.1f} s; people usually take more than 3 s.")
            except ValueError:
                pass
        if row["device_id"] and device_counts.iat[i] >= 2:
            put("device_reuse", (device_counts.iat[i] - 1) / 4,
                f"This device has created {device_counts.iat[i]} accounts" +
                (". Families share devices, so a few is normal." if device_counts.iat[i] < DEFAULT_MIN_SIZE else "."))
        if has_fp_column and not row["device_id"]:
            put("no_device_check", 1, "The browser did not run the device check on the signup page.")
        try:
            asn = int(float(row["asn"])) if row["asn"] else None
        except ValueError:
            asn = None
        if asn in HOSTING_ASNS:
            put("datacenter", 1, f"Signed up from a datacenter or VPN network ({HOSTING_ASNS[asn]}). VPN users do this too.")
        digits = re.search(r"(\d+)$", local.split("+", 1)[0])
        if digits and len(digits.group(1)) >= 2:
            d = len(digits.group(1))
            put("machine_name", (d - 1) / 4, f"The email name ends in {d} digits, common in generated accounts.")
        for key, (val, reason) in behaviour_factors(str(row.get("behaviour", "") or "")).items():
            put(key, val, reason)
        d1 = d1_factor(str(row.get("d1", "") or ""))
        if d1:
            put("d1_model", d1[0], d1[1])
    return x, why


def score_from(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    z = BIAS + x @ WEIGHTS
    return z, 100.0 / (1.0 + np.exp(-z))


# ---------------------------------------------------------------- linking

def link_matrix(frame: pd.DataFrame) -> tuple[sparse.csr_matrix, dict]:
    """Rows = signups, columns = details shared by 2 or more signups, entries
    = sqrt(weight). Then (x @ x.T)[i, j] is the total weight of the details
    signups i and j share. Details shared by too many signups (gmail.com, the
    current Chrome build, a big home-internet provider) are left out: they
    are not evidence that two signups belong together."""
    rows = frame.to_dict("records")
    token_rows = [set(tokens_for(r)) for r in rows]
    df = Counter(tok for toks in token_rows for tok in toks)
    n = len(rows)
    common = max(COMMON_MIN, COMMON_SHARE * n)
    vocab: dict[tuple[str, str], int] = {}
    data, ri, ci = [], [], []
    for r, toks in enumerate(token_rows):
        for tok in toks:
            if df[tok] < 2 or df[tok] > common:
                continue
            if tok[0] == "edomain" and tok[1] in FREE_PROVIDERS:
                continue
            c = vocab.setdefault(tok, len(vocab))
            data.append(math.sqrt(TOKEN_WEIGHTS[tok[0]]))
            ri.append(r)
            ci.append(c)
    x = sparse.csr_matrix((data, (ri, ci)), shape=(n, max(len(vocab), 1)))
    return x, {"tokens_used": len(vocab), "common_cutoff": int(common)}


# ---------------------------------------------------------------- clusters

def _share(values: list[str]) -> tuple[str, float]:
    values = [v for v in values if v]
    if not values:
        return "", 0.0
    value, count = Counter(values).most_common(1)[0]
    return value, count / len(values)


def _evidence(members: pd.DataFrame) -> list[dict]:
    """Details most of the group shares, in plain language, strongest first."""
    n = len(members)
    found = []
    inbox, s = _share(members["email"].map(canonical_inbox).tolist())
    distinct_inboxes = members["email"].map(canonical_inbox).nunique()
    if distinct_inboxes <= max(1, n // 4):
        repeated = {k for k, v in Counter(members["email"].map(canonical_inbox)).items() if v > 1}
        found.append({"kind": "identity", "key": "inbox",
                      "text": f"{n} accounts lead to only {distinct_inboxes} real inbox(es), e.g. {inbox}.",
                      "match": lambda r, v=repeated: canonical_inbox(r["email"]) in v})
    devices = [d for d in members["device_id"] if d]
    if devices and len(set(devices)) <= max(1, len(devices) // 4):
        repeated = {k for k, v in Counter(devices).items() if v > 1}
        found.append({"kind": "identity", "key": "device",
                      "text": f"{len(devices)} accounts came from only {len(set(devices))} device(s).",
                      "match": lambda r, v=repeated: r["device_id"] in v})
    tmpl, s = _share([f"{template(split_email(e)[0])}@{split_email(e)[1]}" for e in members["email"]])
    if s >= 0.7 and not re.fullmatch(r"a(\.a)?@.*", tmpl):
        found.append({"kind": "identity", "key": "etemplate",
                      "text": f"{s:.0%} of email addresses follow one pattern ({tmpl}, where a = letters, "
                              "9{n} = n digits).",
                      "match": lambda r, v=tmpl: f"{template(split_email(r['email'])[0])}@{split_email(r['email'])[1]}" == v})
    domain, s = _share([split_email(e)[1] for e in members["email"]])
    throwaway = disposable_domains()
    n_throwaway = sum(split_email(e)[1] in throwaway for e in members["email"])
    if n_throwaway >= 0.5 * n:
        found.append({"kind": "identity", "key": "disposable",
                      "text": f"{n_throwaway} of {n} use throwaway email services.",
                      "match": lambda r, v=throwaway: split_email(r["email"])[1] in v})
    elif s >= 0.7 and domain not in FREE_PROVIDERS:
        found.append({"kind": "organisation", "key": "edomain",
                      "text": f"{s:.0%} use one organisation's email domain ({domain}).",
                      "match": lambda r, v=domain: split_email(r["email"])[1] == v})
    ua, s = _share(members["user_agent"].tolist())
    if ua and s >= 0.7:
        label = "an automation browser" if is_automation(ua) else "one exact browser build"
        found.append({"kind": "identity" if is_automation(ua) else "software", "key": "ua",
                      "text": f"{s:.0%} use {label}: {ua[:90]}",
                      "match": lambda r, v=ua: r["user_agent"] == v})
    ip, s = _share(members["ip"].tolist())
    if ip and s >= 0.5:
        found.append({"kind": "network", "key": "ip", "text": f"{s:.0%} share one IP address.",
                      "match": lambda r, v=ip: r["ip"] == v})
    else:
        net, s = _share([subnet(i) for i in members["ip"]])
        if net and s >= 0.5:
            found.append({"kind": "network", "key": "net", "text": f"{s:.0%} come from one /24 address block.",
                          "match": lambda r, v=net: subnet(r["ip"]) == v})
    asn, s = _share(members["asn"].tolist())
    try:
        asn_int = int(float(asn)) if asn else None
    except ValueError:
        asn_int = None
    if asn_int in HOSTING_ASNS and s >= 0.5:
        found.append({"kind": "hosting", "key": "asn",
                      "text": f"{s:.0%} signed up from {HOSTING_ASNS[asn_int]}, a datacenter or VPN network.",
                      "match": lambda r, v=asn: r["asn"] == v})
    return found


def _timing_text(sync: dict) -> str:
    pattern = sync.get("pattern")
    span = format_duration(sync.get("span_seconds") or 0)
    if not pattern:
        return f"Created over {span} with ordinary timing."
    return {"burst": f"Created closer together than chance explains (all within {span}).",
            "regular": f"Created at near-constant intervals, about every "
                       f"{format_duration(sync.get('mean_gap') or 0)}, like a timer.",
            "hourly": "Created at the same minute of different hours.",
            "daily": f"Created at the same time of day on different days ({span} in total)."}[pattern]


def judge_cluster(members: pd.DataFrame, risks: np.ndarray, sync: dict, cohesion: float) -> dict:
    evidence = _evidence(members)
    kinds = {e["kind"] for e in evidence}
    keys = {e["key"] for e in evidence}
    mean_risk = float(risks.mean())
    timing = sync["sync"]
    organisation = ("organisation" in kinds and not ({"inbox", "device", "disposable"} & keys)
                    and mean_risk < 20)
    identity = "identity" in kinds
    software = "software" in kinds
    hosting = "hosting" in kinds
    why = []
    if organisation:
        action = "review"
        why.append("Looks like a school or company signing up together: shared organisation email "
                   "domain, no shared devices or throwaway inboxes. Not blocked; worth a human look.")
    elif mean_risk >= 40:
        action = "block"
        why.append(f"Most accounts already fail individual checks (average risk {mean_risk:.0f}/100).")
    elif identity and timing >= 30:
        action = "block"
        why.append("Shared identity details plus unusual timing.")
    elif (hosting or software) and timing >= 50:
        action = "block"
        why.append("Same network or browser build plus strongly unusual timing.")
    elif identity or timing >= 30 or mean_risk >= 20:
        action = "review"
        why.append("Some shared details or unusual timing, but not enough to block.")
    else:
        action = "allow"
        why.append("Shared details are weak and the timing is ordinary.")
    return {"action": action, "organisation": organisation, "evidence": evidence,
            "timing": _timing_text(sync), "why": why, "mean_risk": round(mean_risk, 1),
            "shared_weight": round(cohesion, 2)}


# ---------------------------------------------------------------- analysis

ACTION_RANK = {"allow": 0, "review": 1, "block": 2}


def analyse(su: Signups, link: float = DEFAULT_LINK, min_size: int = DEFAULT_MIN_SIZE,
            half_life: float = DEFAULT_HALF_LIFE, sample: int = 30, per_row: bool = False) -> dict:
    """per_row=True adds "risk", "reasons" and "cluster_of" (group id or -1)
    for every row, plus each group's member indices as "members"; the live
    demo uses these to explain every signup."""
    frame = su.frame
    n = len(frame)
    times = frame["time"].to_numpy(dtype=float)
    signals = signup_signals(frame)
    risk = np.array([min(100, sum(s["points"] for s in sig)) for sig in signals], dtype=float)
    action = np.where(risk >= BLOCK_RISK, "block", np.where(risk >= REVIEW_RISK, "review", "allow")).astype(object)
    reason_src = ["signup checks" if a != "allow" else "" for a in action]
    group_points = np.zeros(n)
    group_reason = [""] * n
    fx, fwhy = signup_factors(frame)
    fcol = {k: i for i, k in enumerate(FACTOR_KEYS)}

    x, link_info = link_matrix(frame)
    sim = (x @ x.T).tocsr()
    sim.data[sim.data < link] = 0
    sim.eliminate_zeros()
    n_comp, comp = connected_components(sim, directed=False)
    sizes = np.bincount(comp)
    scorer = SyncScorer(times, half_life)
    clusters = []
    cluster_of = np.full(n, -1)
    for c in np.flatnonzero(sizes >= min_size):
        idx = np.flatnonzero(comp == c)
        sub = (x[idx] @ x[idx].T).toarray()
        cohesion = float((sub.sum() - np.trace(sub)) / max(len(idx) * (len(idx) - 1), 1))
        sync = scorer.score(times[idx])
        verdict = judge_cluster(frame.iloc[idx], risk[idx], sync, cohesion)
        cid = len(clusters) + 1
        cluster_of[idx] = cid
        # A member is blocked only if it carries the group's evidence itself
        # (two of the shared details, or the only one); the rest go to review.
        # When the group's case rests on identity details (device, inbox,
        # email pattern, throwaway or automation), a member must carry one of
        # those: sharing only the network or browser with a farm is not enough.
        need = min(2, len(verdict["evidence"]))
        identity_ev = [e for e in verdict["evidence"] if e["kind"] == "identity"]
        size_x = min(1.0, max(0.0, (len(idx) - 4) / 10))
        timing_x = float(sync["sync"]) / 100
        shared_txt = "; ".join(e["text"].rstrip(".") for e in verdict["evidence"][:2]) or "a few shared details"
        ev_w = [EVIDENCE_WEIGHT.get(e["key"], 0.5) for e in verdict["evidence"] if e["kind"] != "organisation"]
        ev_all = [e for e in verdict["evidence"] if e["kind"] != "organisation"]
        for i in idx:
            row_i = frame.iloc[i]
            # How much of the group's case applies to this signup: shared
            # device or inbox count fully, a shared email shape only a little.
            carry = (sum(w for e, w in zip(ev_all, ev_w) if e["match"](row_i)) / sum(ev_w)) if ev_w else 0.0
            if size_x * carry > 0:
                fx[i, fcol["swarm_size"]] = size_x * carry
                fwhy[i]["swarm_size"] = f"Linked to {len(idx) - 1} other signups ({shared_txt})."
            if carry:
                fx[i, fcol["shared_identity"]] = carry
                fwhy[i]["shared_identity"] = f"Has {carry:.0%} of what the group shares (weighted)."
            if timing_x * carry > 0:
                fx[i, fcol["timing"]] = timing_x * carry
                fwhy[i]["timing"] = _timing_text(sync)
            if verdict["organisation"]:
                fx[i, fcol["organisation"]] = 1.0
                fwhy[i]["organisation"] = "The group looks like one school or company signing up together."
            mine = verdict["action"]
            if mine == "block":
                row = frame.iloc[i]
                carried = sum(bool(e["match"](row)) for e in verdict["evidence"])
                if carried < need or (identity_ev and not any(e["match"](row) for e in identity_ev)):
                    mine = "review"
            if mine != "allow":
                key = "organisation" if verdict["organisation"] else mine
                group_points[i] = GROUP_POINTS[key]
                shared = "; ".join(e["text"].rstrip(".") for e in verdict["evidence"][:2]) or "shared details"
                group_reason[i] = (f"Linked to {len(idx) - 1} other signups: {shared}. {_timing_text(sync)} "
                                   f"Group verdict: {verdict['why'][0]}")
            if ACTION_RANK[mine] > ACTION_RANK[action[i]]:
                action[i] = mine
                reason_src[i] = f"group {cid}"
        for e in verdict["evidence"]:
            e.pop("match")
        order = idx[np.argsort(times[idx])]
        clusters.append({
            "id": cid, "size": int(len(idx)), **verdict,
            "sync": round(float(sync["sync"]), 1), "pattern": sync["pattern"],
            "beats_random": sync["beats_random"],
            "first": to_iso(times[idx].min()), "last": to_iso(times[idx].max()),
            "signups": [_row(frame, i, risk, signals) for i in order[:sample]],
            "_idx": idx,
        })
    # The score decides the action: one equation for every signup.
    zval, score = score_from(fx)
    action = np.where(score >= SCORE_BLOCK, "block", np.where(score >= SCORE_REVIEW, "review", "allow")).astype(object)
    for c in clusters:
        members = c["_idx"]
        c["rule_action"] = c["action"]
        c["action"] = action[members[np.argsort(score[members])[len(members) // 2]]]   # the median member's action
        c["median_score"] = int(round(float(np.median(score[members]))))
    clusters.sort(key=lambda c: (-ACTION_RANK[c["action"]], -c["size"]))

    report = {
        "dataset": {"rows_read": su.rows_read, "signups": n, "columns_used": su.columns_used,
                    "warnings": su.warnings},
        "settings": {"link": link, "min_size": min_size, "half_life_seconds": half_life,
                     "common_cutoff": link_info["common_cutoff"]},
        "totals": {a: int((action == a).sum()) for a in ("block", "review", "allow")},
        "clusters": clusters,
        "individual": [_row(frame, i, risk, signals) for i in np.flatnonzero((risk >= REVIEW_RISK) & (cluster_of < 0))[:sample]],
        "caveats": CAVEATS,
    }
    if su.labels is not None:
        report["evaluation"] = evaluate(su, action, clusters, score)
    for c in clusters:
        idx = c.pop("_idx")
        if per_row:
            c["members"] = idx.tolist()
    report["actions"] = action.tolist()
    if per_row:
        report["risk"] = risk.astype(int).tolist()
        report["reasons"] = [[s["reason"] for s in sig] for sig in signals]
        report["cluster_of"] = cluster_of.tolist()
        report["score"] = np.round(score).astype(int).tolist()
        report["z"] = np.round(zval, 2).tolist()
        report["score_parts"] = [
            sorted(({"key": k, "label": FACTORS[j][1], "x": round(float(fx[i, j]), 2), "weight": FACTORS[j][2],
                     "contribution": round(float(fx[i, j] * FACTORS[j][2]), 2), "reason": fwhy[i].get(k, ""),
                     "kind": "group" if k in GROUP_KEYS else "signup", "points": round(float(fx[i, j] * FACTORS[j][2]), 2)}
                    for j, k in enumerate(FACTOR_KEYS) if fx[i, j] > 0), key=lambda d: -abs(d["contribution"]))
            for i in range(n)]
        report["model"] = model_description()
    return report


def _row(frame: pd.DataFrame, i: int, risk: np.ndarray, signals: list[list[dict]]) -> dict:
    r = frame.iloc[i]
    return {"id": r["id"], "time": to_iso(r["time"]), "email": r["email"], "username": r["username"],
            "ip": r["ip"], "asn_org": r["asn_org"], "user_agent": r["user_agent"][:120],
            "device_id": r["device_id"], "risk": int(risk[i]),
            "reasons": [s["reason"] for s in signals[i]]}


def _metrics(truth: np.ndarray, flagged: np.ndarray) -> dict:
    tp = int((truth & flagged).sum())
    fp = int((~truth & flagged).sum())
    fn = int((truth & ~flagged).sum())
    tn = int((~truth & ~flagged).sum())
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(100 * tp / (tp + fp), 1) if tp + fp else None,
            "recall": round(100 * tp / (tp + fn), 1) if tp + fn else None,
            "false_positive_rate": round(100 * fp / (fp + tn), 2) if fp + tn else None}


def score_quality(truth: np.ndarray, score: np.ndarray) -> dict:
    """How well the bot score separates bots from people: AUC (chance that a
    random bot scores higher than a random person), a histogram per class,
    and precision / recall / false-positive rate at a few cut-offs."""
    pos, neg = score[truth], score[~truth]
    auc = None
    if len(pos) and len(neg):
        ranks = pd.Series(score).rank().to_numpy()
        auc = float((ranks[truth].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))
    edges = list(range(0, 101, 10))
    hist = lambda v: np.histogram(np.clip(v, 0, 99.999), bins=edges)[0].astype(int).tolist()
    cuts = []
    for cut in (30, 50, 70, 90):
        m = _metrics(truth, score >= cut)
        cuts.append({"cut": cut, **m})
    return {"auc": None if auc is None else round(auc, 4), "bins": edges, "bots": hist(pos), "people": hist(neg),
            "cutoffs": cuts, "bots_total": int(len(pos)), "people_total": int(len(neg))}


def evaluate(su: Signups, action: np.ndarray, clusters: list[dict], score: np.ndarray | None = None) -> dict:
    labels = su.labels
    truth = np.array([is_positive_label(l) for l in labels])
    blocked = action == "block"
    touched = action != "allow"
    # Per scenario: the label, or the note column for innocent look-alikes when present.
    raw = read_table_note(su)
    groups = [l if is_positive_label(l) or not raw else raw[i] for i, l in enumerate(labels)]
    by = []
    for g in sorted(set(groups), key=lambda g: (not is_positive_label(g.split(":")[0]), g)):
        m = np.array([x == g for x in groups])
        by.append({"group": g, "abusive": bool(truth[m][0]), "signups": int(m.sum()),
                   "blocked": int(blocked[m].sum()), "review": int((action[m] == "review").sum())})
    out = {"block": _metrics(truth, blocked), "block_or_review": _metrics(truth, touched), "by_group": by}
    if score is not None:
        out["score"] = score_quality(truth, score)
        for g in by:
            m = np.array([x == g["group"] for x in groups])
            g["mean_score"] = round(float(score[m].mean()), 1)
    return out


def read_table_note(su: Signups) -> list[str] | None:
    return su.frame["note"].tolist() if "note" in su.frame.columns else None


# ---------------------------------------------------------------- CLI

def print_report(report: dict, show: int = 8) -> None:
    d = report["dataset"]
    print(f"{d['signups']:,} signups analysed.")
    for w in d["warnings"]:
        print(f"  note: {w}")
    t = report["totals"]
    print(f"Block {t['block']}, review {t['review']}, allow {t['allow']}.\n")
    for c in report["clusters"][:show]:
        print(f"[{c['action'].upper()}] group {c['id']}: {c['size']} signups, {c['first']} to {c['last']}")
        for e in c["evidence"]:
            print(f"    - {e['text']}")
        print(f"    - {c['timing']}")
        for w in c["why"]:
            print(f"    => {w}")
        print()
    if "evaluation" in report:
        ev = report["evaluation"]
        for name in ("block", "block_or_review"):
            m = ev[name]
            print(f"{name:>16}: precision {m['precision']}%  recall {m['recall']}%  "
                  f"false-positive rate {m['false_positive_rate']}%  (tp {m['tp']}, fp {m['fp']}, fn {m['fn']})")
        print()
        print(f"{'group':<34}{'signups':>8}{'blocked':>9}{'review':>8}")
        for g in ev["by_group"]:
            print(f"{g['group']:<34}{g['signups']:>8}{g['blocked']:>9}{g['review']:>8}")
    print("\nCaveats:")
    for c in report["caveats"]:
        print(f"  - {c}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path")
    p.add_argument("--label-col", help="answer-key column; prints precision, recall and false-positive rate")
    p.add_argument("--link", type=float, default=DEFAULT_LINK, help="total weight of shared details needed to link two signups")
    p.add_argument("--min-size", type=int, default=DEFAULT_MIN_SIZE)
    p.add_argument("--json", action="store_true")
    p.add_argument("--out")
    args = p.parse_args(argv)
    su = load_signups(args.path, args.label_col)
    note = read_table(args.path).get("note")
    if note is not None and args.label_col:
        su.frame["note"] = note.iloc[: len(su.frame)].tolist() if len(note) == len(su.frame) else ""
    report = analyse(su)
    report.pop("actions")
    if args.json or args.out:
        text = json.dumps(report, indent=2, ensure_ascii=False)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        else:
            print(text)
    if not args.json:
        print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
