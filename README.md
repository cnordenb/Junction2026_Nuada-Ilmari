# Swarm detector

Junction 2026, Hostinger challenge. A tool that finds groups of posts or comments that are both **similar in text** and **synchronised in time**: the footprint of brigading, astroturfing and bot networks.

It flags patterns for a person to review. It does not identify who is behind a post.

How it works, measured accuracy and known limits: [docs/swarm-detector.md](docs/swarm-detector.md).

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

1. Choose a dataset from the list (files in `data/`) or upload your own.
2. Optionally paste a few posts you already find suspicious.
3. Press **Find swarms**.

To load the demo dataset and run it straight away, open
http://127.0.0.1:8000/?dataset=demo_posts.csv&labels=label&run=1

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

An `id` column is used if present; otherwise rows are numbered. Rows with empty content or an unreadable time are skipped and counted in the output.

`data/demo_posts.csv` is a synthetic dataset with planted swarms and an answer key in the `label` column. Regenerate it with:

```powershell
.venv\Scripts\python data\make_demo_data.py
```

## Run the tests

```powershell
.venv\Scripts\python -m pytest
```

35 tests covering both scores, the detector on the demo dataset and the dashboard API. They take about 15 seconds.

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
| `scripts/` | `similarity_score.py`, `sync_score.py`, `detect_swarm.py` and shared helpers |
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
