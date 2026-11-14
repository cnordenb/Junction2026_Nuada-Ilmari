# Swarm detector

Finds groups of posts or comments that are both similar in text and synchronised in time: the footprint of brigading, astroturfing and bot networks. Fits the challenge direction "Spot the swarm". The dataset needs only two fields: content and time posted.

## What is in the repository

| Path | What it is |
|---|---|
| `scripts/similarity_score.py` | Text similarity score, 100 = identical, 0 = completely different |
| `scripts/sync_score.py` | Temporal synchrony score, 100 = same instant, 0 = far apart with no pattern |
| `scripts/detect_swarm.py` | Combines the two: clusters similar posts, scores each cluster's timing, flags clusters that have both |
| `scripts/swarm_common.py` | Shared loading, time parsing and text normalisation |
| `dashboard/` | Web dashboard (FastAPI plus one HTML page) |
| `.claude/skills/swarm-detect/` | Claude Code skill that drives the scripts and sets rules for reporting |
| `data/demo_posts.csv` | Synthetic dataset with planted swarms and an answer key |
| `data/make_demo_data.py` | Generates the demo dataset |
| `tests/test_swarm.py` | Tests for the scores, the detector and the dashboard API |

## Run it

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt      (Windows; use .venv/bin/pip elsewhere)

.venv\Scripts\python -m uvicorn dashboard.app:app      then open http://127.0.0.1:8000
.venv\Scripts\python scripts\detect_swarm.py data\demo_posts.csv --label-col label
.venv\Scripts\python -m pytest
```

A link that loads the demo dataset and runs it straight away: `http://127.0.0.1:8000/?dataset=demo_posts.csv&labels=label&run=1`

Put other datasets in `data/` to have them listed in the dashboard, or upload them in the page.

## Deploy on the Hostinger VPS

```
docker build -t swarm-detector .
docker run -d --restart unless-stopped -p 80:8000 --name swarm swarm-detector
```

The Docker image has not been built or run yet (Docker was not running on the machine where this was written). Settings, all optional environment variables: `SWARM_MAX_ROWS` (default 20000), `SWARM_MAX_UPLOAD_MB` (30), `SWARM_MAX_CONCURRENT` (2 analyses at once), `SWARM_ALLOW_SEMANTIC` (set to 0 to hide semantic mode), `SWARM_DATA_DIR`.

The server only opens files from its own `data/` folder or uploads it stored itself; it never opens a path sent by the browser. Uploads are deleted after two hours. There is no login and no rate limit beyond the limit on simultaneous analyses, and no HTTPS: put it behind a reverse proxy (Caddy or nginx) for the public URL.

## How it decides

1. **Similarity.** Average of two cosine similarities over TF-IDF vectors: words and word pairs, and character runs of length 3 to 5. Case, punctuation and spacing are ignored.
2. **Clusters.** Posts scoring 60 or more against each other are linked. A linked group whose distinct texts are too loosely related on average is split again with a tighter threshold.
3. **Synchrony.** Each cluster's timing gets four measurements: bunched together, constant intervals, same minute of the hour, same time of day. Each is compared with 4,000 random groups of the same size from the same dataset. The score is how far the cluster rises above the level only 1 in 1,000 random groups reach, so a busy dataset does not make everything look synchronised.
4. **Swarm score** = sqrt(similarity x synchrony). Strong: 70 or more with at least 8 posts. Moderate: 45 or more. Everything else is listed as "similar text, ordinary timing" and not flagged.

## Measured on the demo dataset

4,411 synthetic posts, 146 of them in five planted swarms. Default settings, lexical matching.

| | |
|---|---|
| Precision | 81.2% (130 of 160 flagged posts were in a planted swarm) |
| Recall | 89.0% (16 swarm posts missed) |
| False-positive rate | 0.7% (30 of 4,265 innocent posts flagged) |

| Group in the answer key | Posts | Flagged | |
|---|---|---|---|
| Copy-paste brigade, 6 minutes | 40 | 40 | found |
| Template astroturfing, two waves | 36 | 36 | found |
| Timer bot, every 30 minutes | 30 | 30 | found |
| Clock bot, top of random hours | 24 | 24 | found |
| Same message reworded, 10 minutes | 16 | 0 | **missed**, also in semantic mode |
| Innocent: same greeting every morning | 30 | 30 | **false positive** (same time of day) |
| Innocent: one quote repeated at random times | 25 | 0 | correctly ignored |
| Innocent: 60 different reactions to one event in 15 minutes | 60 | 0 | correctly ignored |
| Innocent: ordinary chatter and short replies | 4,150 | 0 | correctly ignored |

These numbers come from data we made ourselves, so they show the method does what it is designed to do; they do not show how it performs on real platforms. Measuring that needs a real labelled dataset.

Speed on a laptop: about 4 seconds for 4,411 posts and 43 seconds for 20,411 posts. Semantic mode took about a minute for 4,411 posts.

## Known limits

- **No account IDs.** One person reposting their own text looks the same as many accounts acting together.
- **Rewording defeats it.** The reworded swarm in the demo is missed in both modes. Semantic mode lifts lightly reworded copies over the threshold (one test pair went from 49 to 61), but posts making the same point in entirely different words score like ordinary same-topic discussion.
- **Innocent synchronised repetition is flagged.** Daily greetings, and anything else people repeat on a schedule.
- **The demo dataset is synthetic** and was written by the same people as the detector.
- **Thresholds are judgement calls** (similarity 60, half-life 10 minutes, minimum 5 posts, the verdict cut-offs). They have not been tuned on real data.
- **Size.** Every post is compared with every other, so time grows with the square of the dataset. The dashboard analyses the first 20,000 rows of larger files.
