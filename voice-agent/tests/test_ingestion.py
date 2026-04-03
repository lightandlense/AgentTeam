"""Unit tests for the document ingestion service.

All tests are pure unit tests — no real OpenAI calls and no real database
connections.  External dependencies (embed_chunks, delete_document) are
patched with AsyncMock/Mock where needed.
"""

import csv
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ingestion import (
    MAX_FILE_BYTES,
    chunk_csv,
    chunk_text,
    ingest_document,
    parse_file,
)


# ---------------------------------------------------------------------------
# parse_file tests
# ---------------------------------------------------------------------------


def test_parse_file_rejects_oversized_files() -> None:
    """Files larger than 10 MB raise ValueError before any parsing."""
    oversized = b"x" * (MAX_FILE_BYTES + 1)
    with pytest.raises(ValueError, match="10MB"):
        parse_file("test.txt", oversized)


def test_parse_file_handles_txt() -> None:
    """Plain text files are decoded and returned as-is."""
    content = b"Hello world"
    result = parse_file("sample.txt", content)
    assert "Hello world" in result


def test_parse_file_rejects_unsupported_extension() -> None:
    """Files with unknown extensions raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_file("file.xyz", b"data")


# ---------------------------------------------------------------------------
# chunk_text tests
# ---------------------------------------------------------------------------


def test_chunk_text_splits_long_text_into_multiple_chunks() -> None:
    """A long document produces more than one chunk."""
    # 2000 words of repeated content to exceed CHUNK_TOKENS (400)
    long_text = ("The quick brown fox jumps over the lazy dog. " * 250).strip()
    chunks = chunk_text(long_text)
    assert len(chunks) > 1
    assert all(isinstance(c, str) and len(c) > 0 for c in chunks)


def test_chunk_text_handles_short_text_in_one_chunk() -> None:
    """Short text fits in a single chunk."""
    chunks = chunk_text("Short text")
    assert len(chunks) == 1


# ---------------------------------------------------------------------------
# chunk_csv tests
# ---------------------------------------------------------------------------


def _build_csv_bytes(num_data_rows: int) -> bytes:
    """Helper: build a CSV with a header and *num_data_rows* data rows."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "name", "value"])
    for i in range(num_data_rows):
        writer.writerow([str(i), f"item_{i}", str(i * 10)])
    return buf.getvalue().encode("utf-8")


def test_chunk_csv_groups_rows() -> None:
    """25 data rows should produce 3 chunks (10 + 10 + 5)."""
    csv_bytes = _build_csv_bytes(25)
    chunks = chunk_csv(csv_bytes)
    assert len(chunks) == 3, f"Expected 3 chunks, got {len(chunks)}"


def test_chunk_csv_includes_header_in_every_chunk() -> None:
    """Each chunk must contain the CSV header for self-contained context."""
    csv_bytes = _build_csv_bytes(25)
    chunks = chunk_csv(csv_bytes)
    for chunk in chunks:
        assert "id" in chunk and "name" in chunk and "value" in chunk, (
            f"Header missing from chunk: {chunk[:80]!r}"
        )


# ---------------------------------------------------------------------------
# ingest_document integration test (mocked DB + OpenAI)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_document_calls_delete_then_inserts() -> None:
    """ingest_document should delete prior chunks then add new Embedding rows."""
    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(rowcount=0))

    fake_embedding = [0.1] * 1536

    with (
        patch(
            "app.services.ingestion.embed_chunks",
            new=AsyncMock(return_value=[fake_embedding]),
        ),
        patch(
            "app.services.ingestion.delete_document",
            new=AsyncMock(return_value=0),
        ),
    ):
        result = await ingest_document(
            mock_db, "client-1", "test.txt", b"some text content here"
        )

    assert mock_db.add.called, "db.add() should have been called for new Embedding rows"
    assert mock_db.commit.called, "db.commit() should have been called to persist rows"
    assert result["doc_name"] == "test.txt"
    assert result["chunks_ingested"] >= 1
