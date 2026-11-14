---
name: swarm-detect
description: Detect inauthentic or suspicious swarm behaviour (brigading, astroturfing, bot networks, copy-paste campaigns) in a dataset of posts or comments that has content and a time posted. Use when asked to check a dataset for coordinated posting, to score how similar posts are or how synchronised their timing is, to find posts like a few suspicious examples, or to measure the detector's precision and false-positive rate on labelled data.
---

# Swarm detection

Coordinated campaigns leave two footprints that single posts do not: many posts
with **similar text**, posted in a **synchronised** way. This skill scores both
and flags groups that have both. Three scripts in `scripts/` do the work:

| Script | Score | Scale |
|---|---|---|
| `similarity_score.py` | text similarity | 100 = identical (ignoring case, punctuation, spacing), 0 = no shared words or character runs |
| `sync_score.py` | temporal synchrony | 100 = same instant, 0 = far apart with no timing pattern beyond chance |
| `detect_swarm.py` | swarm score = sqrt(similarity x synchrony) | needs both to be high |

Run them with the project's Python: `.venv/Scripts/python.exe` on Windows,
`.venv/bin/python` elsewhere. If there is no `.venv`, create one and
`pip install -r requirements.txt`.

## Workflow

1. **Look at the data first.** Open the file's first rows. Find the content
   column and the time column; the scripts guess them by name, so pass
   `--text-col` / `--time-col` when the guess could be wrong. Formats: CSV,
   TSV, JSON array, JSON Lines. Times: ISO dates or Unix epochs, taken as UTC
   when no zone is given; ambiguous dates like 3/4/2026 are read month first.
2. **Run the detector.**
   ```
   python scripts/detect_swarm.py <file>
   python scripts/detect_swarm.py <file> --seed "text of a suspicious post" --seed "another one"
   ```
   Seeds are optional example posts: the detector reports the posts that match
   them and whether those matches are synchronised.
3. **Read the notes it prints** (rows skipped, rows cut off, a time window that
   is too wide for the data) and pass them on.
4. **Read the flagged clusters, then read their posts.** The scores say a
   pattern exists; only the text says whether it matters. For each flagged
   cluster ask whether an innocent cause fits (see "False positives").
5. **Check what was let through.** The report lists the largest similar-text
   clusters that were not flagged because their timing is ordinary.
6. **Report** as described under "Reporting".

Use `--json` or `--out report.json` for the full report (every cluster, all
post ids). If the data has a ground-truth column, add `--label-col <name>` to
get precision, recall and false-positive rate.

## Settings that matter

- `--threshold` (default 60): similarity needed to link two posts. 85+ is
  near-verbatim copying; 60 to 85 is the same template with words swapped;
  below 50 mostly links posts that merely share common phrases.
- `--half-life` (default `10m`): the time gap at which two posts score 50.
  Match it to the platform: seconds to minutes for live comment threads, an
  hour or more for slow forums. If the detector warns that random groups
  already look synchronised, shorten it.
- `--min-size` (default 5): smallest cluster reported. Going lower multiplies
  chance hits.
- `--min-chars` (default 20): shorter posts ("lol", "thanks!") are never clustered.
- `--semantic`: also compares meaning with a small embedding model (needs
  `pip install -r requirements-semantic.txt`, about a minute per 5,000 posts
  on a laptop CPU). It catches light rewording. It does not catch the same
  point made in entirely different words.

## How the scores work

**Similarity.** Average of two cosine similarities over TF-IDF vectors: words
and word pairs, and character sequences of length 3 to 5. Unrelated posts in
the same language usually score under 15. Posts are linked when they score at
or above the threshold, linked posts form clusters, and a cluster whose
distinct texts are too loosely related on average is split with a tighter
threshold, so one bridging post cannot merge two unrelated groups.

**Synchrony.** Two posts: `100 x 0.5^(gap / half-life)`. A cluster gets four
measurements: `burst` (each post's closeness to the nearest other post in the
cluster, averaged), `regular` (constant intervals, like a timer), `hourly`
(same minute of the hour) and `daily` (same time of day); the last three need
at least 8 posts. Each is compared with 4,000 random groups of the same size
drawn from the dataset's own timeline. The "chance level" is the value only 1
in 1,000 random groups reach, and the score is how far the cluster rises above
it. A cluster that looks like chance scores 0, however busy the dataset is.
The synchrony score is the highest of the four and names its pattern.

**Verdicts.** `strong`: swarm score 70+, 8+ posts. `moderate`: swarm score
45+. `low`: similar text, ordinary timing; not flagged.

## The single-score scripts

```
python scripts/similarity_score.py pair "text a" "text b"
python scripts/similarity_score.py dataset <file> --top 20 --out similarity.csv
python scripts/sync_score.py pair "2026-11-14 10:00:00" "2026-11-14 10:04:30" --half-life 10m
python scripts/sync_score.py dataset <file>                 # background timing and unusually busy windows
python scripts/sync_score.py dataset <file> --ids 17,42,99  # score one group against the rest
```

The `dataset` form of `similarity_score.py` gives each post its best score
against any other post. The `dataset` form of `sync_score.py` without `--ids`
describes the whole timeline; that is the background level, not evidence of
coordination.

## False positives

Similar and synchronised is what coordination looks like, and also what these
look like. Check each flagged cluster against them:

- **Greetings and rituals**: "good morning" at 8:00 every day scores as a daily pattern.
- **Breaking news and live events**: many people react at once, sometimes in near-identical words.
- **Quotes, memes, copypasta jokes, song lyrics, chants.**
- **Platform or tool output**: "[removed]", auto-moderator notices, share-button text ("I just signed this petition").
- **Giveaways and replies to a prompt** ("comment YES to enter").
- **One author**: with no account column, one person reposting their own text
  looks the same as many accounts. Say so; do not assume many accounts.

What the detector misses: campaigns that reword every post, campaigns spread
thinly over time with no pattern, and anything under the minimum cluster size.

## Reporting

- Lead with what was found: how many clusters were flagged, how many posts,
  out of how many analysed, with the settings used.
- For each flagged cluster give its size, both scores, the timing pattern, the
  time range, one or two example posts, and your reading of whether an
  innocent cause fits.
- Describe patterns, not people. Write "40 near-identical posts within six
  minutes", not "a bot network". Never call an individual post or author a bot
  on this evidence; the scores cannot show who is behind a post.
- State the limits that apply: no account ids, lexical matching only (unless
  `--semantic` was used), rows skipped.
- If labels were available, report precision, recall and false-positive rate
  with the counts behind them.

## Dashboard

The same detection runs behind a web page: `uvicorn dashboard.app:app`, then
open http://127.0.0.1:8000. Datasets placed in `data/` appear in its list;
others can be uploaded. `data/demo_posts.csv` is a synthetic dataset with
planted swarms and an answer key (`label` column); regenerate it with
`python data/make_demo_data.py`. Tests: `python -m pytest`.
