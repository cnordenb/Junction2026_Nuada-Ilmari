# Free-tier guard

Finds swarms of fake signups on a free plan: bot networks and account farms that open many accounts for phishing, spam or resource abuse. Hostinger shut its free hosting brand (000webhost) in 2024. Free tiers everywhere attract this kind of abuse. Fits the challenge direction "Spot the swarm", applied to signups instead of posts.

Dashboard page: `/signups`. Command line: `python scripts/signup_guard.py data/signups/demo_signups.csv --label-col label`.

## What is in the repository

| Path | What it is |
|---|---|
| `scripts/signup_guard.py` | The detector: per-signup checks, linking, swarm verdicts, evaluation against an answer key |
| `scripts/signup_lists.py` | Built-in lists: throwaway email domains, free mail providers, hosting and VPN networks, automation browsers |
| `scripts/eval_signups.py` | Runs the detector on 5 fresh and 5 "hard" simulated streams; writes `data/signups/evaluation.json` |
| `data/make_signup_data.py` | Generates the simulated signup stream with planted abuse, innocent look-alikes and an answer key (`--hard` for smarter attackers) |
| `data/signups/demo_signups.csv` | The demo stream (seed 7), 3,546 signups |
| `dashboard/static/signups.html` | The page: live signup test, stream analysis, accuracy, how it decides |
| `tests/test_signups.py` | 15 tests |

## Input

One signup per row. Required: a time (`created_at`) and an `email`. Optional, and every check that needs one is skipped and reported when it is missing: `username`, `ip`, `asn`, `asn_org`, `user_agent`, `device_id` (a browser fingerprint from the signup page).

## How it decides

**1. Per-signup checks.** Each check adds points and a plain-language reason.

| Check | Points |
|---|---|
| Throwaway inbox service | 45 |
| Several accounts on one real inbox (Gmail ignores dots; many providers ignore +tags) | 50 |
| Browser identifies as an automation tool | 50 |
| One device behind 5 or more accounts | 35 |
| Datacenter or VPN network (weak on purpose: privacy-minded people use VPNs) | 10 |
| Device check did not run, when most signups have one | 10 |

60 or more: block. 35 or more: review.

**2. Linking.** Two signups are linked when the details they share add up to 2.0 or more. Weights: device 3, real inbox 3, email pattern 1.2 (`user48213@mailinator.com` gives `a9{5}@mailinator.com`), exact browser build 1, IP 1, organisation email domain 1, username pattern 0.8, /24 address block 0.8, network (ASN) 0.6. A detail shared by more than 3% of all signups is ignored, because it is not evidence: gmail.com, the current Chrome version, a big home-internet provider. Groups of 5 or more linked signups are scored.

**3. Group timing.** The team's synchrony scorer (`sync_score.py`) compares each group's timing with 4,000 random groups of the same size from the same stream. It looks for a tight burst, near-constant intervals (a timer), the same minute of each hour, or the same time every day.

**4. Group verdict.**

- Shared organisation email domain, no shared devices or inboxes, low risk: **organisation**, sent to review and never blocked.
- Average per-signup risk 40 or more: **block**.
- Shared identity details (device, inbox, email pattern, automation browser) and timing 30 or more: **block**.
- Shared network or exact browser build and timing 50 or more: **block**.
- Weaker combinations: **review**. Otherwise: **allow**.

A member of a blocked group is blocked only if it carries the group's evidence itself: two of the shared details, or the only one. Members that joined the group through a looser link go to review.

## Measured accuracy

Simulated streams written by our team. They show the logic does what it is designed to do and where it breaks. They are **not** a measurement on a real platform.

**Five fresh streams (seeds 1 to 5, not the seed the detector was designed against):**

| | |
|---|---|
| Precision when blocking | 100% (750 of 750) |
| Abusive accounts blocked | 85.7% (750 of 875) |
| Real people blocked | 0% (0 of 16,864) |
| Real people sent to review | 1.52% (256 of 16,864), 200 of them the class and company signups |

**Five hard streams.** The attackers use throwaway domains missing from our list, normal browsers, 20 devices instead of 4, and looser timing:

| | |
|---|---|
| Precision when blocking | 100% |
| Abusive accounts blocked | 73.7% (645 of 875) |
| Real people blocked | 0% |

Per campaign, standard streams:

| Group in the answer key | Signups | Blocked | Review |
|---|---|---|---|
| abuse_tempmail_burst: script, throwaway inboxes, headless browser, cloud server | 225 | 225 | 0 |
| abuse_alias_farm: 2 Gmail inboxes behind 24 accounts | 120 | 120 | 0 |
| abuse_proxy_farm: residential proxies, every IP different, 4 devices | 300 | 300 | 0 |
| abuse_daily_drip: 3 accounts a night from one rented server | 105 | 105 (hard: 0 blocked, 105 review) | 0 |
| abuse_slow_humanlike: copies ordinary users in every field | 125 | **0** | 0 |
| trap_classroom: 28 students, one IP, one Chromebook build, 25 minutes | 140 | 0 | 140 |
| trap_team_onboarding: 12 colleagues, one office IP | 60 | 0 | 60 |
| trap_promo_burst: 150 people within 90 minutes of a newsletter | 750 | 0 | 1 |
| trap_family: 2-3 accounts on one laptop | 464 | 0 | 3 |
| trap_vpn: privacy-VPN users | 450 | 0 | 2 |
| background: ordinary signups | 15,000 | 0 | 50 |

Rerun with `python scripts/eval_signups.py` (about 5 seconds).

## Known limits

- **A careful human-like operator is not caught.** One who varies every recorded detail and signs up at ordinary times (abuse_slow_humanlike) looks like ordinary people to us.
- **Spreading a nightly batch over several hours** drops it from block to review on the hard streams.
- **Classes and company teams cost a human review.** That is deliberate: we would rather ask than block a school.
- **Lists are small built-in snapshots.** Production needs the maintained throwaway-domain list and an IP-to-network database. See `signup_lists.py`.
- **The live demo has no IP-to-network lookup,** so the datacenter or VPN check only runs on files that include an `asn` column.
- **The device check on the demo page is deliberately simple** (a hash of a few browser properties). Real deployments would use a fingerprinting library such as ThumbmarkJS or FingerprintJS v5 (both MIT).
- **Everything is simulated, and the simulator was written by the people who wrote the detector.** A real labelled signup log is the next step.

## Live demo

`/signups`, section 1. Your test signups are added to the end of the demo's ordinary signups and the whole stream is re-analysed, in about half a second. Sign up once normally, then try to farm: five quick signups from one browser, throwaway inboxes, or Gmail dot and +tag variants of one address. Each browser session sees only its own test signups. They are kept in memory only and deleted after two hours (100 per session at most).

Behind a reverse proxy, set `SIGNUP_TRUST_PROXY=1` so the real client IP is read from `X-Forwarded-For`. Only do this when the proxy overwrites that header, or clients can spoof it.
