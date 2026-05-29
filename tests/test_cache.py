"""Verify cache primitives and stats accounting."""
import math
import random

from app.retrieval.cache import _cosine


def test_cosine_identical_vectors_is_one():
    v = [1.0, 2.0, 3.0, 4.0]
    assert math.isclose(_cosine(v, v), 1.0, rel_tol=1e-9)


def test_cosine_orthogonal_vectors_is_zero():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert math.isclose(_cosine(a, b), 0.0, abs_tol=1e-9)


def test_cosine_opposite_vectors_is_negative_one():
    a = [1.0, 2.0, 3.0]
    b = [-1.0, -2.0, -3.0]
    assert math.isclose(_cosine(a, b), -1.0, rel_tol=1e-9)


def test_cosine_zero_vector_returns_zero():
    a = [0.0, 0.0, 0.0]
    b = [1.0, 2.0, 3.0]
    assert _cosine(a, b) == 0.0
    assert _cosine(b, a) == 0.0


def test_cosine_random_vectors_in_range():
    rng = random.Random(42)
    a = [rng.uniform(-1, 1) for _ in range(128)]
    b = [rng.uniform(-1, 1) for _ in range(128)]
    sim = _cosine(a, b)
    assert -1.0 <= sim <= 1.0


def test_cosine_high_similarity_for_near_duplicates():
    rng = random.Random(7)
    a = [rng.uniform(-1, 1) for _ in range(1536)]
    # b is a with 1% noise — should still be highly similar.
    b = [x + rng.uniform(-0.01, 0.01) for x in a]
    sim = _cosine(a, b)
    assert sim > 0.99
