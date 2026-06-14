-- =============================================
-- МИГРАЦИЯ 002: RPC-функции семантического поиска (pgvector)
-- Дата: 14 июня 2026
-- Описание: Добавляет cosine-поиск по эмбеддингам для knowledge_base и
--           client_documents. Размерность vector(1536) = OpenAI ada-002.
-- Стиль: SECURITY INVOKER + SET search_path (как триггеры в schema.sql).
-- Применить: Supabase → SQL Editor.
-- =============================================

-- ---------------------------------------------
-- 1. Поиск по базе знаний нутрициолога
-- ---------------------------------------------
-- query_embedding       — вектор запроса (1536), считается в utils/knowledge.py
-- match_count           — сколько чанков вернуть
-- similarity_threshold  — минимальная cosine-близость (0..1), 0 = без фильтра
CREATE OR REPLACE FUNCTION match_knowledge_base(
    query_embedding vector(1536),
    match_count int DEFAULT 5,
    similarity_threshold float DEFAULT 0.0
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    chunk_index int,
    chunk_text text,
    source text,
    similarity float
)
SECURITY INVOKER
SET search_path = public, pg_temp
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        kb.id,
        kb.document_id,
        kb.chunk_index,
        kb.chunk_text,
        kb.source,
        (1 - (kb.embedding <=> query_embedding))::float AS similarity
    FROM knowledge_base kb
    WHERE kb.embedding IS NOT NULL
      AND (1 - (kb.embedding <=> query_embedding)) >= similarity_threshold
    ORDER BY kb.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ---------------------------------------------
-- 2. Поиск по документам конкретного клиента
-- ---------------------------------------------
-- p_client_id — изоляция: ищем только в документах этого клиента
CREATE OR REPLACE FUNCTION match_client_documents(
    query_embedding vector(1536),
    p_client_id uuid,
    match_count int DEFAULT 5,
    similarity_threshold float DEFAULT 0.0
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    chunk_index int,
    chunk_text text,
    similarity float
)
SECURITY INVOKER
SET search_path = public, pg_temp
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        cd.id,
        cd.document_id,
        cd.chunk_index,
        cd.chunk_text,
        (1 - (cd.embedding <=> query_embedding))::float AS similarity
    FROM client_documents cd
    WHERE cd.client_id = p_client_id
      AND cd.embedding IS NOT NULL
      AND (1 - (cd.embedding <=> query_embedding)) >= similarity_threshold
    ORDER BY cd.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- =============================================
-- ПРОВЕРКА: функции зарегистрированы
-- =============================================
SELECT proname, pg_get_function_identity_arguments(oid) AS args
FROM pg_proc
WHERE proname IN ('match_knowledge_base', 'match_client_documents');

-- =============================================
-- РЕЗУЛЬТАТ:
-- ✅ match_knowledge_base(query_embedding, match_count, similarity_threshold)
-- ✅ match_client_documents(query_embedding, p_client_id, match_count, similarity_threshold)
-- ✅ Cosine-близость через оператор <=> (использует ivfflat-индексы)
-- ✅ SECURITY INVOKER + search_path — соответствует Security Advisor
-- Вызов из Python: supabase.rpc("match_knowledge_base", {...})
-- =============================================
