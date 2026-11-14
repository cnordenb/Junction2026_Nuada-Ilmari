"""Text similarity score for posts and comments.

    100 = identical (after ignoring case, punctuation and spacing)
      0 = completely different (no shared words or character sequences)

The lexical score is the average of two cosine similarities over TF-IDF
vectors: one built from words and word pairs, one from character sequences
of length 3 to 5. Words catch reused phrases; character sequences survive
typos, small edits and inflected languages. With --semantic the score is
the higher of the lexical score and an embedding-based score, which also
catches lightly reworded copies (needs the sentence-transformers package).
It does not catch the same point made in entirely different words: with a
small embedding model those look like ordinary same-topic posts.

Usage:
    python scripts/similarity_score.py pair "first text" "second text"
    python scripts/similarity_score.py dataset data/posts.csv --threshold 60 --top 20
    python scripts/similarity_score.py dataset data/posts.csv --out scores.csv
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from sklearn.feature_extraction.text import TfidfVectorizer

from swarm_common import load_dataset, normalise

DEFAULT_THRESHOLD = 60.0     # pairs at or above this count as "similar"
DEFAULT_MIN_CHARS = 20       # shorter posts ("lol", "thanks!") are never clustered
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# Embedding cosine at or below this maps to 0. Unrelated and merely same-topic
# sentences usually sit below it. A rough calibration, not tuned on labelled data.
SEM_FLOOR = 0.40
MAX_PAIRS = 3_000_000
DENSE_FEATURES = 1000        # most widespread features kept dense for speed (does not change scores)
SPLIT_STEP = 10.0            # how much the link threshold tightens when a cluster is too loose
COHESION_SLACK = 10.0        # a cluster is kept if its mean pairwise similarity >= threshold - slack


def semantic_available() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


class SimilarityIndex:
    """Vectorises a list of texts once and answers similarity queries on it.

    Texts with the same normalised form are merged into one "unique text", so
    exact copies cost nothing extra and do not distort the word statistics.
    Attributes: unique (normalised texts), inverse (text -> unique index),
    counts (texts per unique), lengths (characters per unique).
    """

    def __init__(self, texts: list[str], use_idf: bool = True, semantic: bool = False,
                 model: str = DEFAULT_MODEL):
        first: dict[str, int] = {}
        raw_first: list[str] = []
        inverse = np.empty(len(texts), dtype=np.int64)
        for i, text in enumerate(texts):
            key = normalise(text)
            if key not in first:
                first[key] = len(first)
                raw_first.append(str(text))
            inverse[i] = first[key]
        self.unique = list(first)
        self.inverse = inverse
        self.counts = np.bincount(inverse, minlength=len(self.unique))
        self.lengths = np.array([len(t) for t in self.unique], dtype=np.int64)
        self.semantic = bool(semantic)

        # The product X @ X.T is what every score comes from. Features shared
        # by many texts make that product slow as a sparse operation, so the
        # most widespread features are held in a dense matrix (fast BLAS
        # multiply) and the rest stay sparse. The sum is the same product.
        X = self._lexical(self.unique, use_idf)
        doc_freq = np.diff(X.tocsc().indptr)
        common = np.zeros(X.shape[1], dtype=bool)
        common[np.argsort(-doc_freq, kind="stable")[:DENSE_FEATURES]] = True
        self.D = np.ascontiguousarray(X[:, common].toarray())
        self.R = X[:, ~common].tocsr()
        self.RT = self.R.T.tocsr()
        self.E = self._embed(raw_first, model) if semantic else None

    @staticmethod
    def _lexical(texts: list[str], use_idf: bool) -> sparse.csr_matrix:
        def fit(**kwargs) -> sparse.csr_matrix:
            vec = TfidfVectorizer(lowercase=False, sublinear_tf=True, use_idf=use_idf,
                                  dtype=np.float32, **kwargs)
            try:
                return vec.fit_transform(texts)
            except ValueError:            # no tokens at all (e.g. every text is empty)
                return sparse.csr_matrix((len(texts), 0), dtype=np.float32)

        words = fit(analyzer="word", token_pattern=r"\S+", ngram_range=(1, 2))
        chars = fit(analyzer="char_wb", ngram_range=(3, 5))
        # Each half has unit-length rows, so the dot product of two stacked
        # rows is the average of the word cosine and the character cosine.
        X = (sparse.hstack([words, chars], format="csr") * np.float32(np.sqrt(0.5))).tocsr()
        # Features seen in a single text cannot contribute to any dot product.
        # Dropping them after normalisation keeps the scores and speeds things up.
        doc_freq = np.diff(X.tocsc().indptr)
        return X[:, doc_freq >= 2].tocsr()

    @staticmethod
    def _embed(texts: list[str], model: str) -> np.ndarray:
        if not semantic_available():
            raise RuntimeError(
                "Semantic mode needs the sentence-transformers package: "
                "pip install -r requirements-semantic.txt")
        from sentence_transformers import SentenceTransformer
        encoder = SentenceTransformer(model, device="cpu")
        emb = encoder.encode(texts, batch_size=64, normalize_embeddings=True,
                             show_progress_bar=False, convert_to_numpy=True)
        return np.asarray(emb, dtype=np.float32)

    # -------------------------------------------------------------- scores

    def block(self, rows, cols=None) -> np.ndarray:
        """Dense matrix of scores (0-100) between unique texts `rows` and
        `cols` (all unique texts when cols is None)."""
        if cols is None:
            scores = self.D[rows] @ self.D.T
            scores += (self.R[rows] @ self.RT).toarray()
        else:
            scores = self.D[rows] @ self.D[cols].T
            scores += (self.R[rows] @ self.R[cols].T).toarray()
        np.clip(scores, 0.0, 1.0, out=scores)
        if self.E is not None:
            cos = self.E[rows] @ (self.E if cols is None else self.E[cols]).T
            sem = np.clip((cos - SEM_FLOOR) / (1.0 - SEM_FLOOR), 0.0, 1.0)
            scores = np.maximum(scores, sem)
        return scores * 100.0

    def scan(self, threshold: float = DEFAULT_THRESHOLD, counts: np.ndarray | None = None,
             chunk: int = 512) -> dict:
        """Compare every unique text with every other.

        Returns the pairs scoring >= threshold (i < j, with scores), and for
        each unique text its best score against another unique text, which
        text that was, and how many texts (weighted by `counts`) are similar.
        """
        counts = self.counts if counts is None else counts
        n = len(self.unique)
        best = np.zeros(n, dtype=np.float32)
        best_idx = np.full(n, -1, dtype=np.int64)
        n_similar = np.zeros(n, dtype=np.int64)
        pi, pj, ps, total = [], [], [], 0
        for start in range(0, n, chunk):
            stop = min(n, start + chunk)
            S = self.block(slice(start, stop))
            local = np.arange(stop - start)
            S[local, local + start] = -1.0
            top = S.argmax(axis=1)
            top_score = S[local, top]
            best[start:stop] = np.maximum(top_score, 0.0)
            best_idx[start:stop] = np.where(top_score > 0, top, -1)
            mask = S >= threshold
            n_similar[start:stop] = mask @ counts
            rows, cols = np.nonzero(mask)
            keep = cols > rows + start
            total += int(keep.sum())
            if total > MAX_PAIRS:
                raise ValueError(
                    f"More than {MAX_PAIRS:,} pairs of texts score {threshold:g} or higher. "
                    "Raise the similarity threshold or analyse fewer posts.")
            pi.append(rows[keep] + start)
            pj.append(cols[keep])
            ps.append(S[rows[keep], cols[keep]])
        cat = lambda parts, dtype: np.concatenate(parts).astype(dtype) if parts else np.empty(0, dtype)
        return {"i": cat(pi, np.int64), "j": cat(pj, np.int64), "score": cat(ps, np.float32),
                "best": best, "best_idx": best_idx, "n_similar": n_similar}

    def cohesion(self, members: np.ndarray, counts: np.ndarray | None = None,
                 cap: int = 1200) -> tuple[float, float]:
        """Mean pairwise score (0-100) within a group of unique texts, two ways:
        over all posts, counting exact copies (the group's similarity score),
        and over the distinct texts only (used to decide whether the group
        hangs together; copies would otherwise hide that it is really two
        unrelated groups joined by one bridging post).
        Estimated from a sample for huge groups."""
        counts = self.counts if counts is None else counts
        members = np.asarray(members)
        if len(members) > cap:
            members = np.random.default_rng(0).choice(members, cap, replace=False)
        c = counts[members].astype(np.float64)
        m, u = c.sum(), len(members)
        if m < 2:
            return 0.0, 0.0
        S = self.block(members, members).astype(np.float64)
        np.fill_diagonal(S, 0.0)
        all_posts = (c @ S @ c + 100.0 * (c * (c - 1)).sum()) / (m * (m - 1))
        distinct = S.sum() / (u * (u - 1)) if u > 1 else 100.0
        return float(all_posts), float(distinct)


def find_clusters(index: SimilarityIndex, scan: dict, threshold: float = DEFAULT_THRESHOLD,
                  min_size: int = 3, min_chars: int = DEFAULT_MIN_CHARS,
                  counts: np.ndarray | None = None) -> list[dict]:
    """Group similar texts into clusters.

    Unique texts are linked when they score >= threshold; linked groups form
    clusters. Linking can chain unrelated texts together (A~B, B~C, but A and
    C differ), so a group whose distinct texts average below
    threshold - COHESION_SLACK against each other is split again with a
    tighter link threshold.
    Returns [{"members": unique indices, "similarity": mean pairwise score,
    "size": number of posts}], largest first.
    """
    counts = index.counts if counts is None else counts
    n = len(index.unique)
    valid = (index.lengths >= min_chars) & (counts > 0)
    pi, pj, ps = scan["i"], scan["j"], scan["score"]
    ok = valid[pi] & valid[pj]
    pi, pj, ps = pi[ok], pj[ok], ps[ok]
    accept_at = threshold - COHESION_SLACK
    clusters: list[dict] = []

    def split(nodes: np.ndarray, pairs: np.ndarray, link: float) -> None:
        graph = sparse.coo_matrix((np.ones(len(pairs), dtype=bool), (pi[pairs], pj[pairs])), shape=(n, n))
        _, label = connected_components(graph, directed=False)
        order = np.argsort(label[nodes], kind="stable")
        sorted_nodes = nodes[order]
        sorted_labels = label[sorted_nodes]
        starts = np.concatenate([[0], np.flatnonzero(np.diff(sorted_labels)) + 1])
        sizes = np.add.reduceat(counts[sorted_nodes], starts)
        ends = np.concatenate([starts[1:], [len(sorted_nodes)]])
        pair_label = label[pi[pairs]]
        for start, end, size in zip(starts, ends, sizes):
            if size < min_size:
                continue
            group = sorted_nodes[start:end]
            similarity, distinct = index.cohesion(group, counts)
            if distinct >= accept_at:
                clusters.append({"members": group, "similarity": similarity, "size": int(size)})
                continue
            if link + SPLIT_STEP > 100:
                continue
            inside = pairs[(pair_label == sorted_labels[start]) & (ps[pairs] >= link + SPLIT_STEP)]
            split(group, inside, link + SPLIT_STEP)

    split(np.flatnonzero(valid), np.arange(len(pi)), threshold)
    clusters.sort(key=lambda c: (-c["size"], -c["similarity"]))
    return clusters


def pair_similarity(a: str, b: str, corpus: list[str] | None = None, semantic: bool = False,
                    model: str = DEFAULT_MODEL) -> float:
    """Score two texts. With a corpus, word statistics come from it, which
    stops very common words from inflating the score; without one, every
    word counts equally."""
    index = SimilarityIndex([a, b] + list(corpus or []), use_idf=bool(corpus),
                            semantic=semantic, model=model)
    ia, ib = index.inverse[0], index.inverse[1]
    if ia == ib:
        return 100.0 if index.unique[ia] else 0.0
    return float(index.block([ia], [ib])[0, 0])


def score_dataset(texts: list[str], threshold: float = DEFAULT_THRESHOLD, semantic: bool = False,
                  model: str = DEFAULT_MODEL, top: int = 20) -> dict:
    """Per-post similarity to its closest other post, plus the top pairs of
    distinct texts."""
    index = SimilarityIndex(texts, semantic=semantic, model=model)
    scan = index.scan(threshold)
    inv = index.inverse
    first_post = np.full(len(index.unique), -1, dtype=np.int64)
    first_post[inv[::-1]] = np.arange(len(texts))[::-1]
    second_post = np.full(len(index.unique), -1, dtype=np.int64)
    seen = np.zeros(len(index.unique), dtype=np.int8)
    for p, u in enumerate(inv):
        seen[u] += seen[u] < 2
        if seen[u] == 2 and second_post[u] < 0:
            second_post[u] = p

    has_copy = index.counts[inv] > 1
    nearest_unique = scan["best_idx"][inv]
    nearest = np.where(nearest_unique >= 0, first_post[np.maximum(nearest_unique, 0)], -1)
    copy_of = np.where(first_post[inv] == np.arange(len(texts)), second_post[inv], first_post[inv])
    per_post = {
        "max_similarity": np.where(has_copy, 100.0, scan["best"][inv]).round(1),
        "nearest": np.where(has_copy, copy_of, nearest),
        "n_similar": scan["n_similar"][inv] + index.counts[inv] - 1,
        "exact_copies": index.counts[inv] - 1,
    }
    order = np.argsort(-scan["score"], kind="stable")[:top]
    pairs = [{"a": int(first_post[scan["i"][k]]), "b": int(first_post[scan["j"][k]]),
              "score": round(float(scan["score"][k]), 1)} for k in order]
    return {"per_post": per_post, "pairs": pairs, "n_pairs": int(len(scan["score"])),
            "unique_texts": len(index.unique)}


# ---------------------------------------------------------------- CLI

def _clip(text: str, width: int = 100) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 1] + "…"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Similarity score for posts: 100 = identical, 0 = completely different.")
    sub = parser.add_subparsers(dest="command", required=True)

    pair = sub.add_parser("pair", help="score two texts")
    pair.add_argument("a")
    pair.add_argument("b")
    pair.add_argument("--corpus", help="dataset file used for word statistics (optional)")
    pair.add_argument("--text-col")

    data = sub.add_parser("dataset", help="score every post in a dataset against the others")
    data.add_argument("path")
    data.add_argument("--text-col", help="content column (guessed if omitted)")
    data.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    data.add_argument("--top", type=int, default=20, help="how many top pairs to show")
    data.add_argument("--max-rows", type=int)
    data.add_argument("--out", help="write per-post scores to this CSV file")
    data.add_argument("--json", action="store_true", help="print JSON instead of text")

    for p in (pair, data):
        p.add_argument("--semantic", action="store_true", help="also use sentence embeddings (catches rewording)")
        p.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)

    if args.command == "pair":
        corpus = load_dataset(args.corpus, args.text_col, require_time=False).texts if args.corpus else None
        print(f"{pair_similarity(args.a, args.b, corpus, args.semantic, args.model):.1f}")
        return 0

    ds = load_dataset(args.path, args.text_col, require_time=False, max_rows=args.max_rows)
    result = score_dataset(ds.texts, args.threshold, args.semantic, args.model, args.top)
    per = result["per_post"]
    if args.out:
        import pandas as pd
        pd.DataFrame({
            "id": ds.ids,
            "max_similarity": per["max_similarity"],
            "nearest_id": [ds.ids[k] if k >= 0 else "" for k in per["nearest"]],
            "n_similar": per["n_similar"],
            "exact_copies": per["exact_copies"],
        }).to_csv(args.out, index=False)
    if args.json:
        print(json.dumps({
            "posts": len(ds), "unique_texts": result["unique_texts"], "threshold": args.threshold,
            "pairs_at_or_above_threshold": result["n_pairs"],
            "posts_with_a_similar_post": int((per["max_similarity"] >= args.threshold).sum()),
            "top_pairs": [{"score": p["score"], "id_a": ds.ids[p["a"]], "id_b": ds.ids[p["b"]],
                           "text_a": ds.texts[p["a"]], "text_b": ds.texts[p["b"]]} for p in result["pairs"]],
            "warnings": ds.warnings,
        }, ensure_ascii=False, indent=2))
        return 0

    for w in ds.warnings:
        print(f"note: {w}")
    flagged = int((per["max_similarity"] >= args.threshold).sum())
    print(f"{len(ds):,} posts, {result['unique_texts']:,} distinct texts (column {ds.text_col!r}).")
    print(f"{flagged:,} posts ({flagged / len(ds):.1%}) have at least one other post scoring "
          f"{args.threshold:g} or higher; {int((per['exact_copies'] > 0).sum()):,} have an exact copy.")
    if result["pairs"]:
        print(f"\nMost similar pairs of distinct texts (of {result['n_pairs']:,} at or above {args.threshold:g}):")
        for p in result["pairs"]:
            print(f"  {p['score']:5.1f}  [{ds.ids[p['a']]}] {_clip(ds.texts[p['a']], 70)}")
            print(f"         [{ds.ids[p['b']]}] {_clip(ds.texts[p['b']], 70)}")
    if args.out:
        print(f"\nPer-post scores written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
