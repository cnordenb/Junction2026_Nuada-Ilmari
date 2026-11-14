"""Tests for the command lines, the demo-data generator, file loading edge
cases and the dashboard's limits. They call the code the way a user does:
main(argv) and what it prints, or an HTTP request and its response.

Run from the repository root:  python -m pytest
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "data"))
sys.path.insert(0, str(ROOT))

import detect_swarm  # noqa: E402
import make_demo_data  # noqa: E402
import similarity_score  # noqa: E402
import sync_score  # noqa: E402
from swarm_common import (clip, format_duration, load_dataset, parse_duration, parse_time,  # noqa: E402
                          read_table, run_cli)

TOPICS = "cats trains soup chess ferries pottery drums marathons saunas puzzles libraries bakeries".split()
SWARM_TEXT = "Vote NO on the harbour plan, share this now"


@pytest.fixture(scope="module")
def small(tmp_path_factory) -> Path:
    """72 posts: a 12-post copy-paste swarm from 12 accounts within 12 seconds,
    and 60 unrelated remarks from 7 people."""
    lines = ["id,account,text,time_posted,label"]
    for k in range(12):
        lines.append(f'{k + 1},bot{k},"{SWARM_TEXT} {"!" * (k % 3)}",2026-11-03 21:14:{k:02d},swarm')
    for k, topic in enumerate(TOPICS * 5):
        lines.append(f'{k + 13},person{k % 7},"completely different remark number {k} about {topic}",'
                     f'2026-11-0{1 + k % 9} 1{k % 10}:00:00,organic')
    path = tmp_path_factory.mktemp("small") / "small.csv"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(module, capsys, *argv) -> str:
    assert module.main([str(a) for a in argv]) in (0, None)
    return capsys.readouterr().out


# ---------------------------------------------------------------- detect_swarm.py

def test_detect_prints_groups_accounts_and_accuracy(small, capsys):
    out = run(detect_swarm, capsys, small, "--label-col", "label")
    lines = out.splitlines()
    assert lines[0].startswith("72 posts (61 distinct texts) from 2026-11-01T10:00:00Z to 2026-11-09T")
    assert lines[1] == "Flagged: 1 clusters (1 strong, 0 moderate) covering 12 posts (16.7%)."
    assert lines[2] == "Similar text but no unusual timing: 6 clusters, 30 posts (not flagged)."
    assert "=== Cluster 1: STRONG, swarm score 100 (similarity 100, synchrony 100) ===" in lines
    assert "  2026-11-03T21:14:00Z to 2026-11-03T21:14:11Z, 1 distinct texts" in lines
    assert "  Written by 12 different accounts." in lines
    assert f"    2026-11-03T21:14:00Z  [1] {SWARM_TEXT}" in lines
    assert sum(SWARM_TEXT in line for line in lines) == 3            # three example posts per group
    assert "No cluster is both" not in out
    let_through = lines.index("Largest similar-text clusters that were NOT flagged (timing looks ordinary):")
    assert lines[let_through + 1].startswith("  cluster 2: 5 posts, similarity ")
    assert lines[let_through + 1].endswith(", synchrony 0  completely different remark number 55 about marathons")
    assert [l.split(":")[0] for l in lines[let_through + 1:let_through + 7]] == [f"  cluster {k}" for k in range(2, 7)] + [""]
    assert "=== Accounts: 19 in the data, 12 with a flagged type ===" in lines
    assert any(line.split() [:2] == ["Single-purpose", "12"] for line in lines)
    assert "  Most notable accounts:" in lines
    assert any(line.startswith("    bot0 ") and line.endswith("1 of its 1 posts are in flagged group 1.") for line in lines)
    assert ("  Against the labels (an account counts as real when most of its posts are labelled as swarm): "
            "precision 100.0%, recall 100.0%, false-positive rate 0.0% (TP 12, FP 0, FN 0, TN 7).") in lines
    assert ("Against the labels: precision 100.0%, recall 100.0%, false-positive rate 0.0% "
            "(TP 12, FP 0, FN 0, TN 60).") in lines
    assert "  organic                      0 of    60 flagged" in lines
    assert "  swarm                       12 of    12 flagged" in lines
    assert lines[-5] == "Read this before drawing conclusions:" and all(l.startswith("  - ") for l in lines[-4:])


def test_detect_without_accounts_and_with_nothing_to_flag(small, capsys, tmp_path):
    out = run(detect_swarm, capsys, small, "--account-col", "none")
    assert "No account column was used, so accounts were not typed. Add --account-col if the data has one." in out
    assert "Written by" not in out and "Against the labels" not in out and "=== Accounts" not in out
    quiet = tmp_path / "quiet.csv"
    quiet.write_text("\n".join(small.read_text(encoding="utf-8").splitlines()[:1] +
                               small.read_text(encoding="utf-8").splitlines()[13:]), encoding="utf-8")
    out = run(detect_swarm, capsys, quiet)
    assert "Flagged: 0 clusters (0 strong, 0 moderate) covering 0 posts (0.0%)." in out
    assert "\nNo cluster is both similar and synchronised enough to flag.\n" in out
    assert "Most notable accounts" not in out


def test_detect_with_no_similar_posts_at_all(capsys, tmp_path):
    path = tmp_path / "distinct.csv"
    path.write_text("text,time_posted\n" + "\n".join(f"{t} are what post {k} is about,2026-11-01 {k:02d}:00:00"
                                                     for k, t in enumerate(TOPICS)), encoding="utf-8")
    out = run(detect_swarm, capsys, path)
    assert "Similar text but no unusual timing: 0 clusters, 0 posts (not flagged)." in out
    assert "\nNo cluster is both similar and synchronised enough to flag.\n" in out and "NOT flagged" not in out

def test_detect_seeds_json_and_out_file(small, capsys, tmp_path):
    seeds = tmp_path / "seeds.csv"
    seeds.write_text(f'content,time\n"{SWARM_TEXT}",2026-11-03 21:14:05\n"{SWARM_TEXT} please",never\n', encoding="utf-8")
    out = run(detect_swarm, capsys, small, "--seed", "zebra xylophone quantum marmalade", "--seeds-file", seeds, "--show", "2")
    lines = out.splitlines()
    assert "=== Sample posts: 12 matches, verdict STRONG, swarm score 100 ===" in lines
    assert sum(line.startswith("    100.0  2026-11-03T21:14:") for line in lines) == 2        # --show 2

    target = tmp_path / "report.json"
    out = run(detect_swarm, capsys, small, "--json", "--out", target, "--seed", SWARM_TEXT)
    report = json.loads(out)
    assert report == json.loads(target.read_text(encoding="utf-8"))
    assert report["seeds"]["n_matches"] == 12 and report["seeds"]["seeds"][0]["matches"] == 12
    assert "sync_with_seed" not in report["seeds"]["matches"][0]          # the sample had no time
    assert report["params"]["account_column"] == "account" and report["summary"]["flagged_posts"] == 12
    out = run(detect_swarm, capsys, small, "--out", target)
    assert out.endswith(f"\nFull report written to {target}\n")

    out = run(detect_swarm, capsys, small, "--seed", "zebra xylophone quantum marmalade", "--seed", SWARM_TEXT + " today")
    assert "=== Sample posts: 12 matches" in out
    out = run(detect_swarm, capsys, small, "--seed", "zebra xylophone quantum marmalade")
    assert "=== Sample posts: 0 matches, verdict LOW, swarm score 0 ===" in out
    assert "  0 post(s) in the dataset score 60 or higher against the sample. Too few to judge timing." in out


def test_detect_rejects_bad_settings(small):
    ds = load_dataset(small)
    report = detect_swarm.analyse(ds, seeds=[{"content": SWARM_TEXT, "time": "never"}, {"content": SWARM_TEXT, "time": ""}])
    assert report["warnings"] == ["Could not read the time of 1 sample post(s); they were used for text matching only."]
    for bad in (["--threshold", "0"], ["--threshold", "101"], ["--min-size", "1"], ["--half-life", "0s"]):
        with pytest.raises(ValueError):
            detect_swarm.main([str(small), *bad])
    detect_swarm.main([str(small), "--threshold", "100", "--min-size", "2", "--json"])


def test_run_cli_turns_user_errors_into_exit_code_1(small, capsys):
    assert run_cli(lambda: detect_swarm.main([str(small), "--text-col", "nope"])) == 1
    captured = capsys.readouterr()
    assert captured.err == "error: No column named 'nope' for content. Columns: id, account, text, time_posted, label\n"
    assert captured.out == ""
    assert run_cli(lambda: sync_score.main(["pair", "2026-11-14 10:00", "2026-11-14 10:00"])) == 0
    assert capsys.readouterr().out == "100.0\n"
    with pytest.raises(KeyError):                  # a bug is not a user error: it must not be swallowed
        run_cli(lambda: {}["x"])


# ---------------------------------------------------------------- sync_score.py

def test_sync_pair(capsys):
    assert run(sync_score, capsys, "pair", "2026-11-14 10:00:00", "2026-11-14 10:10:00") == "50.0\n"
    assert run(sync_score, capsys, "pair", "2026-11-14 10:00:00", "2026-11-14 10:10:00", "--half-life", "5m") == "25.0\n"
    with pytest.raises(ValueError, match="Cannot read time 'yesterday-ish'"):
        sync_score.main(["pair", "yesterday-ish", "2026-11-14"])


def test_sync_dataset_background_and_selected_group(small, capsys, tmp_path):
    out = run(sync_score, capsys, "dataset", small)
    lines = out.splitlines()
    assert lines[0].startswith("72 posts from 2026-11-01T10:00:00Z to ") and lines[0].endswith("(column 'time_posted'), half-life 10 min.")
    assert lines[2].startswith("Background timing of all 72 posts. This is the dataset's normal level")
    assert "  component   measured   chance level   score" in lines
    assert [l.split()[0] for l in lines[lines.index("  component   measured   chance level   score") + 1:][:4]] == \
        ["burst", "regular", "hourly", "daily"]
    assert "Unusually busy windows (1 found, strongest first):" in lines
    assert any(l.startswith("  2026-11-03T21:10:00Z to 2026-11-03T21:20:00Z: 12 posts, about 0.1 expected") for l in lines)
    assert "Per-post scores" not in out

    scores = tmp_path / "scores.csv"
    out = run(sync_score, capsys, "dataset", small, "--ids", ",".join(map(str, range(1, 13))), "--out", scores)
    assert "\nSynchrony of 12 selected posts: 100.0 / 100 - posts arrive at near-constant intervals.\n" in out
    assert "  More synchronised than 100.0% of random groups of the same size from this dataset.\n" in out
    assert out.endswith(f"\nPer-post scores written to {scores}\n")
    rows = scores.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "id,time,sync_with_nearest_post" and len(rows) == 73
    assert rows[1] == "1,2026-11-03T21:14:00Z,99.9" and rows[13].split(",")[2] == "0.0"

    with pytest.raises(ValueError, match="Ids not found in the dataset: 999, zzz"):
        sync_score.main(["dataset", str(small), "--ids", "1, zzz,999,"])


def test_sync_dataset_json_and_quiet_timeline(small, capsys, tmp_path):
    report = json.loads(run(sync_score, capsys, "dataset", small, "--json", "--ids", "1,2,3,4,5,6,7,8"))
    assert report["posts"] == 72 and report["half_life_seconds"] == 600.0 and report["warnings"] == []
    group = report["group"]
    assert group["n"] == 8 and group["pattern"] == "regular" and group["sync"] == 100.0
    assert group["baseline_source"] == "dataset" and set(group["raw"]) == {"burst", "regular", "hourly", "daily"}
    assert group["raw"]["burst"] == 99.9 and group["span_seconds"] == 7.0
    assert report["bursts"][0]["start"] == "2026-11-03T21:10:00Z" and report["bursts"][0]["posts"] == 12

    even = tmp_path / "even.csv"
    even.write_text("text,time_posted\n" + "\n".join(f"post {k},2026-11-01 {k:02d}:00:00" for k in range(24)) + "\n,2026-11-02\n",
                    encoding="utf-8")
    out = run(sync_score, capsys, "dataset", even)
    assert out.startswith("note: 1 rows with empty content were skipped.\n24 posts from ")
    assert "\nNo unusually busy windows found.\n" in out
    # Scoring every post leaves no background to compare with: the scorer says so.
    assert "  Nothing to compare bursts with, so burst is as measured; the pattern scores are compared with evenly scattered times.\n" in out


# ---------------------------------------------------------------- similarity_score.py

def test_similarity_pair(small, capsys):
    assert run(similarity_score, capsys, "pair", "The vote was RIGGED!!!", "the vote   was rigged") == "100.0\n"
    assert run(similarity_score, capsys, "pair", "quick brown fox", "12345 67890") == "0.0\n"
    plain = float(run(similarity_score, capsys, "pair", "share this now about cats", "share this now about soup"))
    with_corpus = float(run(similarity_score, capsys, "pair", "share this now about cats", "share this now about soup",
                            "--corpus", small, "--text-col", "text"))
    assert 0 < plain < 100 and 0 < with_corpus < 100 and with_corpus != plain      # word statistics change the score


def test_similarity_dataset_text_json_and_out(small, capsys, tmp_path):
    scores = tmp_path / "sim.csv"
    out = run(similarity_score, capsys, "dataset", small, "--top", "2", "--out", scores)
    lines = out.splitlines()
    assert lines[0] == "72 posts, 61 distinct texts (column 'text')."
    assert lines[1].startswith("42 posts (58.3%) have at least one other post scoring 60 or higher; 12 have an exact copy.")
    assert lines[3].startswith("Most similar pairs of distinct texts (of ") and lines[3].endswith(" at or above 60):")
    assert len(lines) == 4 + 2 * 2 + 2 and lines[-1] == f"Per-post scores written to {scores}"
    assert lines[4].startswith("  ") and "[" in lines[4] and lines[5].startswith("         [")
    rows = scores.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "id,max_similarity,nearest_id,n_similar,exact_copies" and len(rows) == 73
    assert rows[1] == "1,100.0,2,11,11"

    report = json.loads(run(similarity_score, capsys, "dataset", small, "--json", "--threshold", "99.5", "--max-rows", "20"))
    assert report["posts"] == 20 and report["unique_texts"] == 9 and report["threshold"] == 99.5
    assert report["pairs_at_or_above_threshold"] == 0 and report["top_pairs"] == []
    assert report["posts_with_a_similar_post"] == 12
    assert report["warnings"] == ["The file has 72 rows; only the first 20 were analysed."]
    report = json.loads(run(similarity_score, capsys, "dataset", small, "--json", "--top", "1"))
    pair = report["top_pairs"][0]
    assert pair["text_a"] != pair["text_b"] and pair["score"] >= 60 and {pair["id_a"], pair["id_b"]} <= set(map(str, range(1, 73)))

    lonely = tmp_path / "lonely.csv"
    lonely.write_text("text\nalpha bravo charlie delta\nzulu yankee xray whiskey\n", encoding="utf-8")
    out = run(similarity_score, capsys, "dataset", lonely)
    assert out == "2 posts, 2 distinct texts (column 'text').\n0 posts (0.0%) have at least one other post scoring 60 or higher; 0 have an exact copy.\n"


# ---------------------------------------------------------------- demo data

def test_demo_generator_reproduces_the_committed_dataset(tmp_path, capsys):
    out = tmp_path / "demo.csv"
    make_demo_data.main(["--out", str(out)])
    assert capsys.readouterr().out == f"Wrote {out} with 4483 posts, 146 of them in planted swarms.\n"
    assert out.read_bytes() == (ROOT / "data" / "demo_posts.csv").read_bytes()
    make_demo_data.main(["--out", str(out), "--background", "10"])
    assert capsys.readouterr().out == f"Wrote {out} with 493 posts, 146 of them in planted swarms.\n"


# ---------------------------------------------------------------- loading and formatting

def test_read_table_formats(tmp_path):
    (tmp_path / "a.tsv").write_text("text\ttime_posted\nhello, world\t2026-11-01\n", encoding="utf-8")
    assert read_table(tmp_path / "a.tsv").to_dict("records") == [{"text": "hello, world", "time_posted": "2026-11-01"}]
    (tmp_path / "a.txt").write_text("text,time_posted\nhello,2026-11-01\n", encoding="utf-8")
    assert list(read_table(tmp_path / "a.txt").columns) == ["text", "time_posted"]
    # Unknown suffix: the first character decides.
    (tmp_path / "list.data").write_text('  [{"text": "a", "n": 1}, {"text": "b"}]', encoding="utf-8")
    assert read_table(tmp_path / "list.data").to_dict("records") == [{"text": "a", "n": "1.0"}, {"text": "b", "n": ""}]
    (tmp_path / "lines.data").write_text('{"text": "a"}\n\n{"text": "b"}\n', encoding="utf-8")
    assert read_table(tmp_path / "lines.data")["text"].tolist() == ["a", "b"]
    (tmp_path / "plain.data").write_text("text\na\n", encoding="utf-8")
    assert read_table(tmp_path / "plain.data")["text"].tolist() == ["a"]
    (tmp_path / "wrapped.json").write_text('{"meta": [1], "posts": [{"text": "a"}, {"text": "b"}]}', encoding="utf-8")
    assert read_table(tmp_path / "wrapped.json")["text"].tolist() == ["a", "b"]
    (tmp_path / "nolist.json").write_text('{"text": "a"}', encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a list of objects"):
        read_table(tmp_path / "nolist.json")
    (tmp_path / "empty.csv").write_text("text,time_posted\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no rows"):
        read_table(tmp_path / "empty.csv")


def test_load_dataset_column_choices_and_errors(small, tmp_path):
    ds = load_dataset(small, account_col="auto", label_col="label", max_rows=20)
    assert (ds.text_col, ds.time_col, ds.account_col) == ("text", "time_posted", "account")
    assert ds.ids[:2] == ["1", "2"] and ds.accounts[0] == "bot0" and ds.labels[0] == "swarm"
    assert len(ds) == 20 and ds.rows_read == 72 and ds.truncated_from == 72
    assert ds.warnings == ["The file has 72 rows; only the first 20 were analysed."]
    full = load_dataset(small, max_rows=72)
    assert full.truncated_from is None and full.warnings == [] and full.accounts is None and full.labels is None
    assert load_dataset(small, text_col="account", id_col="text").ids[0].startswith(SWARM_TEXT)

    (tmp_path / "x.csv").write_text("body,note\nhello there,x\n ,y\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Could not tell which column holds the time posted. Columns: body, note"):
        load_dataset(tmp_path / "x.csv")
    with pytest.raises(ValueError, match="No column named 'who' for account"):
        load_dataset(tmp_path / "x.csv", require_time=False, account_col="who")
    with pytest.raises(ValueError, match="No column named 'lbl' for label"):
        load_dataset(tmp_path / "x.csv", require_time=False, label_col="lbl")
    untimed = load_dataset(tmp_path / "x.csv", require_time=False, account_col="auto")
    assert untimed.texts == ["hello there"] and untimed.dropped_empty == 1 and untimed.dropped_no_time == 0
    assert untimed.time_col is None and untimed.account_col is None and untimed.ids == ["1"]
    (tmp_path / "bad.csv").write_text("body,time_posted\nhello,never\n,2026-11-01\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No usable rows"):
        load_dataset(tmp_path / "bad.csv")
    (tmp_path / "mixed.csv").write_text("body,time_posted\nhello,never\nworld,2026-11-01\n", encoding="utf-8")
    assert load_dataset(tmp_path / "mixed.csv").warnings == [
        "1 rows were skipped because the time in column 'time_posted' could not be read."]


def test_durations_times_and_clipping():
    assert [format_duration(s) for s in (0.4, 1, 59.6, 60, 90, 600, 5400, 36000, 86400, 129600, -120)] == \
        ["under 1 s", "1 s", "60 s", "1 min", "1.5 min", "10 min", "1.5 h", "10 h", "1 d", "1.5 d", "2 min"]
    assert parse_duration(90) == 90.0 and parse_duration(" 1.5 H ") == 5400 and parse_duration("2 days") == 172800
    assert parse_duration("3min") == 180 and parse_duration("2hr") == 7200 and parse_duration("5sec") == 5
    for bad in ("0", -5, "ten minutes"):
        with pytest.raises(ValueError):
            parse_duration(bad)
    assert parse_time("1970-01-02") == 86400.0 and parse_time(5) == 5.0
    with pytest.raises(ValueError, match="Cannot read time 'soon'"):
        parse_time("soon")
    assert clip("a  b\n c", 10) == "a b c" and clip("abcdefghij", 10) == "abcdefghij" and clip("abcdefghijk", 10) == "abcdefghi…"


# ---------------------------------------------------------------- dashboard limits

@pytest.fixture()
def dash(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import dashboard.app as app_module
    monkeypatch.setattr(app_module, "UPLOAD_DIR", tmp_path / "uploads")
    return app_module, TestClient(app_module.app)


def test_dashboard_config_and_semantic_switch(dash, monkeypatch):
    app_module, client = dash
    config = client.get("/api/config").json()
    assert config["max_rows"] == 20000 and config["max_upload_mb"] == 30
    assert config["defaults"] == {"threshold": 60.0, "half_life": "10m", "min_size": 5}
    monkeypatch.setattr(app_module, "ALLOW_SEMANTIC", False)
    assert client.get("/api/config").json()["semantic_available"] is False
    res = client.post("/api/analyze", json={"dataset_id": "server:demo_posts.csv", "semantic": True})
    assert res.status_code == 400 and res.json()["detail"] == "Semantic mode is not installed on this server."


def test_dashboard_upload_limits_and_expiry(dash, monkeypatch):
    app_module, client = dash
    monkeypatch.setattr(app_module, "MAX_UPLOAD_BYTES", 2 * 1024 * 1024)
    big = b"text,time_posted\n" + b"x" * (2 * 1024 * 1024)
    res = client.post("/api/datasets", params={"name": "big.csv"}, content=big)
    assert res.status_code == 413 and res.json()["detail"] == "File is larger than 2 MB."
    assert not list(app_module.UPLOAD_DIR.glob("*")) if app_module.UPLOAD_DIR.exists() else True
    res = client.post("/api/datasets", params={"name": "broken.json"}, content=b"{not json")
    assert res.status_code == 400 and res.json()["detail"].startswith("Could not read broken.json: ")
    assert list(app_module.UPLOAD_DIR.glob("*")) == []            # a file that cannot be read is not kept

    body = b"text,time_posted\n" + "ä".encode() * 1500 + b" long post,2026-11-01 10:00:00\nshort post here,2026-11-01 10:00:05\n"
    first = client.post("/api/datasets", params={"name": "../../first name.csv"}, content=body).json()
    assert first["name"] == "first name.csv" and first["rows"] == 2 and len(first["preview"][0]["text"]) == 200
    stored = app_module.UPLOAD_DIR / first["id"].split(":")[1]
    report = client.post("/api/analyze", json={"dataset_id": first["id"], "min_size": 2, "account_col": ""}).json()
    assert report["dataset"]["name"] == "first name.csv" and report["params"]["account_column"] is None
    assert report["elapsed_seconds"] >= 0

    old = time.time() - 3 * 3600
    os.utime(stored, (old, old))
    second = client.post("/api/datasets", params={"name": "second.csv"}, content=body).json()
    assert not stored.exists() and (app_module.UPLOAD_DIR / second["id"].split(":")[1]).exists()
    res = client.get("/api/datasets/info", params={"id": first["id"]})
    assert res.status_code == 404 and "removed after two hours" in res.json()["detail"]
    assert client.get("/api/datasets/info", params={"id": second["id"]}).json()["name"] == "second.csv"


def test_dashboard_trims_long_posts_and_refuses_when_busy(dash, small):
    app_module, client = dash
    long_text = "Vote NO on the harbour plan " + "really " * 200
    body = ("text,time_posted,account\n" + "\n".join(f'"{long_text}",2026-11-03 21:14:{k:02d},bot{k}' for k in range(12)) + "\n" +
            "\n".join(f'"remark {k} about {t}",2026-11-0{1 + k % 9} 1{k % 10}:00:00,p{k % 5}' for k, t in enumerate(TOPICS * 4))).encode()
    info = client.post("/api/datasets", params={"name": "long.csv"}, content=body).json()
    request = {"dataset_id": info["id"], "account_col": "account", "seeds": [{"content": long_text}]}
    report = client.post("/api/analyze", json=request).json()
    by_id = {a["id"]: a for a in report["accounts"]["accounts"]}
    shown = [report["clusters"][0]["posts"][0], report["seeds"]["matches"][0], by_id["bot0"]["sample_posts"][0]]
    assert [(len(p["content"]), p["content"][-1]) for p in shown] == [(1001, "…")] * 3
    short = by_id["p0"]["sample_posts"][0]["content"]
    assert short.startswith("remark ") and not short.endswith("…")

    for _ in range(app_module.MAX_CONCURRENT):
        assert app_module._busy.acquire(blocking=False)
    try:
        res = client.post("/api/analyze", json=request)
        assert res.status_code == 429 and "busy" in res.json()["detail"]
    finally:
        for _ in range(app_module.MAX_CONCURRENT):
            app_module._busy.release()
    assert client.post("/api/analyze", json=request).status_code == 200      # the slot was given back
