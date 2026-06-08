1from typing import Any, Dict, List, Optional

from postgrest.exceptions import APIError

from .client import get_supabase_service_client
from .models import (
    Client,
    ClientDocumentChunk,
    ClientEvent,
    ClientProfile,
    Conversation,
    DocumentMetadata,
    KnowledgeBaseChunk,
    NutritionPlan,
    SystemSetting,
    Task,
)


def _service_client():
    return get_supabase_service_client()


def _extract_data(response: Any) -> Any:
    return getattr(response, "data", None)


def _execute_single(request: Any) -> Any:
    try:
        response = request.execute()
        return _extract_data(response)
    except APIError as err:
        payload = err.args[0] if err.args else None
        if isinstance(payload, str) and "PGRST116" in payload:
            return None
        if isinstance(payload, dict) and payload.get("code") == "PGRST116":
            return None
        raise


def insert_document_metadata(metadata: DocumentMetadata) -> Any:
    supabase = _service_client()
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
    return _extract_data(
        supabase.table("document_metadata").insert(payload).select("*").execute()
    )


def get_document_metadata(document_id: str) -> Optional[Dict[str, Any]]:
    supabase = _service_client()
    return _execute_single(
        supabase.table("document_metadata").select("*").eq("id", document_id).single()
    )


def insert_knowledge_base_chunk(chunk: KnowledgeBaseChunk) -> Any:
    supabase = _service_client()
    payload = {
        "document_id": str(chunk.document_id),
        "chunk_index": chunk.chunk_index,
        "chunk_text": chunk.chunk_text,
        "embedding": chunk.embedding,
        "source": chunk.source,
    }
    return _extract_data(
        supabase.table("knowledge_base").insert(payload).select("*").execute()
    )


def insert_client_document_chunk(chunk: ClientDocumentChunk) -> Any:
    supabase = _service_client()
    payload = {
        "client_id": str(chunk.client_id),
        "document_id": str(chunk.document_id),
        "chunk_index": chunk.chunk_index,
        "chunk_text": chunk.chunk_text,
        "embedding": chunk.embedding,
    }
    return _extract_data(
        supabase.table("client_documents").insert(payload).select("*").execute()
    )


def get_client_by_id(client_id: str) -> Optional[Dict[str, Any]]:
    supabase = _service_client()
    return _execute_single(
        supabase.table("clients").select("*").eq("id", client_id).single()
    )


def get_client_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    supabase = _service_client()
    return _execute_single(
        supabase.table("clients").select("*").eq("telegram_id", telegram_id).single()
    )


def get_active_nutrition_plan(client_id: str) -> Optional[Dict[str, Any]]:
    supabase = _service_client()
    return _execute_single(
        supabase.table("nutrition_plans")
        .select("*")
        .eq("client_id", client_id)
        .eq("is_active", True)
        .single()
    )


def get_tasks_by_client(client_id: str) -> List[Dict[str, Any]]:
    supabase = _service_client()
    response = (
        supabase.table("tasks").select("*").eq("client_id", client_id).execute()
    )
    return _extract_data(response) or []


def get_system_setting(key: str) -> Optional[Dict[str, Any]]:
    supabase = _service_client()
    return _execute_single(
        supabase.table("system_settings").select("*").eq("key", key).single()
    )


def get_all_system_settings() -> List[Dict[str, Any]]:
    supabase = _service_client()
    response = supabase.table("system_settings").select("*").execute()
    return _extract_data(response) or []


def get_knowledge_base_chunks(document_id: str) -> List[Dict[str, Any]]:
    supabase = _service_client()
    response = (
        supabase.table("knowledge_base")
        .select("*")
        .eq("document_id", document_id)
        .execute()
    )
    return _extract_data(response) or []


def get_client_document_chunks(client_id: str) -> List[Dict[str, Any]]:
    supabase = _service_client()
    response = (
        supabase.table("client_documents")
        .select("*")
        .eq("client_id", client_id)
        .execute()
    )
    return _extract_data(response) or []
