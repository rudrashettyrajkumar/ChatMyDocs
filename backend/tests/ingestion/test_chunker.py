"""Chunker golden tests (spec E2 Required tests): the most bug-prone code in
the project — exact chunk boundaries, page mapping across a page break, and
overlap correctness, all pinned to precomputed `cl100k_base` token counts so
nothing here is approximate.

Every word below is verified (see the literal lists) to encode to exactly ONE
`cl100k_base` token both alone and mid-sequence, so `count_tokens(" ".join(words))
== len(words)` — this lets the tests hand-compute exact expected chunks instead
of asserting fuzzy bounds.
"""

import pytest

from backend.ingestion.chunker import Chunk, chunk_pages, count_tokens

# Sixteen distinct single-`cl100k_base`-token words (verified via `enc.encode`).
_W = ["cat", "dog", "bird", "fish", "lion", "wolf", "bear", "deer", "fox", "hawk",
      "crow", "duck", "frog", "moth", "worm", "camel"]

# Twenty-five distinct single-token words, for the hard-split test.
_W25 = ["cat", "dog", "bird", "fish", "lion", "wolf", "bear", "deer", "fox", "hawk",
        "crow", "duck", "frog", "moth", "worm", "camel", "apple", "bread", "chair",
        "table", "river", "stone", "cloud", "grass", "house"]


@pytest.fixture(autouse=True)
def _small_budget(monkeypatch):
    """CHUNK_TOKENS=10 / CHUNK_OVERLAP=3 — small enough to hand-compute exact
    chunk boundaries with a handful of words."""
    monkeypatch.setenv("CHUNK_TOKENS", "10")
    monkeypatch.setenv("CHUNK_OVERLAP", "3")
    from backend.utils.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_count_tokens_matches_word_count_for_verified_words():
    assert count_tokens(" ".join(_W)) == len(_W)


def test_empty_pages_yield_no_chunks():
    assert chunk_pages([]) == []


def test_single_short_page_is_one_chunk_with_matching_page_bounds():
    text = " ".join(_W[:4])  # 4 tokens, well under the 10-token budget
    chunks = chunk_pages([(1, text)])
    assert chunks == [Chunk(chunk_index=0, text=text, page_start=1, page_end=1, token_count=4)]


def test_page_break_and_overlap_straddle_pages():
    """Two paragraphs on page 1, a third on page 2. Budget=10 packs the first
    two paragraphs into chunk 0; chunk 1 opens with the OVERLAP tail from page
    1 plus the new page-2 paragraph — so it must report page_start=1 (from the
    carried-over overlap) and page_end=2 (spec Req 3: "overlap can straddle
    pages")."""
    p1, p2, p3 = " ".join(_W[0:5]), " ".join(_W[5:10]), " ".join(_W[10:15])
    page1_text = f"{p1}\n\n{p2}"
    page2_text = p3

    chunks = chunk_pages([(1, page1_text), (2, page2_text)])

    assert len(chunks) == 2
    assert chunks[0] == Chunk(
        chunk_index=0, text=f"{p1}\n\n{p2}", page_start=1, page_end=1, token_count=10
    )
    # Chunk 1 = the overlap tail (p2, from page 1) + the new page-2 paragraph.
    assert chunks[1] == Chunk(
        chunk_index=1, text=f"{p2}\n\n{p3}", page_start=1, page_end=2, token_count=10
    )


def test_oversized_paragraph_hard_splits_on_raw_token_windows():
    """A single 25-token paragraph (no blank lines) with a 10-token budget must
    be hard-split into three windows, then packed+overlapped like any other
    unit. Every source word survives, in order, across the chunks."""
    text = " ".join(_W25)  # 25 tokens, well over the 10-token budget

    chunks = chunk_pages([(1, text)])

    assert len(chunks) == 3
    # Every chunk stays on the single source page.
    assert all(c.page_start == 1 and c.page_end == 1 for c in chunks)
    # No mid-word cut: every word from every chunk is one of the source words.
    for chunk in chunks:
        for word in chunk.text.split():
            assert word in _W25
    # Every source word appears somewhere, and in original order overall.
    seen = " ".join(c.text for c in chunks).split()
    assert set(_W25) <= set(seen)
    first_positions = {word: seen.index(word) for word in _W25}
    assert sorted(first_positions, key=first_positions.get) == _W25
    # Overlap: at least one word is duplicated across consecutive chunks.
    assert any(
        set(chunks[i].text.split()) & set(chunks[i + 1].text.split())
        for i in range(len(chunks) - 1)
    )


def test_chunking_is_deterministic():
    pages = [(1, f"{' '.join(_W[0:5])}\n\n{' '.join(_W[5:10])}"), (2, " ".join(_W[10:15]))]
    assert chunk_pages(pages) == chunk_pages(pages)


def test_chunk_index_is_sequential():
    pages = [(1, f"{' '.join(_W[0:5])}\n\n{' '.join(_W[5:10])}"), (2, " ".join(_W[10:15]))]
    chunks = chunk_pages(pages)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
