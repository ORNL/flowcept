"""Utilities for scoring LLM responses against expected text in integration tests.

Uses fact-recall scoring: what fraction of expected's content words are present in
actual (case-insensitive, 5-char prefix matching for morphological variants).

This metric is more appropriate than TF-IDF cosine for LLM responses that contain
markdown tables, UUIDs, or verbose formatting: it does not penalise actual for having
more text, and correctly detects missing key facts.

sklearn is NOT required.  Falls back gracefully if unavailable.
"""

from __future__ import annotations

import re

_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_HEX_FRAG_RE = re.compile(r"\b[0-9a-f]{8,}\b", re.I)
_MD_NOISE_RE = re.compile(r"[|`*#_\-]{2,}")

_STOP_WORDS = {
    "the", "a", "an", "is", "was", "are", "were", "be", "been", "have", "has", "had",
    "do", "does", "did", "will", "would", "shall", "should", "may", "might", "must",
    "can", "could", "to", "of", "in", "on", "at", "by", "for", "with", "about", "from",
    "it", "its", "and", "or", "but", "if", "than", "that", "this", "these", "those",
    "which", "who", "whose", "what", "how", "when", "where", "why", "via", "vs",
    "two", "one", "some", "any", "all", "each", "per", "ran", "run", "not", "no",
    "so", "as", "up", "out", "also", "into", "during", "same", "more", "most", "just",
    "too", "very", "still",
}


def _clean_tokenize(text: str) -> set:
    """Strip UUIDs, markdown noise, then return a set of lowercase word tokens."""
    text = _UUID_RE.sub(" ", text)
    text = _HEX_FRAG_RE.sub(" ", text)
    text = _MD_NOISE_RE.sub(" ", text)
    return set(re.findall(r"\b\w+\b", text.lower()))


def fact_recall(actual: str, expected: str) -> float:
    """Fraction of expected's content words present in actual (0.0–1.0).

    Content words are extracted from *expected* by removing stop words and
    short tokens (< 3 chars).  Presence in *actual* is tested via 5-char
    prefix matching so that morphological variants like ``coordinates`` /
    ``coordinated`` or ``submit`` / ``submitted`` match correctly.

    Parameters
    ----------
    actual : str
        LLM response to evaluate.
    expected : str
        Reference text with the key facts the response should contain.

    Returns
    -------
    float
        Score in [0.0, 1.0].  Returns 0.0 when expected has no content words.
    """
    exp_words = [
        w for w in _clean_tokenize(expected)
        if len(w) >= 3 and w not in _STOP_WORDS
    ]
    if not exp_words:
        return 0.0

    act_tokens = _clean_tokenize(actual)

    def _present(word: str) -> bool:
        if word in act_tokens:
            return True
        prefix = word[:5] if len(word) >= 5 else word
        return any(t.startswith(prefix) for t in act_tokens)

    found = sum(1 for w in exp_words if _present(w))
    return found / len(exp_words)


def cosine_similarity(text_a: str, text_b: str) -> float:
    """Return TF-IDF cosine similarity between two strings (0.0–1.0).

    Kept for backward compatibility; ``score_response`` now uses
    ``fact_recall`` instead.  Returns 0.0 on empty input or if sklearn is
    unavailable.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as _sk_cos
    except ImportError:
        return 0.0

    a = _UUID_RE.sub(" ", text_a)
    b = _UUID_RE.sub(" ", text_b)
    if not a.strip() or not b.strip():
        return 0.0
    try:
        matrix = TfidfVectorizer().fit_transform([a, b])
        return float(_sk_cos(matrix[0:1], matrix[1:2])[0][0])
    except Exception:
        return 0.0


def score_response(actual: str, expected: str, threshold: float) -> bool:
    """Return True if the fact-recall score of *actual* against *expected* meets *threshold*.

    Parameters
    ----------
    actual : str
        LLM response to evaluate.
    expected : str
        Reference text from the test YAML.
    threshold : float
        Minimum score required (0.0–1.0).
    """
    return fact_recall(actual, expected) >= threshold
