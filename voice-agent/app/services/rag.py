"""RAG query service.

Embeds a caller's question using OpenAI text-embedding-3-small, retrieves
the top-N most similar chunks from the client's vector store (pgvector), and
generates a conversational answer using Claude Haiku.

Fallback: returns TRANSFER_SENTINEL when no chunks pass the similarity
threshold, or when Haiku indicates insufficient context.
"""

import logging

import anthropic
import openai
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.ingestion import EMBED_MODEL, SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

TOP_N_CHUNKS: int = 5
TRANSFER_SENTINEL: str = "__TRANSFER__"
HAIKU_MODEL: str = "claude-haiku-4-5"

_SYSTEM_PROMPT: str = (
    "You are a helpful receptionist at an appliance repair shop. Answer the caller's question "
    "naturally and conversationally, as a knowledgeable staff member would on the phone. "
    "Base your answer only on the provided context. Keep answers concise but complete. "
    "Never mention documents, sources, or that you looked anything up. "
    "If the context doesn't contain enough information to answer confidently, say only: __TRANSFER__"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def retrieve_chunks(
    db: AsyncSession, client_id: str, question_embedding: list[float]
) -> list[str]:
    """Retrieve the top-N chunks most similar to *question_embedding*.

    Only returns chunks whose cosine similarity (1 - cosine_distance) is at
    or above SIMILARITY_THRESHOLD.

    Args:
        db:                 Active async SQLAlchemy session.
        client_id:          Tenant/client identifier.
        question_embedding: Embedding vector for the caller's question.

    Returns:
        List of content strings for matching chunks, ordered by similarity
        (most similar first).  May be empty if no chunk passes the threshold.
    """
    sql = text(
        """
        SELECT content
        FROM embeddings
        WHERE client_id = :client_id
          AND (1 - (embedding <=> CAST(:q_vec AS vector))) >= :threshold
        ORDER BY embedding <=> CAST(:q_vec AS vector)
        LIMIT :top_n
        """
    )
    result = await db.execute(
        sql,
        {
            "client_id": client_id,
            "q_vec": str(question_embedding),
            "threshold": SIMILARITY_THRESHOLD,
            "top_n": TOP_N_CHUNKS,
        },
    )
    rows = result.fetchall()
    chunks = [row[0] for row in rows]
    logger.debug(
        "retrieve_chunks: found %d chunks for client=%s", len(chunks), client_id
    )
    return chunks


async def generate_answer(question: str, chunks: list[str]) -> str:
    """Generate a conversational answer using Claude Haiku.

    The answer is grounded solely in the provided *chunks*.  If Haiku
    determines there is insufficient context it returns TRANSFER_SENTINEL.

    Args:
        question: The caller's original question.
        chunks:   Retrieved context chunks.

    Returns:
        A conversational answer string, or TRANSFER_SENTINEL.
    """
    chunks_joined = "\n\n".join(chunks)
    user_message = f"Context:\n{chunks_joined}\n\nQuestion: {question}"

    client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    response = await client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=300,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    answer = response.content[0].text.strip()
    logger.debug("generate_answer: haiku returned %d chars", len(answer))
    return answer


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def answer_question(
    db: AsyncSession, client_id: str, question: str
) -> str:
    """Embed *question*, retrieve relevant chunks, and generate an answer.

    Returns TRANSFER_SENTINEL when:
    - No chunks pass the similarity threshold (no relevant content found).
    - Claude Haiku returns TRANSFER_SENTINEL (insufficient context).

    Args:
        db:        Active async SQLAlchemy session.
        client_id: Tenant/client identifier.
        question:  The caller's question.

    Returns:
        A conversational answer string, or TRANSFER_SENTINEL.
    """
    # 1. Embed the question.
    oai_client = openai.AsyncOpenAI(api_key=get_settings().openai_api_key)
    embed_response = await oai_client.embeddings.create(
        model=EMBED_MODEL, input=[question]
    )
    q_embedding: list[float] = embed_response.data[0].embedding

    # 2. Retrieve matching chunks.
    chunks = await retrieve_chunks(db, client_id, q_embedding)
    if len(chunks) == 0:
        logger.info(
            "answer_question: no chunks above threshold for client=%s — transferring",
            client_id,
        )
        return TRANSFER_SENTINEL

    # 3. Generate answer.
    result = await generate_answer(question, chunks)
    if result == TRANSFER_SENTINEL or TRANSFER_SENTINEL in result:
        logger.info(
            "answer_question: haiku returned transfer sentinel for client=%s", client_id
        )
        return TRANSFER_SENTINEL

    return result


__all__ = [
    "TOP_N_CHUNKS",
    "TRANSFER_SENTINEL",
    "HAIKU_MODEL",
    "retrieve_chunks",
    "generate_answer",
    "answer_question",
]
