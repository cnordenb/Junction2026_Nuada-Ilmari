# Sargas

**Sargas** (Lithuanian for *guard*) catches swarms of fake signups on free tiers and explains every verdict. Junction 2026, Hostinger challenge ("Spot the swarm", with parts of "Clean the traffic").

Propaganda online runs on fake accounts: astroturfing, brigading and fake engagement all need many accounts that each look real. Those accounts come from free tiers, and the site owners who run them pay for it in burned resources, spam and phishing under their name. Sargas judges **groups of accounts**, not single requests: one device behind 15 "different people", one inbox spelled ten ways, one email template, signups faster than chance. Farms that slip in are caught as the group grows, and their earlier accounts are suspended.

## Live (Hostinger VPS)

| | |
|---|---|
| **https://botswarm.tech** | Neighbr, a satirical "Tinder for horses" with a free tier: the site Sargas protects. Sign up and watch your own live bot score. |
| **https://guard.botswarm.tech** | Sargas dashboard: live scores per person with every factor, swarms found, review queue, IP bans, accuracy on labelled data. |
| **https://attack.botswarm.tech** | Attack console (demo key): launch fixed-size bot campaigns against Neighbr. |

## How it decides

One published equation, 18 factors, each measured from 0 to 1:

    bot score = 100 / (1 + e^-z),   z = -4 + sum(weight x factor)        0-34 allow, 35-59 review, 60+ block

- **Signup:** throwaway inbox, same inbox under other spellings, automation browser, hidden field filled, form filled too fast, device reused, device check missing, datacenter/VPN, machine-made name.
- **Behaviour on the page:** no mouse/touch/typing, robotic movement or typing, natural movement (lowers the score), latency too low for a person.
- **AI:** Liquid AI's d1-omni-600M (on the server, llama.cpp) judges whether the email looks machine-made.
- **Group:** size of the linked group, how much of the group's shared details this signup has, group timing against 4,000 random groups, school/company group (lowers the score).

Weights are set by hand and published; it is a ranking score with stated rules, not a probability. IP addresses behind 2+ blocked accounts are banned at the door (each ban can be switched off or reset).

## AI where it measurably helps

We benchmarked two on-server models on labelled data (`data/bench/`) and use each only where it beat the algorithm:

| Job | Who | Evidence |
|---|---|---|
| Block / review / allow | **Algorithm** | AUC 0.90, 82% of bots, 0 of 60 people flagged. As judges, d1 flagged 17 people and LFM3-VL-2B 10. |
| Email looks machine-made | **d1** (score factor, weight 1.0) | AUC 0.80; name/bio prompts were near chance and are not used. |
| Ranking the review queue | **Algorithm + d1 blend** | Ranking AUC 0.90 -> 0.94, same decisions. |
| Plain-language swarm summaries | **LFM3-VL-2B** | Reads well; shown next to the facts, never changes a verdict. |

## Measured accuracy (forged logs with an answer key)

10 simulated signup logs, including smarter attackers we did not tune for, and innocent look-alikes (a class on one campus IP, a company team, families on one laptop, VPN users, a newsletter rush): **0 of 16,864 real people blocked, 85.7% of bots blocked**, AUC 0.93. Known miss: a careful bot that varies every detail and replays human input. Details: [docs/signup-guard.md](docs/signup-guard.md). Demo runbook: [docs/live-demo.md](docs/live-demo.md). Decisions and dead ends: [docs/DEVLOG.md](docs/DEVLOG.md).

```bash
.venv/bin/python -m pytest                          # 69 tests (one needs a live d1 server)
.venv/bin/python scripts/eval_signups.py            # accuracy on 10 forged logs
python3 scripts/attack_demo.py https://botswarm.tech --key <demo key>   # attack from a laptop
```

## Also in this repository

**Post swarm detector** (page `/` on a local run, details in [docs/swarm-detector.md](docs/swarm-detector.md)): Junction 2026, Hostinger challenge. A tool that finds groups of posts or comments that are both **similar in text** and **synchronised in time**, and types the **accounts** behind them by behaviour: the footprint of brigading, astroturfing and bot networks.

## Requirements

- **Python 3.12** (developed and tested on 3.12.9, Windows 11). Older versions have not been tried.
- About 370 MB of disk for the virtual environment with the core and test dependencies.
- Optional: Docker, for deployment.
- Optional: about 850 MB more disk and an internet connection for semantic mode (PyTorch plus a small model downloaded on first use).

Python packages, pinned in the requirements files:

| File | Contents | Needed for |
|---|---|---|
| `requirements.txt` | numpy, scipy, scikit-learn, pandas, fastapi, uvicorn | scripts and dashboard |
| `requirements-dev.txt` | the above plus pytest and httpx | running the tests |
| `requirements-semantic.txt` | sentence-transformers (pulls in PyTorch) | optional semantic mode |

## Set up

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
```

macOS or Linux:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

The commands below use the Windows path `.venv\Scripts\python`. On macOS or Linux use `.venv/bin/python` instead.

## Run the dashboard

```powershell
.venv\Scripts\python -m uvicorn dashboard.app:app
```

Open http://127.0.0.1:8000, then:

1. Choose a dataset from the list (files in `data/`) or upload your own, and check the content, time and account columns.
2. Optionally paste a few posts you already find suspicious.
3. Press **Find swarms**.

The setup then folds away and the results appear in tabs:

| Tab | Shows |
|---|---|
| Overview | The headline, how a group gets flagged, and a bubble chart of every group by similarity and synchrony |
| Groups | Each flagged group with its evidence: a strip of when its posts were made, a clock grid, and the posts. A second list holds groups with similar text but ordinary timing |
| Accounts | Accounts by behaviour type, and for each account its four signals, posting times and posts |
| Timing | Posts over time, and weekday-by-hour heatmaps for all posts and flagged posts |
| Sample matches | Posts like the samples you added (only when you added some) |
| Accuracy | Precision, recall and false-positive rate for posts and accounts (only with an answer-key column) |
| Limits | Notes about the run, what the result cannot tell you, and what was let through |

To load the demo dataset and run it straight away, open
http://127.0.0.1:8000/?dataset=demo_posts.csv&labels=label&run=1
(add `&tab=groups`, `&tab=accounts` and so on to open a specific tab).

Add `--reload` to the uvicorn command while editing code, and `--port 8080` to use another port.

## Run from the command line

```powershell
# Full detection, with accuracy against the demo answer key
.venv\Scripts\python scripts\detect_swarm.py data\demo_posts.csv --label-col label

# Look for posts like one or more examples
.venv\Scripts\python scripts\detect_swarm.py data\demo_posts.csv --seed "text of a suspicious post"

# The two scores on their own
.venv\Scripts\python scripts\similarity_score.py pair "first text" "second text"
.venv\Scripts\python scripts\sync_score.py pair "2026-11-14 10:00:00" "2026-11-14 10:04:30"
.venv\Scripts\python scripts\similarity_score.py dataset data\demo_posts.csv --top 20
.venv\Scripts\python scripts\sync_score.py dataset data\demo_posts.csv
```

Every script has `--help`. Useful options on `detect_swarm.py`:

| Option | Default | Meaning |
|---|---|---|
| `--text-col`, `--time-col` | guessed from column names | which columns hold the content and the time posted |
| `--account-col` | a column named `account`, `author`, `user_id` or similar, if present | which column says who wrote each post; `none` to skip account types |
| `--threshold` | 60 | similarity (0 to 100) needed to link two posts |
| `--half-life` | `10m` | time gap at which two posts score 50 for synchrony (`30s`, `10m`, `2h`, `1d`) |
| `--min-size` | 5 | smallest group to report |
| `--label-col` | none | answer-key column; prints precision, recall and false-positive rate |
| `--json`, `--out FILE` | off | full report as JSON |
| `--semantic` | off | also compare meaning (needs the optional install below) |

## Dataset format

One post per row, in CSV, TSV, JSON (a list of objects) or JSON Lines. Two columns are required:

- **Content**: the text of the post or comment.
- **Time posted**: an ISO date such as `2026-11-14 10:00:00` or `2026-11-14T10:00:00Z`, or a Unix timestamp. Times without a zone are read as UTC. Ambiguous dates such as `3/4/2026` are read month first.

One column is optional but recommended:

- **Account**: who wrote the post (a name or an id). With it, each flagged group says how many accounts are behind it, and each account gets a behaviour type: automated-looking, repetitive, swarm participant, single-purpose, occasional participant, no signals, or too few posts to judge. Without it, one person reposting their own text looks the same as many accounts acting together.

An `id` column is used if present; otherwise rows are numbered. Rows with empty content or an unreadable time are skipped and counted in the output.

`data/demo_posts.csv` is a synthetic dataset with planted swarms, accounts and an answer key in the `label` column. Regenerate it with:

```powershell
.venv\Scripts\python data\make_demo_data.py
```

## Run the tests

```powershell
.venv\Scripts\python -m pytest
```

Tests cover the post detector and account types (Carl), the signup guard, the live demo, the d1 prompts and the dashboard API.

## Optional: semantic mode

Compares meaning as well as wording, which catches lightly reworded copies. It is much slower (about a minute per 5,000 posts on a laptop).

```powershell
.venv\Scripts\pip install -r requirements-semantic.txt
.venv\Scripts\python scripts\detect_swarm.py data\demo_posts.csv --semantic
```

Once installed, the option also appears in the dashboard under "More options".

## Deploy with Docker

```bash
docker build -t swarm-detector .
docker run -d --restart unless-stopped -p 80:8000 --name swarm swarm-detector
```

The image has not been built or run yet, so treat the `Dockerfile` as untested. It installs the core dependencies only; semantic mode is not included.

Optional environment variables for the dashboard (pass with `-e NAME=value`):

| Variable | Default | Meaning |
|---|---|---|
| `SWARM_MAX_ROWS` | 20000 | rows analysed per dataset; larger files are cut to the first rows |
| `SWARM_MAX_UPLOAD_MB` | 30 | largest upload accepted |
| `SWARM_MAX_CONCURRENT` | 2 | analyses allowed at once |
| `SWARM_ALLOW_SEMANTIC` | 1 | set to 0 to hide semantic mode |
| `SWARM_DATA_DIR` | `data/` | folder of datasets offered in the list |
| `SWARM_UPLOAD_DIR` | system temp folder | where uploads are stored (deleted after two hours) |

The dashboard has no login, no rate limit beyond the limit on simultaneous analyses, and no HTTPS. Put it behind a reverse proxy such as Caddy or nginx for a public URL.

## Project layout

| Path | Contents |
|---|---|
| `scripts/` | `similarity_score.py`, `sync_score.py`, `detect_swarm.py`, `account_types.py` and shared helpers |
| `dashboard/` | FastAPI app (`app.py`) and the page (`static/index.html`) |
| `data/` | demo dataset and its generator |
| `tests/` | test suite |
| `.claude/skills/swarm-detect/` | Claude Code skill for running the detector and reporting results |
| `docs/` | design notes, development log, brainstorm and plan |

## Troubleshooting

- **"Could not tell which column holds the content"**: pass `--text-col` and `--time-col`, or pick the columns in the dashboard.
- **Rows skipped because the time could not be read**: check the time column's format against "Dataset format" above.
- **"More than 3,000,000 pairs of texts score ... or higher"**: the similarity threshold is too low for this dataset; raise it.
- **A note that random groups already look synchronised**: the posts are packed closely in time; use a shorter `--half-life`.
- **Port already in use**: start uvicorn with `--port 8080`.
