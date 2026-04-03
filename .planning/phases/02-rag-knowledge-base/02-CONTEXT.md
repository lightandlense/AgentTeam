# Phase 2: RAG Knowledge Base - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Document ingestion pipeline (PDF, DOCX, TXT, CSV → fixed-size chunks → OpenAI embeddings → vector store) and RAG query handler (caller question → similarity search → Claude Haiku generates grounded answer, or transfers to team if no confident match found). Admin panel for uploading and managing documents. Scheduling, outreach, and other voice agent capabilities are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Document Ingestion Interface
- Web admin panel with file upload form (not raw API)
- Re-uploading a document appends new chunks alongside existing ones (no automatic replacement)
- Delete button per document — removes all chunks for that document
- Supported file types at launch: PDF, DOCX, TXT, CSV
- Ingestion is synchronous — admin waits for upload to fully process before getting confirmation
- Enforce a document size cap (exact limit at Claude's discretion, e.g. 10MB)

### Fallback Behavior
- When no documents match a caller's question: transfer to the team ("I'm not sure about that — let me transfer you")
- Low confidence matches are treated as no match — err on the side of caution, no hedging answers
- Similarity threshold value and number of chunks to retrieve are at Claude's discretion

### Answer Generation
- Conversational and natural — sounds like a knowledgeable staff member, not a database readout
- No attribution — answers never mention that information came from a document
- Answer length matches complexity: short for simple questions, more detail when the topic needs it

### Chunking Strategy
- Fixed-size chunks with overlap (exact token size and overlap at Claude's discretion)
- CSV files: group multiple rows per chunk (e.g. 10 rows) for more retrieval context
- Text/PDF/DOCX: fixed-size token chunking with overlap

### Claude's Discretion
- Exact similarity threshold value
- Number of chunks retrieved per query (top-N)
- Exact chunk size and overlap in tokens
- Exact document size cap value
- Grounding strictness (strict doc-only vs. light common-sense inference)

</decisions>

<specifics>
## Specific Ideas

- This is for appliance repair businesses — answers should sound like a knowledgeable repair shop staff member speaking on the phone
- Transfer (not callback offer) is the preferred fallback — matches the voice persona's role as a receptionist routing calls

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-rag-knowledge-base*
*Context gathered: 2026-04-03*
