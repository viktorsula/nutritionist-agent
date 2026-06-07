from typing import Any, Dict, Optional

from .client import get_supabase_service_client
from .models import ClientDocumentChunk, DocumentMetadata, KnowledgeBaseChunk


def insert_document_metadata(metadata: DocumentMetadata) -> Any:
    supabase = get_supabase_service_client()
    payload: Dict[str, Any] = {
        "source": metadata.source,
        "external_id": metadata.external_id,
        "client_id": str(metadata.client_id) if metadata.client_id else None,
        "document_type": metadata.document_type,
        "title": metadata.title,
        "description": metadata.description,
        "mime_type": metadata.mime_type,
        "storage_url": metadata.storage_url,
        "file_name": metadata.file_name,
        "file_size_bytes": metadata.file_size_bytes,
        "extracted_text": metadata.extracted_text,
        "metadata": metadata.metadata,
    }
    return supabase.table("document_metadata").insert(payload).select("*").execute()


def get_document_metadata(document_id: str) -> Any:
    supabase = get_supabase_service_client()
    return (
        supabase.table("document_metadata")
        .select("*")
        .eq("id", document_id)
        .single()
        .execute()
    )


def insert_knowledge_base_chunk(chunk: KnowledgeBaseChunk) -> Any:
    supabase = get_supabase_service_client()
    payload = {
        "document_id": str(chunk.document_id),
        "chunk_index": chunk.chunk_index,
        "chunk_text": chunk.chunk_text,
        "embedding": chunk.embedding,
        "source": chunk.source,
    }
    return supabase.table("knowledge_base").insert(payload).select("*").execute()


def insert_client_document_chunk(chunk: ClientDocumentChunk) -> Any:
    supabase = get_supabase_service_client()
    payload = {
        "client_id": str(chunk.client_id),
        "document_id": str(chunk.document_id),
        "chunk_index": chunk.chunk_index,
        "chunk_text": chunk.chunk_text,
        "embedding": chunk.embedding,
    }
    return supabase.table("client_documents").insert(payload).select("*").execute()
