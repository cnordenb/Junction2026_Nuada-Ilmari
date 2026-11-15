# Post swarm detector: usage

Finds groups of posts that are similar in text and synchronised in time, and types the accounts behind them. How it decides and its measured accuracy: [swarm-detector.md](swarm-detector.md).

## Run the dashboard

```bash
.venv/bin/python -m uvicorn dashboard.app:app
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

```bash
# Full detection, with accuracy against the demo answer key
.venv/bin/python scripts/detect_swarm.py data/demo_posts.csv --label-col label

# Look for posts like one or more examples
.venv/bin/python scripts/detect_swarm.py data/demo_posts.csv --seed "text of a suspicious post"

# The two scores on their own
.venv/bin/python scripts/similarity_score.py pair "first text" "second text"
.venv/bin/python scripts/sync_score.py pair "2026-11-14 10:00:00" "2026-11-14 10:04:30"
.venv/bin/python scripts/similarity_score.py dataset data/demo_posts.csv --top 20
.venv/bin/python scripts/sync_score.py dataset data/demo_posts.csv
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

```bash
.venv/bin/python data/make_demo_data.py
```

## Optional: semantic mode

Compares meaning as well as wording, which catches lightly reworded copies. It is much slower (about a minute per 5,000 posts on a laptop).

```bash
.venv/bin/pip install -r requirements-semantic.txt
.venv/bin/python scripts/detect_swarm.py data/demo_posts.csv --semantic
```

Once installed, the option also appears in the dashboard under "More options".

## Troubleshooting

- **"Could not tell which column holds the content"**: pass `--text-col` and `--time-col`, or pick the columns in the dashboard.
- **Rows skipped because the time could not be read**: check the time column's format against "Dataset format" above.
- **"More than 3,000,000 pairs of texts score ... or higher"**: the similarity threshold is too low for this dataset; raise it.
- **A note that random groups already look synchronised**: the posts are packed closely in time; use a shorter `--half-life`.
- **Port already in use**: start uvicorn with `--port 8080`.
