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

**16:02:20** Added account types to the swarm detector, rebuilt the dashboard around tabs, and wrote a plan for real-time AI integration.
- Request (from the user): show output more pedagogically (less scrolling, more tabs, more kinds of graph), focus on account type for bot detection, and outline real-time AI integration and automation in rainstorm.md as a plan only.
- Assumption, not confirmed with the user: "account type" means a behaviour-based type worked out from an optional account column, not a type supplied by a platform (verified, business, and so on).
- Added scripts/account_types.py: four signals per account (schedule, 
o_pause, epetition, swarm) and seven types. Flagged types: automated-looking, repetitive, swarm participant, single-purpose. Not flagged: occasional participant, no signals, too few posts to judge.
- Changed scripts/swarm_common.py (optional account column, found by name), scripts/detect_swarm.py (accounts per group, account summary, weekday-by-hour activity, --account-col), dashboard/app.py (ccount_col).
- Changed data/make_demo_data.py and regenerated data/demo_posts.csv: now 4,483 posts from 879 accounts, with an ccount column, three bot accounts, three innocent morning greeters and one innocent round-the-clock news feed.
- Rewrote dashboard/static/index.html: the setup folds into a summary bar after a run; results are in tabs (Overview, Groups, Accounts, Timing, Sample matches, Accuracy, Limits); groups and accounts use a list with a detail pane. New charts: bubble chart of groups by similarity and synchrony, stacked timeline, weekday-by-hour heatmaps, strip plot of post times, clock grid, measured-versus-chance bars, account-type bars.
- Decision: a type describes behaviour, not intent. "Automated-looking" is kept apart from "malicious" in the code, the page, the skill and the docs, because news feeds, scheduling tools and people with daily routines all look automated.
- Decision: accounts with one or two posts are never typed on their own. They are flagged only through the group they post in (single-purpose), or left as "too few posts to judge".
- Decision: gave the synthetic ordinary accounts a seven-hour sleep window. Without it the heaviest ordinary posters had no quiet period and were typed automated-looking, which was a flaw in the fake data rather than something the detector should be tuned around. Real accounts will be messier than this.
- Result on the synthetic demo data, posts: precision 81.3%, recall 89.0%, false-positive rate 0.7% (unchanged counts: 130 right, 30 wrong, 16 missed).
- Result on the synthetic demo data, accounts: 65 of 879 flagged (7 automated-looking, 58 single-purpose); precision 93.8%, recall 79.2%, false-positive rate 0.5%. The 4 wrong ones are the three greeters and the news feed. The 16 missed are the accounts of the reworded swarm.
- Fixed: the dashboard showed post precision as 81.3% and the command line as 81.2% (130 of 160 is exactly 81.25%). Both now round halves up, and ratios are stored to 6 decimals instead of 4 so they are not rounded twice. Earlier entries in this log say 81.2%; same counts.
- Tests: 41, passing (was 35).
- Updated README.md, docs/swarm-detector.md and the skill .claude/skills/swarm-detect/SKILL.md for the above.
- Added to docs/brainstorm.md: "Plan: real-time AI integration and automation, built on the swarm detector prototype" (live ingest in small batches, where an LLM through the Hostinger AI Router helps and where it must not decide, real-time account signals, four levels of automation with a person approving anything that removes posts or blocks accounts, phases A to D, risks). Plan only; nothing in it is built.
- Checked by eye in headless Chrome: all seven tabs, plus the Groups tab at narrow width and a run without an account column.
- Not verified: the repetitive, swarm participant and occasional participant types never occur in the demo data, so they are covered by unit tests only. Speed at 20,000 rows has not been timed since account typing was added (4,483 rows: 17 seconds for a full command-line run).
- Not done: Docker image still not built; nothing deployed; no test on real data; nothing committed.
- Question: is the behaviour-based reading of "account type" what was meant?
- Question: account names are personal data. Do we pseudonymise them in the dashboard before it goes public?
- Question (still open): which real labelled dataset do we evaluate on, and is this the team's main build?

**17:59:28** ub-mode pass, status so far (nothing committed).
- Done: every function is under CRAP 10 (worst 9.0, `load_dataset`); dryer at threshold 0.8 finds no duplicates. Refactors were pinned by 18 golden CLI outputs that stayed byte-identical, plus new `tests/test_cli.py` (suite: 59 tests).
- Tooling notes: crapper and mutator need a pytest coverage command passed in (their default finds no tests); crapper installed `coverage` into `.venv`.
- Mutation testing is NOT done. Run 1 was invalid: 530 of 578 mutants "survived" because tests and `dashboard/app.py` found the code with `Path(__file__).resolve()`, which follows the mutation worker's symlinks back to the unmutated files. Changed to `.absolute()` in `tests/test_swarm.py`, `tests/test_cli.py`, `dashboard/app.py`; a three-mutant trial was then killed. Run 2 (all 578 sites) was stopped by Claude Code because the machine ran low on memory; it produced no results.
- Not rerun after the `.absolute()` change: full pytest suite, golden comparison, crapper, dryer.
- Open: rerun mutation testing with fewer workers (`--max-workers 3` or so) when memory allows; add `.metrics/` and `target/` to `.gitignore`; update test counts in README and docs.
