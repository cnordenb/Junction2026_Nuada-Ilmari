# Live demo runbook

A fictional small business, **Ruska Bookings**, offers a 14-day free trial. Free-Tier Guard judges every trial signup the moment it arrives, and re-judges the recent stream each time, so a farm that looked fine at first is caught and its earlier accounts suspended as it grows. One laptop attacks the site over the internet; another shows the dashboard.

| Address | What it is |
|---|---|
| `https://trial.<domain>` | The business site with the trial form. Judges can sign up from their phones. |
| `https://guard.<domain>` | The live dashboard: scoreboard, signups per 30 s, swarms found, live feed. |
| `https://<domain>` | The analysis tools: post swarm detector, `/signups` page. |

Locally the same pages are at `http://127.0.0.1:8000/trial` and `/guard`.

## What is live and what is simulated

- **Live:** every trial signup (yours, the judges', the attack script's), every verdict, re-judging, retroactive suspension, the dashboard.
- **Simulated, and labelled as such on the dashboard:** two weeks of ordinary signups loaded as history, so the timing tests have a baseline, and a stream of "ordinary customers" (one every 20 s on average, `GUARD_SIM_EVERY`) so there is normal traffic around the attack.
- **The scoreboard's answer key:** the attack script sends a header with its campaign name (`X-Demo-Truth`, checked against `GUARD_DEMO_KEY`). It is stored for the scoreboard only and never given to the detector. Anything without it counts as a real visitor.
- **What the trial form collects:** a device hash (browser properties and a canvas drawing), how long the form took, the browser's automation flag, and a hidden field people never see. No passwords. The page says to use any address; nothing is sent.

## Live bot scores

Every signup gets a **bot score from 0 to 100** with the points and reason behind it. The score is the stronger of the per-signup checks and the verdict of the group the signup belongs to (block 90, review 55, organisation 40). Under 35 is allowed, 35 to 59 goes to review, 60 and over is blocked. It is a ranking score with stated rules, not a calibrated probability.

- **On the phone:** after signing up, the trial page shows your ticket (e.g. `VCXN`), your live score, the reasons and how the score has moved. It updates every 2 seconds. Sign up again from the same phone and watch it climb.
- **On the dashboard:** every person by ticket with their live score, the points per reason, and "score at signup → now" when a farm is caught later. Also a live histogram of scores by source, and the results on the forged logs.
- **Tested on forged bot activity logs** (`scripts/eval_signups.py`, 10 logs with an answer key): AUC 0.92; 0 of 16,864 people score 70 or more; 85.7% of bots do (73.7% on hard logs).

## Deploy (Hostinger VPS)

1. DNS: point `A` records for `<domain>`, `trial.<domain>` and `guard.<domain>` at the VPS IP.
2. On the VPS (Docker template), with the repository checked out:
   ```bash
   DOMAIN=<domain> GUARD_DEMO_KEY=$(openssl rand -hex 12) bash deploy/deploy.sh
   ```
   Write the key down; the attack laptop needs it. Caddy fetches HTTPS certificates automatically once DNS resolves.
3. Check from a phone on mobile data: `https://trial.<domain>` and `https://guard.<domain>`.

The image was built and attacked locally (Docker on macOS) before deployment: 27 of 27 attack signups blocked, simulated customers allowed.

## Demo setup (three laptops)

| Laptop | Shows |
|---|---|
| 1 | `trial.<domain>`, the business site. Judges sign up here, or scan the QR code on the dashboard with their own phone (better: each phone is its own device). |
| 2 | A terminal running the attack. **Use a phone hotspot**, not the venue wifi, so judges and attacker don't share an IP address. |
| 3 | `guard.<domain>`, full screen. |

Attack (laptop 2, Python 3.9+ only, no installs):
```bash
python3 scripts/attack_demo.py https://trial.<domain> --key <GUARD_DEMO_KEY>
python3 scripts/attack_demo.py https://trial.<domain> --key <KEY> --include-miss   # also the campaign we expect to miss
python3 scripts/attack_demo.py https://trial.<domain> --key <KEY> --campaigns stealth-farm --speed 2
```

Reset between demos (deletes live signups, keeps history):
```bash
curl -X POST -H "X-Demo-Key: <KEY>" https://guard.<domain>/api/guard/reset
```

## A 90-second script

1. Laptop 3: "This is a small booking company's free trial, watched live." Point at the simulated customers trickling in and being allowed.
2. Invite a judge to sign up on laptop 1 or their phone. It is allowed.
3. Laptop 2: start the attack.
   - **naive-bot:** blocked on its own signals (throwaway inbox, hidden field filled).
   - **alias-farm:** one Gmail inbox, dots and +tags. Review from the 2nd account, blocked from the 5th.
   - **stealth-farm:** each account looks fine alone. The first four get in. On the fifth the group forms: one email pattern, one stale browser build, 3 devices, timing faster than chance. Everything is blocked, and the dashboard shows "4 caught after signup".
4. Point at the swarm panel: the reasons are in plain language.
5. Honest close: run `--include-miss` or name it. A careful operator who varies everything gets through when they use residential proxies. In this demo it lands in review only because every attack comes from one laptop's IP.

## What we measured in this setup (local run, 2026-11-14)

| Campaign | Sent | Blocked at signup | Final |
|---|---|---|---|
| naive-bot | 12 | 12 | 12 blocked |
| alias-farm | 10 | 6 (3 review, 1 in) | all 10 blocked |
| stealth-farm | 15 | 11 (4 in) | all 15 blocked |
| humanlike | 6 | 0 (6 review) | review, through the shared IP only |

## Known limits of the live setup

- No IP-to-network lookup on the server yet, so the datacenter/VPN check does not run on live signups.
- All attack traffic comes from one laptop. Real farms rotate residential IPs. That case is covered in the simulated evaluation (`docs/signup-guard.md`), not here.
- Judges signing up one after another on the **same** demo laptop share a device. From the fifth on they look like a device farm. That is correct behaviour, but use phones.
- One server process re-judges about 3,400 history rows plus live signups on each signup (about 0.3 to 0.5 s). Fine for a demo. A busy site would re-judge in batches.
