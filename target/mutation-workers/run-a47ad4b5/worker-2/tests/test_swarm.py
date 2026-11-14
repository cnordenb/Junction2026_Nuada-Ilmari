"""Tests for the scoring scripts, the combined detector and the dashboard API.

Run from the repository root:  python -m pytest
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from account_types import classify, longest_daily_quiet_hours  # noqa: E402
from detect_swarm import analyse  # noqa: E402
from similarity_score import SimilarityIndex, find_clusters, pair_similarity, score_dataset  # noqa: E402
from swarm_common import (guess_columns, load_dataset, normalise, parse_duration, parse_times,  # noqa: E402
                          read_table)
from sync_score import SyncScorer, find_bursts, group_sync, nearest_sync, pair_sync  # noqa: E402

DEMO = ROOT / "data" / "demo_posts.csv"


# ---------------------------------------------------------------- similarity

def test_identical_texts_score_100():
    assert pair_similarity("Share this before they delete it", "Share this before they delete it") == 100.0


def test_case_punctuation_and_spacing_are_ignored():
    assert pair_similarity("The vote was RIGGED!!!", "the vote   was rigged") == 100.0


def test_unrelated_texts_score_near_zero():
    a = "The council vote on the harbour development was rigged from the start"
    b = "My grandmother's soup recipe smells exactly like childhood summers"
    assert pair_similarity(a, b) < 15
    assert pair_similarity("quick brown fox", "12345 67890") == 0.0      # no shared words or letter runs


def test_small_edit_scores_between_and_is_symmetric():
    a = "The vote was rigged, share this now before they delete it"
    b = "The vote was rigged, repost this now before they delete it"
    score = pair_similarity(a, b)
    assert 60 < score < 100
    assert score == pytest.approx(pair_similarity(b, a), abs=1e-3)


def test_empty_text_scores_zero():
    assert pair_similarity("", "") == 0.0
    assert pair_similarity("...", "hello there") == 0.0


def test_normalise_keeps_letters_of_any_script_and_emoji():
    assert normalise("  Hyvää   HUOMENTA, kaikille!  ") == "hyvää huomenta kaikille"
    assert normalise("so true🔥🔥") == "so true 🔥 🔥"


def test_score_dataset_reports_copies_and_nearest():
    texts = ["buy cheap followers today only", "Buy cheap followers TODAY only!", "the ferry was late again this morning",
             "buy cheap followers today only, trusted by thousands"]
    result = score_dataset(texts, threshold=50)
    per = result["per_post"]
    assert per["max_similarity"][0] == 100.0 and per["nearest"][0] == 1 and per["nearest"][1] == 0
    assert per["exact_copies"].tolist() == [1, 1, 0, 0]
    assert per["max_similarity"][2] < 20
    assert per["nearest"][3] in (0, 1)


def test_loose_chains_are_split_into_tight_clusters():
    # A~B and B~C but A and C share nothing: must not end up as one cluster.
    a = "alpha bravo charlie delta echo foxtrot golf hotel"
    c = "india juliet kilo lima mike november oscar papa"
    b = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa"
    # Many exact copies must not hide the split.
    texts = [a] * 30 + [c] * 10 + [b]
    index = SimilarityIndex(texts, use_idf=False)
    assert index.block([index.inverse[0]], [index.inverse[40]])[0, 0] > 60       # a~b linked
    assert index.block([index.inverse[0]], [index.inverse[30]])[0, 0] < 5        # a, c unrelated
    clusters = find_clusters(index, index.scan(60), threshold=60, min_size=3)
    assert len(clusters) == 2
    assert sorted(c["size"] for c in clusters)[0] in (10, 11) and sorted(c["size"] for c in clusters)[1] in (30, 31)


# ---------------------------------------------------------------- synchrony

def test_pair_sync_scale():
    assert pair_sync(1000, 1000) == 100.0
    assert pair_sync(0, 600, half_life=600) == pytest.approx(50.0)
    assert pair_sync(0, 86400, half_life=600) < 1e-6


def _background(n=3000, days=10, seed=1):
    return np.sort(np.random.default_rng(seed).uniform(0, days * 86400, n))


def test_simultaneous_group_scores_100_and_random_group_scores_0():
    bg = _background()
    scorer = SyncScorer(bg, half_life=600)
    burst = scorer.score(np.full(20, 5000.0))
    assert burst["sync"] == pytest.approx(100.0) and burst["pattern"] == "burst"
    assert burst["beats_random"] == 100.0
    rng = np.random.default_rng(7)
    random_scores = [scorer.score(rng.choice(bg, 20, replace=False))["sync"] for _ in range(200)]
    assert np.mean(np.array(random_scores) == 0) > 0.97     # chance level is the 1-in-1,000 mark, per measurement


def test_timer_pattern_is_detected():
    bg = _background()
    times = 3 * 86400 + 1800.0 * np.arange(30)               # every 30 minutes
    result = SyncScorer(bg, half_life=600).score(times)
    assert result["pattern"] == "regular" and result["sync"] > 90


def test_top_of_the_hour_pattern_is_detected():
    bg = _background()
    hours = np.random.default_rng(3).choice(np.arange(24, 200), 24, replace=False)
    result = SyncScorer(bg, half_life=600).score(hours * 3600.0 + 2)
    assert result["pattern"] == "hourly" and result["sync"] > 90


def test_patterns_need_enough_posts():
    result = group_sync(1800.0 * np.arange(5), half_life=60, background=_background())
    assert result["raw"]["regular"] == 0.0


def test_group_without_background_uses_measured_burst():
    result = group_sync([0, 0, 0])
    assert result["sync"] == 100.0 and result["beats_random"] is None


def test_nearest_sync_and_bursts():
    times = np.concatenate([np.arange(0, 86400, 600.0), np.full(40, 40000.0)])
    per_post = nearest_sync(times, half_life=600)
    assert per_post[-1] == 100.0 and per_post[0] == pytest.approx(50.0)
    bursts = find_bursts(times, 600)
    assert bursts and bursts[0]["start"] <= 40000 <= bursts[0]["end"] and bursts[0]["posts"] >= 40


# ---------------------------------------------------------------- loading

def test_parse_times_formats():
    out = parse_times(["2026-11-14 10:00:00", "2026-11-14T10:00:00Z", "2026-11-14T12:00:00+02:00",
                       "1794650400", "1794650400000", "not a date", ""])
    assert out[0] == out[1] == out[2] == out[3] == out[4] == 1794650400.0
    assert np.isnan(out[5]) and np.isnan(out[6])


def test_parse_duration():
    assert parse_duration("30s") == 30 and parse_duration("10m") == 600
    assert parse_duration("2h") == 7200 and parse_duration("1d") == 86400 and parse_duration("45") == 45
    with pytest.raises(ValueError):
        parse_duration("soon")


def test_guess_columns():
    assert guess_columns(["id", "content", "time_posted", "label"]) == {
        "text": "content", "time": "time_posted", "id": "id", "account": None}
    guess = guess_columns(["Author", "msg", "time_posted"])
    assert guess["time"] == "time_posted" and guess["text"] is None      # "post" must not match the time column
    assert guess["account"] == "Author"
    guess = guess_columns(["Tweet", "Created_At", "video", "user_agent"])
    assert guess["id"] is None and guess["account"] is None              # exact names only


def test_load_json_and_jsonl_and_dropped_rows(tmp_path):
    rows = [{"body": "hello world, this is a post", "created_utc": 1794650400},
            {"body": "", "created_utc": 1794650401},
            {"body": "another post entirely", "created_utc": "garbage"}]
    (tmp_path / "a.json").write_text(json.dumps({"data": rows}), encoding="utf-8")
    (tmp_path / "a.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    for name in ("a.json", "a.jsonl"):
        ds = load_dataset(tmp_path / name)
        assert len(ds) == 1 and ds.dropped_empty == 1 and ds.dropped_no_time == 1
        assert ds.text_col == "body" and ds.time_col == "created_utc" and ds.ids == ["1"]
        assert len(ds.warnings) == 2
    assert len(read_table(tmp_path / "a.json")) == 3


def test_load_reports_missing_columns(tmp_path):
    (tmp_path / "x.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="content"):
        load_dataset(tmp_path / "x.csv")


# ---------------------------------------------------------------- detector on the demo dataset

@pytest.fixture(scope="module")
def demo_report():
    return analyse(load_dataset(DEMO, label_col="label", account_col="auto"))


def test_demo_planted_swarms_are_flagged(demo_report):
    by_label = demo_report["evaluation"]["by_label"]
    for label in ("swarm_copypaste", "swarm_template", "swarm_schedule", "swarm_clock"):
        assert by_label[label]["flagged"] == by_label[label]["posts"], label


def test_demo_known_limits_are_what_the_docs_say(demo_report):
    """Reworded copies are missed without semantic mode, and the daily
    greeting is a false positive. Both are documented, so pin them."""
    assert demo_report["evaluation"]["by_label"]["swarm_paraphrase"]["flagged"] == 0
    greeting = [c for c in demo_report["clusters"] if c["posts"][0]["content"].startswith("Good morning")]
    assert greeting and greeting[0]["verdict"] != "low" and greeting[0]["pattern"] == "daily"


def test_demo_innocent_lookalikes_are_not_flagged(demo_report):
    ds = load_dataset(DEMO, label_col="note")
    flagged_ids = {i for c in demo_report["clusters"] if c["verdict"] != "low" for i in c["post_ids"]}
    for note in ("quote", "news", "background", "short", "news feed"):
        hits = [i for i, n in zip(ds.ids, ds.labels) if n == note and i in flagged_ids]
        assert not hits, f"{note}: {len(hits)} posts flagged"
    quote = [c for c in demo_report["clusters"] if "Be the change" in c["posts"][0]["content"]]
    assert quote and quote[0]["verdict"] == "low" and quote[0]["synchrony"] == 0


def test_demo_false_positive_rate_is_low(demo_report):
    ev = demo_report["evaluation"]
    assert ev["false_positive_rate"] < 0.01
    assert ev["precision"] > 0.8 and ev["recall"] > 0.85


def test_seeds_find_the_matching_swarm():
    ds = load_dataset(DEMO, label_col="label")
    seed = "The council vote on the harbour development was rigged from the start. Share this before they delete it"
    report = analyse(ds, seeds=[{"content": seed, "time": "2026-11-03 21:15:00"}, {"content": "   "}])
    seeds = report["seeds"]
    assert len(seeds["seeds"]) == 1 and seeds["n_matches"] == 40 and seeds["verdict"] == "strong"
    labels = dict(zip(ds.ids, ds.labels))
    assert all(labels[i] == "swarm_copypaste" for i in seeds["match_ids"])
    assert all(m["sync_with_seed"] > 50 for m in seeds["matches"])


def test_seed_with_no_match_and_tiny_dataset():
    ds = load_dataset(DEMO, max_rows=30)
    report = analyse(ds, seeds=[{"content": "zebra xylophone quantum marmalade"}])
    assert report["seeds"]["n_matches"] == 0 and report["seeds"]["verdict"] == "low"
    assert report["summary"]["flagged_clusters"] == 0
    json.dumps(report)      # report must be JSON-serialisable


# ---------------------------------------------------------------- account types

def test_classify_rules():
    quiet = {"schedule": 0, "no_pause": 0, "repetition": 0, "swarm": 0}
    assert classify(10, 0, quiet, 60) == "no_signals"
    assert classify(2, 0, quiet, 60) == "too_few"
    assert classify(1, 1, {**quiet, "swarm": 100}, 60) == "single_purpose"
    assert classify(6, 4, {**quiet, "swarm": 66.7}, 60) == "swarm_participant"
    assert classify(10, 2, {**quiet, "swarm": 20}, 60) == "occasional"
    assert classify(5, 0, {**quiet, "repetition": 80}, 60) == "repetitive"
    assert classify(40, 0, {**quiet, "no_pause": 90}, 60) == "automated"
    assert classify(12, 12, {"schedule": 100, "no_pause": 0, "repetition": 95, "swarm": 100}, 60) == "automated"   # first match wins


def test_longest_daily_quiet_hours():
    assert longest_daily_quiet_hours(np.array([8, 9, 10, 20]) * 3600.0) == pytest.approx(12.0)        # 20:00 to 08:00
    day = 86400.0
    assert longest_daily_quiet_hours(np.array([0 * day + 23 * 3600, 1 * day + 1 * 3600, 2 * day + 12 * 3600])) == pytest.approx(11.0)
    assert longest_daily_quiet_hours(np.arange(48) * 1800.0) == pytest.approx(0.5)


def test_demo_account_types(demo_report):
    acc = demo_report["accounts"]
    by_id = {a["id"]: a for a in acc["accounts"]}
    assert by_id["watersafe_alerts"]["type"] == "automated" and by_id["watersafe_alerts"]["pattern"] == "regular"
    assert by_id["boost_agency"]["type"] == "automated" and by_id["boost_agency"]["pattern"] == "hourly"
    # Automated but benign: the news feed never posts in a flagged group.
    feed = by_id["harbour_daily_news"]
    assert feed["type"] == "automated" and feed["signals"]["no_pause"] >= 50 and feed["flagged_posts"] == 0
    assert acc["type_counts"]["single_purpose"] == 58          # 40 copy-paste accounts + 18 template accounts
    assert acc["type_counts"]["automated"] == 7                # 3 bots, the news feed, 3 people with a morning ritual
    assert sum(acc["type_counts"].values()) == acc["n_accounts"]
    # Ordinary people sleep: no organic background account is typed as automated.
    ev = acc["evaluation"]
    assert ev["false_positives"] == 4 and ev["true_positives"] == 61 and ev["false_negatives"] == 16
    json.dumps(demo_report)


def test_demo_groups_say_how_many_accounts(demo_report):
    flagged = [c for c in demo_report["clusters"] if c["verdict"] != "low"]
    spread = sorted(c["accounts"] for c in flagged)
    assert spread == [1, 2, 3, 18, 40]
    one = next(c for c in flagged if c["accounts"] == 1)
    assert "one account" in one["accounts_note"] and one["top_accounts"][0]["id"] == "watersafe_alerts"
    assert all(len(c["times"]) == c["size"] and c["times"] == sorted(c["times"]) for c in flagged)
    assert np.array(demo_report["activity"]["total"]).sum() == demo_report["dataset"]["posts"]
    assert np.array(demo_report["activity"]["flagged"]).sum() == demo_report["summary"]["flagged_posts"]


def test_without_account_column_accounts_are_not_typed():
    report = analyse(load_dataset(DEMO))
    assert report["accounts"] is None
    assert all("accounts" not in c and "account" not in c["posts"][0] for c in report["clusters"])
    assert any("No account column" in c for c in report["caveats"])


def test_repetitive_and_unknown_accounts(tmp_path):
    rows = ["account,content,time_posted"]
    for k in range(6):       # one account repeating itself at unrelated times
        rows.append(f'spammy,"Cheap watches for sale, visit my profile for the best deals today {k}",2026-11-0{k + 1} 1{k}:1{k}:00')
    for k in range(40):      # ordinary accounts, and some rows with no account at all
        who = "" if k % 4 == 0 else f"person{k % 7}"
        rows.append(f'{who},"unrelated remark number {k} about topic {k * 7919 % 101} and nothing else",2026-11-0{1 + k % 9} 0{k % 10}:{10 + k}:00')
    path = tmp_path / "a.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    report = analyse(load_dataset(path, account_col="account"))
    acc = report["accounts"]
    by_id = {a["id"]: a for a in acc["accounts"]}
    assert by_id["spammy"]["type"] == "repetitive" and by_id["spammy"]["signals"]["repetition"] > 80
    assert "" not in by_id and acc["posts_without_account"] == 10 and acc["n_accounts"] == 8   # spammy + person0..6


# ---------------------------------------------------------------- dashboard API

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ["SWARM_UPLOAD_DIR"] = str(tmp_path_factory.mktemp("uploads"))
    from fastapi.testclient import TestClient
    from dashboard.app import app
    return TestClient(app)


def test_api_lists_and_describes_datasets(client):
    assert client.get("/").status_code == 200
    listing = client.get("/api/datasets").json()
    assert any(d["id"] == "server:demo_posts.csv" for d in listing)
    info = client.get("/api/datasets/info", params={"id": "server:demo_posts.csv"}).json()
    assert info["guess"]["text"] == "content" and info["guess"]["time"] == "time_posted" and len(info["preview"]) == 5
    assert info["guess"]["account"] == "account"
    res = client.post("/api/analyze", json={"dataset_id": "server:demo_posts.csv", "account_col": "account"})
    assert res.status_code == 200 and res.json()["accounts"]["flagged_accounts"] == 65
    assert res.json()["clusters"][0]["posts"][0]["account"]


@pytest.mark.parametrize("bad", ["server:../requirements.txt", "server:make_demo_data.py", "upload:../../x.csv",
                                 "upload:abc.csv", "C:/Windows/win.ini", "server:"])
def test_api_rejects_paths(client, bad):
    assert client.get("/api/datasets/info", params={"id": bad}).status_code == 404
    assert client.post("/api/analyze", json={"dataset_id": bad}).status_code == 404


def test_api_upload_and_analyse(client):
    lines = ["text,when"] + [f'"Vote NO on the harbour plan, share this now {"!" * (k % 3)}",2026-11-03 21:14:{k:02d}' for k in range(12)]
    lines += [f'"completely different remark number {k} about {w}",2026-11-0{1 + k % 9} 1{k % 10}:00:00'
              for k, w in enumerate("cats trains soup chess ferries pottery drums marathons saunas puzzles libraries bakeries".split() * 5)]
    body = "\n".join(lines).encode()
    assert client.post("/api/datasets", params={"name": "evil.exe"}, content=body).status_code == 400
    assert client.post("/api/datasets", params={"name": "empty.csv"}, content=b"").status_code == 400
    info = client.post("/api/datasets", params={"name": "mine.csv"}, content=body).json()
    assert info["id"].startswith("upload:") and info["rows"] == 72 and info["guess"]["text"] == "text"
    res = client.post("/api/analyze", json={"dataset_id": info["id"], "text_col": "text", "time_col": "when",
                                            "seeds": [{"content": "Vote NO on the harbour plan, share this now"}]})
    assert res.status_code == 200, res.text
    report = res.json()
    assert report["summary"]["flagged_clusters"] == 1 and report["clusters"][0]["size"] == 12
    assert report["seeds"]["n_matches"] == 12 and report["dataset"]["name"] == "mine.csv"


def test_api_reports_bad_input_as_400(client):
    res = client.post("/api/analyze", json={"dataset_id": "server:demo_posts.csv", "text_col": "nope"})
    assert res.status_code == 400 and "nope" in res.json()["detail"]
    res = client.post("/api/analyze", json={"dataset_id": "server:demo_posts.csv", "half_life": "soon"})
    assert res.status_code == 400
    res = client.post("/api/analyze", json={"dataset_id": "server:demo_posts.csv", "threshold": 5})
    assert res.status_code == 422
