"""Document ingestion service.

Parses PDF, DOCX, TXT, and CSV files into text chunks, embeds them
using OpenAI text-embedding-3-small, and persists them to the
per-client embeddings table in PostgreSQL.

Re-ingesting a document with the same (client_id, doc_name) pair
deletes all prior chunks before inserting new ones.
"""

import csv
import io
import logging
import os
from pathlib import Path

import openai
import tiktoken
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.client import Embedding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

MAX_FILE_BYTES: int = 10 * 1024 * 1024  # 10 MB
CHUNK_TOKENS: int = 400
CHUNK_OVERLAP_TOKENS: int = 80
CSV_ROWS_PER_CHUNK: int = 10
EMBED_MODEL: str = "text-embedding-3-small"
EMBED_BATCH_SIZE: int = 100
SIMILARITY_THRESHOLD: float = 0.75  # used by RAG query service (plan 02-03)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_file(filename: str, content: bytes) -> str:
    """Parse a file's raw bytes into a plain-text string.

    Args:
        filename: Original file name (used to detect extension).
        content:  Raw file bytes.

    Returns:
        Extracted text as a single string.

    Raises:
        ValueError: If the file exceeds MAX_FILE_BYTES or has an unsupported
                    extension.  CSV files are NOT handled here — use
                    chunk_csv() directly.
    """
    if len(content) > MAX_FILE_BYTES:
        raise ValueError(
            f"File exceeds 10MB limit ({len(content)} bytes)"
        )

    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        import pypdf  # local import keeps startup cost zero when unused

        reader = pypdf.PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)

    if ext == ".docx":
        import docx  # python-docx

        doc = docx.Document(io.BytesIO(content))
        paragraphs = [para.text for para in doc.paragraphs]
        return "\n".join(paragraphs)

    if ext == ".txt":
        return content.decode("utf-8", errors="replace")

    if ext == ".csv":
        # CSV text is returned as-is; chunk_csv() handles the grouping.
        return content.decode("utf-8", errors="replace")

    raise ValueError(f"Unsupported file type: {ext}")


# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------


def chunk_text(text: str) -> list[str]:
    """Split *text* into token-bounded chunks with overlap.

    Uses tiktoken's cl100k_base encoding (same as OpenAI's embeddings).
    Chunks are CHUNK_TOKENS tokens wide with CHUNK_OVERLAP_TOKENS token
    overlap between adjacent chunks.

    Args:
        text: Plain-text content to chunk.

    Returns:
        List of non-empty chunk strings.
    """
    enc = tiktoken.get_encoding("cl100k_base")
    tokens: list[int] = enc.encode(text)

    chunks: list[str] = []
    step = CHUNK_TOKENS - CHUNK_OVERLAP_TOKENS
    start = 0

    while start < len(tokens):
        window = tokens[start : start + CHUNK_TOKENS]
        decoded = enc.decode(window)
        if decoded.strip():
            chunks.append(decoded)
        start += step

    logger.debug("chunk_text: %d tokens -> %d chunks", len(tokens), len(chunks))
    return chunks


def chunk_csv(content: bytes) -> list[str]:
    """Split CSV bytes into multi-row string chunks.

    Each chunk contains the header row followed by up to CSV_ROWS_PER_CHUNK
    data rows.  The header is repeated in every chunk so each chunk is
    self-contained.

    Args:
        content: Raw CSV bytes (UTF-8 encoded).

    Returns:
        List of non-empty chunk strings.
    """
    text = content.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))

    rows = list(reader)
    if not rows:
        return []

    header = rows[0]
    data_rows = rows[1:]

    chunks: list[str] = []
    for i in range(0, max(len(data_rows), 1), CSV_ROWS_PER_CHUNK):
        batch = data_rows[i : i + CSV_ROWS_PER_CHUNK]
        if not batch:
            break
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(header)
        writer.writerows(batch)
        chunk_str = buf.getvalue().strip()
        if chunk_str:
            chunks.append(chunk_str)

    logger.debug("chunk_csv: %d data rows -> %d chunks", len(data_rows), len(chunks))
    return chunks


def chunk_file(filename: str, content: bytes) -> list[str]:
    """Dispatch to the correct chunker based on file extension.

    Args:
        filename: Original file name.
        content:  Raw file bytes.

    Returns:
        List of non-empty chunk strings.
    """
    ext = Path(filename).suffix.lower()
    if ext == ".csv":
        return chunk_csv(content)
    text = parse_file(filename, content)
    return chunk_text(text)


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


async def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Embed a list of text chunks using OpenAI's embedding model.

    Batches requests in groups of EMBED_BATCH_SIZE to stay within API limits.

    Args:
        chunks: List of text strings to embed.

    Returns:
        Flat list of embedding vectors aligned with *chunks*.
    """
    client = openai.AsyncOpenAI(api_key=get_settings().openai_api_key)
    embeddings: list[list[float]] = []

    for i in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[i : i + EMBED_BATCH_SIZE]
        logger.debug(
            "embed_chunks: embedding batch %d-%d of %d",
            i,
            i + len(batch),
            len(chunks),
        )
        response = await client.embeddings.create(model=EMBED_MODEL, input=batch)
        # Response items are ordered by index, matching our batch order.
        batch_vectors = [item.embedding for item in response.data]
        embeddings.extend(batch_vectors)

    return embeddings


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------


async def delete_document(
    db: AsyncSession, client_id: str, doc_name: str
) -> int:
    """Delete all embedding chunks for a given (client_id, doc_name) pair.

    Args:
        db:        Active async SQLAlchemy session.
        client_id: The tenant/client identifier.
        doc_name:  The document name (filename).

    Returns:
        Number of rows deleted.
    """
    stmt = (
        delete(Embedding)
        .where(Embedding.client_id == client_id)
        .where(Embedding.doc_name == doc_name)
    )
    result = await db.execute(stmt)
    await db.commit()
    deleted = result.rowcount
    logger.info(
        "delete_document: removed %d chunks for client=%s doc=%s",
        deleted,
        client_id,
        doc_name,
    )
    return deleted


async def ingest_document(
    db: AsyncSession, client_id: str, filename: str, content: bytes
) -> dict:
    """Parse, embed, and store a document for a given client.

    Re-ingestion of a document with the same filename replaces all prior
    chunks cleanly (delete-then-insert).

    Args:
        db:        Active async SQLAlchemy session.
        client_id: The tenant/client identifier.
        filename:  Original file name (used for parsing + stored as doc_name).
        content:   Raw file bytes.

    Returns:
        Dict with ``doc_name`` and ``chunks_ingested`` keys.

    Raises:
        ValueError: If the file produces no content after parsing.
    """
    chunks = chunk_file(filename, content)
    if not chunks:
        raise ValueError("Document produced no content after parsing")

    vectors = await embed_chunks(chunks)

    # Replace any prior version of this document.
    await delete_document(db, client_id, filename)

    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        db.add(
            Embedding(
                client_id=client_id,
                doc_name=filename,
                chunk_index=i,
                content=chunk,
                embedding=vector,
            )
        )

    await db.commit()
    logger.info(
        "ingest_document: stored %d chunks for client=%s doc=%s",
        len(chunks),
        client_id,
        filename,
    )
    return {"doc_name": filename, "chunks_ingested": len(chunks)}


__all__ = [
    "MAX_FILE_BYTES",
    "CHUNK_TOKENS",
    "CHUNK_OVERLAP_TOKENS",
    "CSV_ROWS_PER_CHUNK",
    "EMBED_MODEL",
    "EMBED_BATCH_SIZE",
    "SIMILARITY_THRESHOLD",
    "parse_file",
    "chunk_text",
    "chunk_csv",
    "chunk_file",
    "embed_chunks",
    "delete_document",
    "ingest_document",
]
