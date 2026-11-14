# DEVLOG

## 2026-11-13

**21:26:26** Read CLAUDE.md (Hostinger challenge brief). `materials.md` exists but is empty, so no links could be taken from it.

**21:30:00** Created `suggestion.md` with a proposed project, roles and timeline.
- Decision (proposed, not yet agreed by the team): build "Name the technique" (explainable manipulation-technique classifier for pasted text) with a public accuracy page; "Trust the source" only as an optional add-on.
- Decision (proposed): non-technical team member takes the role of evaluation and story lead (test set, technique definitions, false-positive review, pitch, mentor liaison, submission).
- Question: was `materials.md` meant to contain links? It needs to be saved or filled in.
- Question: is the SemEval-2020 Task 11 corpus accessible and licensed for our use? Not verified.
- Deadline noted: Sunday 2026-11-15 10:00 EET.

## 2026-11-14

**10:29:29** Updated `suggestion.md`: replaced the non-technical member's task list with five tasks built around UI/UX and diagrams (result-screen wireframe, how-it-works diagram, technique cards, usability and false-positive testing, accuracy page and pitch).
- Decision (proposed): bulk test-set labelling, mentor liaison and submission text move to the three technical members.
- Question: who among the technical members owns the labelled test set now?

**11:31:34** New idea from the team: example-based detector (user enters five posts, system extracts common signs and scans a larger dataset). Feedback given in chat, nothing built.
- Proposed implementation: LLM extracts explicit signs from the five examples contrasted with a background sample; embedding similarity ranks the dataset; LLM checks top candidates against the signs with quoted evidence; user confirm/reject loop.
- Question: does this replace 'Name the technique' or not? Team must choose one today.
- Question: which dataset to scan and evaluate on? Candidate: FiveThirtyEight Russian troll tweets mixed with ordinary tweets (not verified).

**11:33:26** Created `brainstorm.md` with the example-based detector idea, its analysis, a possible implementation and a comparison with 'Name the technique'.

**11:34:45** Added to `brainstorm.md`: visitor origin and VPN detection with origin-based restrictions (GeoIP, ASN, Tor and VPN lists, signal mismatches; firewall, nginx, app middleware and softer responses; analysis of false positives and privacy).
- Question: standalone tool, or a signal inside another idea?
- Not verified: licences and freshness of the free GeoIP and VPN lists.

**14:25:25** Built a swarm detector ("Spot the swarm" direction) for datasets of posts with content and time posted. Overview and measurements in `docs/swarm-detector.md`.
- Added `scripts/similarity_score.py` (100 = identical, 0 = completely different), `scripts/sync_score.py` (100 = same instant, 0 = far apart with no pattern), `scripts/detect_swarm.py` (combines them), `scripts/swarm_common.py`.
- Added the Claude Code skill `.claude/skills/swarm-detect/`, the dashboard `dashboard/` (FastAPI plus one page), `data/demo_posts.csv` with its generator, `tests/test_swarm.py` (35 tests, passing), `Dockerfile`, requirements files, `.gitignore`.
- Decision (from the user): dataset has only content and time; lexical similarity by default with optional semantic mode; manually added posts act as seeds; run locally, ready for the VPS.
- Decision: similarity = average of word-level and character-level TF-IDF cosine. Chosen over embeddings as the default because it needs no model and same-topic posts do not score as similar.
- Decision: synchrony is scored against random groups from the same dataset, and counts only above the level 1 in 1,000 random groups reach. First version used the 95th percentile and flagged 12 small organic clusters by luck on the demo data.
- Decision: minimum cluster size 5, and the timer, hourly and daily patterns need 8 posts. Smaller groups produced chance hits.
- Decision: the dashboard server only opens files from `data/` or its own uploads, never a path from the browser, because it will be public.
- Result on the synthetic demo data: precision 81.2%, recall 89.0%, false-positive rate 0.7%. Misses the reworded swarm (also in semantic mode); flags the innocent daily greeting.
- Installed sentence-transformers and PyTorch into `.venv` to test semantic mode; the model is cached under the user profile.
- Not done: Docker image not built (Docker daemon was not running); nothing deployed; no test on real data.
- Question: which real labelled dataset do we evaluate on? The numbers above are from data we generated ourselves.
- Question: does this become the team's main build, alongside or instead of the Glasshouse traffic work in `links.md`?
- Updated `docs/suggestion.md` links section with the six links now in `docs/materials.md` (not opened or checked).
- Note: the markdown files were moved into `docs/` by someone else; this log continues there.

**14:35:13** Added `README.md` at the repository root: requirements, setup, running the dashboard and scripts, dataset format, tests, optional semantic mode, Docker deployment and settings, troubleshooting.
- Note: Python requirement stated as 3.12 because that is the only version tested.

**14:48:07** Team decision (from Tom, after talking to Hostinger): focus on preventing free tiers from being exploited by bot networks and astroturfing. Hostinger closed its free hosting brand (000webhost) in 2024; the mentor reacted positively to the idea. Started the signup version of the swarm detector on branch `signup-guard`.
- Decision: reuse the team's synchrony scorer (`sync_score.py`) for group timing; replace text similarity with weighted shared signup details (device, real inbox, email and username pattern, browser build, IP, /24, ASN).
- Decision: details shared by more than 3% of signups are ignored for linking (gmail.com, current Chrome, big ISPs are not evidence).
- Decision: network evidence is weak on purpose (VPN users, offices, schools). Blocking needs shared identity details plus unusual timing, or high per-signup risk.
- Decision: a shared organisation email domain without shared devices or inboxes is treated as a school or company: review, never block.
- Decision: a member of a blocked group is blocked only if it carries the group's evidence itself; looser members go to review. Before this, one ordinary person who happened to share an email pattern was blocked with the nightly batch.
- Decision: the built-in throwaway-domain and hosting-ASN lists are small hand-typed snapshots so the demo works offline; `SIGNUP_DISPOSABLE_FILE` loads a maintained list. Nothing was downloaded.
- Fix in the simulator: ordinary people now always get unique inboxes after Gmail normalisation. Before, the generator gave two different people `inesjones@gmail.com` and `ines.jones@gmail.com`, which Gmail would never do, and the inbox-reuse check flagged them.

**15:09:04** Added `data/make_signup_data.py` (simulated stream with 5 abuse campaigns, 5 innocent look-alike types, answer key; `--hard` for attackers using tricks the detector was not tuned on), `scripts/signup_guard.py`, `scripts/signup_lists.py`, `scripts/eval_signups.py`, the `/signups` page and `/api/signups/*` endpoints, `tests/test_signups.py` (15 tests; 50 total passing), `docs/signup-guard.md`, a link from the post-swarm page.
- Result, 5 fresh streams: block precision 100%, recall 85.7%, 0 of 16,864 real people blocked, 1.52% sent to review (mostly the class and company traps).
- Result, 5 hard streams: block precision 100%, recall 73.7%; the nightly batch drops to review when spread over several hours.
- Known miss, by design: `abuse_slow_humanlike` (an operator who varies every detail) is never caught.
- Live demo: each browser session's test signups are added to the demo's ordinary signups and re-analysed (~0.5 s); stored in memory only, per session, deleted after 2 hours.
- Note: developed on macOS with Python 3.15 (only 3.15 and 3.11 available locally); pinned requirements installed and all tests pass.
- Not done: not deployed; Docker image still not built; no real signup data; live demo has no IP-to-network lookup.
- Question: should `/` show the signup guard instead of the post detector, now that it is the main direction?
- Question: can Hostinger share any (anonymised) signup or abuse data to evaluate on?

**15:51:29** Built the live demo for the in-person review (request from Tom: a normal small-business site with a free trial, attacked live, plus a dashboard of the whole event; not static).
- Added `dashboard/live.py`: trial signup API, SQLite store, re-judging of the recent stream on every signup (so a farm is caught as it grows and earlier accounts are suspended), background simulated customers, dashboard state, demo reset. `dashboard/static/trial.html` (fictional "Ruska Bookings"), `dashboard/static/guard.html` (live dashboard, polls every 1.2 s), `scripts/attack_demo.py` (standard library only; campaigns naive-bot, alias-farm, stealth-farm, humanlike), `tests/test_live.py` (8 tests; 58 total passing), `deploy/` (Docker Compose with Caddy for HTTPS on the bare domain and the trial and guard subdomains, plus a deploy script), `docs/live-demo.md`.
- Decision: subdomains `trial.` and `guard.` are served by the same app (routing by Host header), so one container and one database.
- Decision: the trial form collects live-only signals: hidden honeypot field, time to fill the form, `navigator.webdriver`, a device hash including a canvas drawing. Added to `signup_guard.py` as honeypot (60), webdriver (50), fast fill under 1.5 s (30). No password field.
- Decision: the attack script labels its requests with `X-Demo-Truth` (needs `GUARD_DEMO_KEY`) for the scoreboard only; the detector never sees it. Reasons are returned only to labelled attack requests, never to ordinary visitors.
- Decision: a blocked group's member must carry one of the group's identity details (device, inbox, email pattern, throwaway, automation) to be blocked. Found in testing: a real visitor on the attacker's IP and browser was blocked with the farm. Simulated evaluation numbers are unchanged.
- Decision: emails are masked on the dashboard; live signups stay in a SQLite file on the server until reset.
- Built the Docker image for the first time (locally) and attacked the running container: 27 of 27 attack signups blocked, simulated customers allowed.
- Local run of the full attack: naive-bot 12/12 blocked at signup; alias-farm 6 blocked at signup, all 10 in the end; stealth-farm 11 blocked at signup, 4 caught afterwards; humanlike 6 review only because all attacks share one IP.
- Not done: deployment. Waiting for the Hostinger account and domain.
- Question: which domain name, and who holds the VPS login?

**17:26:24** Judges' feedback (via Tom): scoring every user with a stated reason, on the forged bot activity logs, counts as testing. They want live per-user scores on the dashboard, and people on their phones should see their own score change live.
- Added a bot score (0 to 100) per signup in `signup_guard.py`: the stronger of the per-signup points and the group verdict (block 90, review 55, organisation 40). Every point comes with its reason. Documented as a ranking score with stated rules, not a calibrated probability.
- Added a graded signal: 2 to 4 accounts on one device score 5 points per extra account (families share devices, so it stays weak). 5 or more is the existing device-farm signal.
- `eval_signups.py` now measures the score on the 10 forged logs: AUC 0.92 (standard and hard), with no real people at 70 or more (0 of 16,864). At 70 or more, 85.7% of bots (hard logs: 73.7%). Mean score per group is in the table; the human-like operator scores 0, like real people.
- Live demo: every signup gets a 4-character ticket and a private token. The trial page shows "your live bot score", with reasons, a gauge and a history line, polling every 2 s (`/api/trial/status`). The dashboard lists people by ticket with live scores and points per reason, a live score histogram by source, and the forged-log test results.
- Decision: `GUARD_SHOW_SCORE=1` (default) shows people their own score and reasons for the demo. A real site would turn it off, because it teaches attackers what is checked.
- Tests: 61 passing.

**18:19:02** Deployed to the Hostinger VPS (179.67.199.198, Ubuntu 26.04, Docker 29 already installed) with `deploy/docker-compose.yml` from `/opt/botswarm`.
- Access with a dedicated SSH key (Tom installed it with ssh-copy-id); no password used by the agent. The root password was shared in chat and should be changed.
- The demo key lives in `deploy/.env` on the server and locally (git-ignored).
- Domain botswarm.site shows Active in hPanel but the .site registry has no delegation yet (WHOIS: available; Let's Encrypt: NXDOMAIN). Caddy was paused to avoid Let's Encrypt failure limits.
- Decision: serve on `179-67-199-198.sslip.io` meanwhile (wildcard DNS to the server's IP), with real Let's Encrypt certificates. Live now: https://trial.179-67-199-198.sslip.io and https://guard.179-67-199-198.sslip.io. A watcher on Tom's Mac switches Caddy to botswarm.site once all three names resolve.
- Tested from outside over the internet: attack from this Mac, 27 of 27 attack signups blocked (4 caught after signup), 11 of 11 simulated customers allowed; dashboard updated live. Also tested inside the container: 37 of 37. Live data reset afterwards.
- Question: why has botswarm.site not reached the registry? Ask the Hostinger booth if it is still missing.

**18:29:14** Demo setup for the peer review (Tom): three pages, only real people plus a bot swarm launched on demand.
- Added the attack console (`dashboard/static/attack.html`, `/attack`, `attack.<domain>`): unlock with the demo key, launch one campaign at a time (naive-bot 12, alias-farm 10, stealth-farm 15, humanlike 6 signups), see each verdict, score and reason, stop, reset. The server runs the campaign and posts to its own public signup API over HTTP; each launch sends a fixed number and stops.
- Decision: simulated customers switched off in production (`GUARD_SIM_EVERY=0`), so the dashboard shows only real visitors and the launched swarm. The two-week simulated history stays as the timing baseline only and is no longer shown as users; the dashboard says so.
- Dashboard: the score formula replaces the simulated-customer tile.
- Deployed: https://trial.179-67-199-198.sslip.io, https://guard.179-67-199-198.sslip.io, https://attack.179-67-199-198.sslip.io (Caddy now also serves `attack.`). Live check: naive-bot 12 of 12 blocked at score 100, no simulated users; reset to 0 afterwards. Tests: 62 passing.
- Note: if botswarm.site starts resolving, an `attack` A record is also needed.
