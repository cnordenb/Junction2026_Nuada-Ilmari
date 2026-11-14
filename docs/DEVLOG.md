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
