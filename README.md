# Sargas

Sargas spots bot-nets by looking at **groups of signups**, stopping the fake accounts behind propaganda and free-trial abuse. Built for the Hostinger challenge at Junction 2026.

- **Against propaganda:** astroturfing, brigading and fake reviews need thousands of fake accounts. Sargas stops them at signup.
- **For site owners:** bot-nets exploit free trials. Sargas blocks the swarm, including accounts that already got in.

## Live demo

**[demo.botswarm.tech](https://demo.botswarm.tech)** links all three sites:

| Site | What it is |
|---|---|
| [botswarm.tech](https://botswarm.tech) | Neighbr, a satirical "Tinder for horses" with a free tier, protected by Sargas. Sign up to see your live bot score and its reasons. |
| [guard.botswarm.tech](https://guard.botswarm.tech) | The Sargas dashboard: every signup's score and reasons, detected groups with AI summaries, review queue, IP bans, test results. |
| [attack.botswarm.tech](https://attack.botswarm.tech) | Attack console (demo key needed): launch bot campaigns against Neighbr and watch them get caught. |

## How it works

1. **Check each signup:** inbox tricks, a hidden form field, form-filling speed, mouse and typing rhythm, network latency.
2. **Link the group:** signups that share rare details (a device, an inbox, an email template, a browser build) are linked.
3. **Test the timing:** each group's arrival times are compared with 4,000 random groups from the same stream.
4. **Decide and explain:** every signup gets a score from 0 to 100 with a reason for every point.

The score is a logistic model with hand-set weights:

```
score = 100 / (1 + e^-z)        z = -4 + Σ weight × factor        (each factor 0 to 1)
```

0–34 allow · 35–59 review · 60+ block. There are 18 factors: the signup itself, behaviour on the page, an AI check on the email address, and the linked group (size, shared details, timing). Natural human movement and school or company groups lower the score. An IP behind 2 or more blocked accounts is banned at the door; each ban can be switched off or reset on the dashboard.

Weights were set by how strong each piece of evidence is, then checked on labelled test logs that mix bot campaigns with innocent look-alikes (a school class on one IP, a company team, families sharing a laptop, VPN users, a newsletter rush), and tested on attackers we did not tune for.

## Results

On 10 labelled test logs ([scripts/eval_signups.py](scripts/eval_signups.py)): **0 of 16,864 real people blocked, 85.7% of bots blocked**, AUC 0.93. Known miss: a bot that copies human behaviour closely.

## AI

Two open models run on the server with llama.cpp, so no user data leaves it. Benchmarked on labelled data ([data/bench/](data/bench/)):

| Job | Done by | Result |
|---|---|---|
| Block / review / allow | The formula | 0 of 60 real people flagged (the models as judges: d1 17, LFM3 10) |
| Spot machine-made email addresses | Liquid AI d1-omni-600M | AUC 0.80; a factor in the score |
| Sort the review queue | Formula + d1 second opinion | ranking AUC 0.90 → 0.94 |
| Summarise each group in plain words | Liquid AI LFM3-VL-2B | shown on the dashboard, never changes a verdict |

## Tech

Python and FastAPI · NumPy and SciPy for the statistics · SQLite · llama.cpp with Liquid AI models · Docker Compose and Caddy for automatic HTTPS · a Hostinger KVM 2 VPS and the domain botswarm.tech, both from Hostinger.

## Run locally

Python 3.12 (also tested on 3.15).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
GUARD_DEMO_KEY=dev .venv/bin/python -m uvicorn dashboard.app:app
```

Open http://127.0.0.1:8000/trial (signup), `/guard` (dashboard) and `/attack` (console, key `dev`). Without the AI models running, their factor and summaries are left out.

```bash
.venv/bin/python -m pytest                                                # tests
.venv/bin/python scripts/eval_signups.py                                  # accuracy on 10 test logs
python3 scripts/attack_demo.py http://127.0.0.1:8000 --key dev            # attack from the command line
```

## Deploy

On a server with Docker, from the repository root:

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d --build
```

`deploy/.env` (not in git) sets `GUARD_DEMO_KEY`, `SITE_HOSTS` (every hostname that gets HTTPS), `NEIGHBR_HOSTS` (hostnames that open on the signup page) and `GUARD_SIM_EVERY=0`. Services: `app` (FastAPI), `llm` (d1-omni-600M), `lfm` (LFM3-VL-2B), `caddy` (HTTPS). Demo runbook: [docs/live-demo.md](docs/live-demo.md).

## Repository

| Path | Contents |
|---|---|
| `scripts/signup_guard.py` | the detector: checks, linking, timing test, score |
| `dashboard/live.py` | live signup API, dashboard state, IP bans, attack console, AI worker |
| `dashboard/static/` | `trial.html` (Neighbr), `guard.html` (dashboard), `attack.html` (console), `demo.html` (landing page) |
| `data/make_signup_data.py` | generates the labelled test logs |
| `scripts/bench_d1.py`, `scripts/bench_meta.py` | AI benchmarks |
| `deploy/` | Docker Compose, Caddyfile |
| `docs/` | [SUBMISSION.md](docs/SUBMISSION.md), [Sargas.pptx](docs/Sargas.pptx), [signup-guard.md](docs/signup-guard.md), [DEVLOG.md](docs/DEVLOG.md) |

## Also here: post swarm detector

Finds groups of posts that are similar in text and synchronised in time, and types the accounts behind them. Page `/` on a local run. Usage: [docs/post-detector.md](docs/post-detector.md); method and accuracy: [docs/swarm-detector.md](docs/swarm-detector.md).
