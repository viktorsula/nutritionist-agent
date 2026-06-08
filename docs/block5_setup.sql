-- =============================================
-- БЛОК 5 — ДОКУМЕНТЫ И PGVECTOR
-- Выполнить в Supabase → SQL Editor
-- Источник: docs/schema.sql (строки 6, 138-177)
-- =============================================

-- 1. Включить расширение pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Метаданные документов
CREATE TABLE document_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    external_id TEXT,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    document_type TEXT CHECK (document_type IN ('knowledge_base', 'client_document', 'report', 'other')) DEFAULT 'other',
    title TEXT,
    description TEXT,
    mime_type TEXT,
    storage_url TEXT,
    file_name TEXT,
    file_size_bytes BIGINT,
    extracted_text TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 3. База знаний (общая, чанки с эмбеддингами)
CREATE TABLE knowledge_base (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES document_metadata(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    embedding vector(1536),
    source TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 4. Документы клиентов (чанки с эмбеддингами)
CREATE TABLE client_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    document_id UUID REFERENCES document_metadata(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 5. Индексы для векторного поиска (ivfflat, cosine distance)
CREATE INDEX IF NOT EXISTS idx_knowledge_base_embedding ON knowledge_base USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_client_documents_embedding ON client_documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
