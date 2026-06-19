"""Utilities for scoring LLM responses against expected text in integration tests.

Uses sklearn TF-IDF cosine similarity — no network calls, no model downloads.
sklearn is available in the flowcept conda env; it is not added as a hard
dependency because it is only needed for test scoring.
"""

from __future__ import annotations


def cosine_similarity(text_a: str, text_b: str) -> float:
    """Return TF-IDF cosine similarity between two strings (0.0–1.0).

    Parameters
    ----------
    text_a, text_b : str
        Texts to compare.

    Returns
    -------
    float
        Similarity score in [0.0, 1.0].  Returns 0.0 on empty input or errors.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as _sk_cos
    except ImportError as exc:
        raise ImportError("sklearn is required for test scoring: pip install scikit-learn") from exc

    if not text_a.strip() or not text_b.strip():
        return 0.0
    try:
        matrix = TfidfVectorizer().fit_transform([text_a, text_b])
        return float(_sk_cos(matrix[0:1], matrix[1:2])[0][0])
    except Exception:
        return 0.0


def score_response(actual: str, expected: str, threshold: float) -> bool:
    """Return True if the cosine similarity between *actual* and *expected* meets *threshold*.

    Parameters
    ----------
    actual : str
        LLM response to evaluate.
    expected : str
        Reference text from the test YAML.
    threshold : float
        Minimum similarity required (0.0–1.0).
    """
    return cosine_similarity(actual, expected) >= threshold
