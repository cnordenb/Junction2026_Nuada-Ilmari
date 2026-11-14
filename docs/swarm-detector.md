# Swarm detector

Finds groups of posts or comments that are both similar in text and synchronised in time: the footprint of brigading, astroturfing and bot networks. Fits the challenge direction "Spot the swarm". The dataset needs only two fields: content and time posted. With a third, optional field saying which account wrote each post, it also counts the accounts behind each group and gives every account a behaviour type.

## What is in the repository

| Path | What it is |
|---|---|
| `scripts/similarity_score.py` | Text similarity score, 100 = identical, 0 = completely different |
| `scripts/sync_score.py` | Temporal synchrony score, 100 = same instant, 0 = far apart with no pattern |
| `scripts/detect_swarm.py` | Combines the two: clusters similar posts, scores each cluster's timing, flags clusters that have both |
| `scripts/account_types.py` | Four signals per account and a behaviour type; used by `detect_swarm.py` when the data has an account column |
| `scripts/swarm_common.py` | Shared loading, time parsing and text normalisation |
| `dashboard/` | Web dashboard (FastAPI plus one HTML page). Results are in tabs: Overview, Groups, Accounts, Timing, Sample matches, Accuracy, Limits |
| `.claude/skills/swarm-detect/` | Claude Code skill that drives the scripts and sets rules for reporting |
| `data/demo_posts.csv` | Synthetic dataset with planted swarms, accounts and an answer key |
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

## Account types

Only when the dataset has an account column. Each flagged group then says how many accounts wrote it ("40 different accounts", "all from one account"), and each account gets four signals from 0 to 100:

| Signal | Measures | Needs |
|---|---|---|
| `schedule` | Posts at constant intervals, at the same minute of the hour, or at the same time of day. Scored against random groups from the dataset, like group synchrony | 8 posts |
| `no_pause` | No daily quiet period. A longest quiet period of 8 hours or more scores 0, 2 hours or less scores 100 | 30 posts over 3 days |
| `repetition` | How similar the account's own posts are to each other | 3 posts |
| `swarm` | Share of its posts that sit in flagged groups | 1 post |

The type is the first rule that matches:

| Type | Rule | Flagged |
|---|---|---|
| Automated-looking | `schedule` or `no_pause` is 50 or more | yes |
| Repetitive | `repetition` is at or above the similarity threshold | yes |
| Swarm participant | 3 or more posts, at least half in flagged groups | yes |
| Single-purpose | 1 or 2 posts, all in flagged groups | yes |
| Occasional participant | Some posts in flagged groups, fewer than half | no |
| No signals | 3 or more posts, nothing unusual | no |
| Too few posts to judge | 1 or 2 posts, none flagged | no |

A type describes behaviour in this dataset. It is not a verdict of "bot" or "human": a news feed, a scheduling tool and a person who says good morning at eight every day are all automated-looking. A single-purpose account is only suspicious because of the group it sits in. Accounts with too few posts are unjudged, not cleared.

## Measured on the demo dataset

4,483 synthetic posts from 879 accounts, 146 of the posts in five planted swarms. Default settings, lexical matching.

Posts:

| | |
|---|---|
| Precision | 81.3% (130 of 160 flagged posts were in a planted swarm) |
| Recall | 89.0% (16 swarm posts missed) |
| False-positive rate | 0.7% (30 of 4,337 innocent posts flagged) |

Accounts (an account counts as a swarm account when most of its posts are in a planted swarm; 77 are):

| | |
|---|---|
| Precision | 93.8% (61 of 65 accounts with a flagged type were swarm accounts) |
| Recall | 79.2% (16 swarm accounts missed, all from the reworded swarm) |
| False-positive rate | 0.5% (4 of 802 innocent accounts: the three morning greeters and the news feed) |

Of the 65 flagged accounts, 7 are automated-looking and 58 are single-purpose. None came out as repetitive, swarm participant or occasional participant, so the demo data does not exercise those three types; they are covered by unit tests only. The other accounts: 443 with no signals, 371 with too few posts to judge.

| Group in the answer key | Posts | Flagged | Accounts behind it | |
|---|---|---|---|---|
| Copy-paste brigade, 6 minutes | 40 | 40 | 40, one post each | found |
| Template astroturfing, two waves | 36 | 36 | 18, two posts each | found |
| Timer bot, every 30 minutes | 30 | 30 | 1 | found; reported as one account repeating itself, not a group |
| Clock bot, top of random hours | 24 | 24 | 2 | found |
| Same message reworded, 10 minutes | 16 | 0 | 16 | **missed**, also in semantic mode |
| Innocent: same greeting every morning | 30 | 30 | 3 | **false positive** (same time of day) |
| Innocent: one quote repeated at random times | 25 | 0 | | correctly ignored |
| Innocent: 60 different reactions to one event in 15 minutes | 60 | 0 | | correctly ignored |
| Innocent: news feed posting round the clock | 72 | 0 | 1 | posts correctly ignored; the account is typed automated-looking, which is accurate but counts as an account false positive |
| Innocent: ordinary chatter and short replies | 4,150 | 0 | | correctly ignored |

These numbers come from data we made ourselves, so they show the method does what it is designed to do; they do not show how it performs on real platforms. Measuring that needs a real labelled dataset. The synthetic accounts are also simpler than real ones: every ordinary account was given a seven-hour sleep window, and every swarm account posts nothing outside its swarm.

Speed on a laptop: a full command-line run on the 4,483 posts took 17 seconds including start-up and account typing. Before account typing was added, the analysis alone took about 4 seconds for 4,411 posts and 43 seconds for 20,411 posts; the larger size has not been timed again. Semantic mode took about a minute for 4,411 posts.

## Known limits

- **Without an account column**, one person reposting their own text looks the same as many accounts acting together, and no account is typed.
- **Account types are behaviour, not intent.** Benign automation (news feeds, scheduled posts, service bots) and people with daily routines are typed automated-looking. Four of the 65 flagged accounts in the demo are innocent for this reason.
- **Throwaway accounts cannot be judged alone.** An account with one or two posts is only flagged through the group it posts in, so if the group is missed, so are its accounts (the 16 reworded-swarm accounts in the demo).
- **Account names are personal data.** The dashboard shows them as they appear in the file. Uploads are deleted after two hours, but nothing is pseudonymised.
- **Rewording defeats it.** The reworded swarm in the demo is missed in both modes. Semantic mode lifts lightly reworded copies over the threshold (one test pair went from 49 to 61), but posts making the same point in entirely different words score like ordinary same-topic discussion.
- **Innocent synchronised repetition is flagged.** Daily greetings, and anything else people repeat on a schedule.
- **The demo dataset is synthetic** and was written by the same people as the detector.
- **Thresholds are judgement calls** (similarity 60, half-life 10 minutes, minimum 5 posts, the verdict cut-offs). They have not been tuned on real data.
- **Size.** Every post is compared with every other, so time grows with the square of the dataset. The dashboard analyses the first 20,000 rows of larger files.
