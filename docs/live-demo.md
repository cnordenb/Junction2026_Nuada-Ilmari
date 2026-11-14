# Live demo runbook

## The three pages

| Laptop | Page | Address |
|---|---|---|
| 1 | **Sargas dashboard**: live scores per person (ticket, factors, AI opinion), swarms with AI summaries, review queue, IP bans, accuracy on labelled data, QR code | https://guard.botswarm.tech |
| 2 | **Neighbr signup** ("Tinder for horses"). Judges sign up on their own phones via the QR code and see their live bot score | https://botswarm.tech |
| 3 | **Attack console**: paste the demo key, press Launch. Each campaign sends a fixed number of signups and stops | https://attack.botswarm.tech |

Backup addresses (same server): `guard.`, `trial.` and `attack.179-67-199-198.sslip.io`.

The demo key is in `deploy/.env` (not in git): `grep GUARD_DEMO_KEY deploy/.env | cut -d= -f2`.

## Before each group of judges

- Console: **Reset demo** (click twice). Clears live signups, bans and AI summaries.
- Attack laptop on a **phone hotspot**, judges on **their own phones** (mobile data if the venue wifi is slow).

## Campaigns on the console

| Campaign | Signups | What it shows |
|---|---|---|
| naive-bot | 12 | Throwaway inbox, hidden field, no mouse: blocked at once; its IP is banned after 2 accounts and the rest bounce at the door. |
| alias-farm | 10 | One Gmail inbox with dots and +tags, a script fills the form (no mouse/typing): blocked from the 5th. |
| stealth-farm | 15 | Realistic names, new proxy IP each time, robotic mouse, 3 devices. The first few get in; when the group forms, all are blocked, earlier ones included ("caught after signup"). IP bans cannot stop it. |
| humanlike | 6 | Replays human input with varied details. Our honest miss: it gets in. |

## What is live and what is not

- Live: every signup and verdict, re-judging, IP bans, behaviour signals, d1 factor and second opinions, LFM3 summaries.
- Not shown as users: two weeks of simulated past signups used only as the timing baseline.
- Live signups (including real emails and IPs) are stored on the VPS until Reset. Delete everything after the event: `docker compose --env-file deploy/.env -f deploy/docker-compose.yml down -v`.

## Deploy or update

On the VPS in `/opt/botswarm`: `docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d --build`. Services: `app` (FastAPI), `llm` (llama.cpp + d1-omni-600M), `lfm` (llama.cpp + LFM3-VL-2B), `caddy` (HTTPS for every host in `SITE_HOSTS`).
