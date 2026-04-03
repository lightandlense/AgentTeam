-- Enable pgvector extension (must run before table creation)
CREATE EXTENSION IF NOT EXISTS vector;

-- clients table
CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    business_name TEXT NOT NULL,
    business_address TEXT,
    timezone TEXT NOT NULL DEFAULT 'America/Chicago',
    owner_email TEXT NOT NULL,
    twilio_number TEXT,
    retell_agent_id TEXT,
    services JSONB DEFAULT '[]'::jsonb,
    hours JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- oauth_tokens table
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id SERIAL PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    encrypted_access_token TEXT NOT NULL,
    encrypted_refresh_token TEXT NOT NULL,
    token_expiry TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- embeddings table (vector dimension 1536 for OpenAI text-embedding-3-small)
CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    doc_name TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ivfflat index for cosine similarity search on embeddings
-- lists=100 is appropriate for up to ~1M vectors; adjust down for small datasets
CREATE INDEX IF NOT EXISTS embeddings_embedding_idx
    ON embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
