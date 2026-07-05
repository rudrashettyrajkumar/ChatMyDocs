"""rrf tests (spec E3 Required tests): hand-computed fixture with a known
fused order, and dedup across lists for an id that appears in more than one.
"""

from dataclasses import dataclass

from backend.utils.rrf import reciprocal_rank_fusion


@dataclass(frozen=True)
class _Stub:
    id: str


def test_hand_computed_fusion_order_and_dedup():
    a, b, c, d = _Stub("a"), _Stub("b"), _Stub("c"), _Stub("d")
    list_a = [a, b, c]  # ranks 0,1,2
    list_b = [b, d, a]  # ranks 0,1,2
    list_c = [c, a]  # ranks 0,1

    # Hand-computed with k=60:
    # a = 1/63 (A r2) + 1/63 (B r2) + 1/62 (C r1) ≈ 0.047875
    # b = 1/62 (A r1) + 1/61 (B r0)               ≈ 0.032522
    # c = 1/63 (A r2) + 1/61 (C r0)                ≈ 0.032266
    # d = 1/62 (B r1)                              ≈ 0.016129
    # => a > b > c > d
    fused = reciprocal_rank_fusion([list_a, list_b, list_c], top_k=4)

    assert [chunk.id for chunk in fused] == ["a", "b", "c", "d"]
    # `a` appeared in all three lists but must be de-duplicated to one entry.
    assert len(fused) == 4


def test_top_k_truncates_and_empty_input_is_empty():
    stubs = [_Stub(str(i)) for i in range(10)]
    fused = reciprocal_rank_fusion([stubs], top_k=6)
    assert [c.id for c in fused] == [str(i) for i in range(6)]

    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_ties_keep_first_seen_order():
    # Two lists each contributing one chunk at rank 0 — identical score, so the
    # stable sort must preserve first-seen (input) order.
    x, y = _Stub("x"), _Stub("y")
    fused = reciprocal_rank_fusion([[x], [y]])
    assert [c.id for c in fused] == ["x", "y"]
