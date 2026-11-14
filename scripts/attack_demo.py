"""Attack the demo trial site the way a fake-account operator would.

Run it from a laptop against the live site and watch the guard dashboard.
Standard library only, so it runs on any laptop with Python 3.9+.

    python scripts/attack_demo.py https://trial.example.com --key DEMO_KEY
    python scripts/attack_demo.py http://127.0.0.1:8000 --key dev --speed 2
    python scripts/attack_demo.py URL --campaigns stealth-farm --include-miss

Campaigns, in order:
    naive-bot     a script posting straight to the API: throwaway inboxes,
                  "user12345" names, fills the hidden field, no device check
    alias-farm    one Gmail inbox multiplied with dots and +tags, real browser
    stealth-farm  realistic names, a real browser string, 3 devices rotating,
                  human-speed form filling: each account looks fine alone
    humanlike     (only with --include-miss) varies every detail and waits
                  between signups. We expect this one to get through.

--key sends a header with the campaign name so the dashboard can keep score.
The detector never sees that header. Run this from a different network than
the visitors (a phone hotspot), otherwise visitors share the attacker's IP.
"""
from __future__ import annotations

import argparse
import json
import random
import secrets
import sys
import time
import urllib.error
import urllib.request

COLOURS = {"block": "\033[1;31m", "review": "\033[1;33m", "allow": "\033[1;32m", "dim": "\033[2m", "bold": "\033[1m",
           "end": "\033[0m"}
THROWAWAY = ["mailinator.com", "yopmail.com", "guerrillamail.com", "sharklasers.com", "10minutemail.com", "maildrop.cc"]
FIRST = "aino mikko sanna jukka leena pekka anna lukas sophie jonas lea felix marie paul julia oliver amelia harry grace noah".split()
LAST = "virtanen korhonen nieminen laine smith jones muller schmidt garcia rossi bianchi novak hansen karlsson silva".split()
CHROME = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/{v}.0.0.0 Safari/537.36")
STALE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/124.0.6367.60 Safari/537.36")
OTHER_UAS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 26_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
    "Mozilla/5.0 (Linux; Android 14; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36",
]


def colour(text: str, key: str) -> str:
    return f"{COLOURS[key]}{text}{COLOURS['end']}" if sys.stdout.isatty() else text


def device() -> str:
    return secrets.token_hex(8)


def naive_bot(rng: random.Random):
    for _ in range(12):
        n = rng.randrange(10000, 99999)
        yield ({"email": f"user{n}@{rng.choice(THROWAWAY)}", "business": f"user{n}", "website": "http://cheap-seo.example"},
               "python-urllib/3.12", 0.3)


def alias_farm(rng: random.Random):
    base = "johnsmithdeals"
    for _ in range(10):
        local = list(base)
        for pos in sorted(rng.sample(range(1, len(base) - 1), rng.randrange(1, 4)), reverse=True):
            local.insert(pos, ".")
        email = "".join(local) + (f"+trial{rng.randrange(1, 99)}" if rng.random() < 0.6 else "") + "@gmail.com"
        yield ({"email": email, "business": f"{rng.choice(FIRST).title()} Studio", "device_id": device(),
                "fill_ms": rng.randrange(4000, 9000)}, CHROME.format(v=rng.choice([140, 141, 142])), 1.5)


def stealth_farm(rng: random.Random):
    devices = [device() for _ in range(3)]
    for k in range(15):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        digits = rng.randrange(1000, 9999)
        yield ({"email": f"{first}{last}{digits}@outlook.com", "business": f"{first.title()} {last.title()} Hair",
                "device_id": devices[k % 3], "fill_ms": rng.randrange(3000, 8000)}, STALE, 2.0)


def humanlike(rng: random.Random):
    for _ in range(6):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        email = rng.choice([f"{first}.{last}@gmail.com", f"{first}{rng.randrange(70, 99)}@icloud.com",
                            f"{first[0]}{last}@proton.me", f"{first}_{last}@yahoo.com"])
        yield ({"email": email, "business": f"{last.title()} {rng.choice(['Yoga', 'Nails', 'Barber', 'Massage'])}",
                "device_id": device(), "fill_ms": rng.randrange(9000, 40000)}, rng.choice(OTHER_UAS), rng.uniform(8, 20))


CAMPAIGNS = {"naive-bot": naive_bot, "alias-farm": alias_farm, "stealth-farm": stealth_farm, "humanlike": humanlike}


def post(url: str, body: dict, ua: str, key: str | None, campaign: str) -> dict:
    headers = {"Content-Type": "application/json", "User-Agent": ua}
    if key:
        headers["X-Demo-Truth"] = f"{key}:{campaign}"
    req = urllib.request.Request(url.rstrip("/") + "/api/trial/signup", data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as exc:
        return {"action": "error", "message": f"HTTP {exc.code}: {exc.read()[:200].decode(errors='replace')}"}
    except urllib.error.URLError as exc:
        return {"action": "error", "message": str(exc.reason)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("url", help="trial site, e.g. https://trial.example.com or http://127.0.0.1:8000")
    p.add_argument("--key", help="demo key, so the dashboard can keep score")
    p.add_argument("--campaigns", default="naive-bot,alias-farm,stealth-farm", help="comma-separated, in order")
    p.add_argument("--include-miss", action="store_true", help="also run the human-like campaign we expect to miss")
    p.add_argument("--speed", type=float, default=1.0, help="2 = twice as fast")
    p.add_argument("--pause", type=float, default=6.0, help="seconds between campaigns")
    p.add_argument("--seed", type=int)
    args = p.parse_args(argv)
    rng = random.Random(args.seed)
    names = [c.strip() for c in args.campaigns.split(",") if c.strip()]
    if args.include_miss and "humanlike" not in names:
        names.append("humanlike")
    unknown = [n for n in names if n not in CAMPAIGNS]
    if unknown:
        p.error(f"unknown campaign(s): {', '.join(unknown)}. Choose from {', '.join(CAMPAIGNS)}")

    totals = {}
    for c_i, name in enumerate(names):
        items = list(CAMPAIGNS[name](rng))
        print(colour(f"\n== {name}: {len(items)} signups ==", "bold"))
        tally = {"block": 0, "review": 0, "allow": 0, "error": 0}
        for i, (body, ua, delay) in enumerate(items, 1):
            r = post(args.url, body, ua, args.key, name)
            action = r.get("action", "error")
            tally[action] = tally.get(action, 0) + 1
            label = colour(f"{action.upper():<6}", action if action in COLOURS else "dim")
            reason = (r.get("reasons") or [r.get("message", "")])[0] if action != "allow" else ""
            print(f"[{name} {i:>2}/{len(items)}] {body['email']:<40} {label} {colour(reason, 'dim')}")
            time.sleep(delay / args.speed)
        totals[name] = tally
        print(colour(f"   at signup: {tally['block']} blocked, {tally['review']} review, {tally['allow']} got in"
                     + (f", {tally['error']} errors" if tally["error"] else ""), "dim"))
        if c_i < len(names) - 1:
            time.sleep(args.pause / args.speed)

    print(colour("\nSummary at signup time (the dashboard also shows accounts caught afterwards):", "bold"))
    for name, t in totals.items():
        sent = sum(t.values())
        print(f"  {name:<14} sent {sent:>3}   blocked {t['block']:>3}   review {t['review']:>3}   got in {t['allow']:>3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
