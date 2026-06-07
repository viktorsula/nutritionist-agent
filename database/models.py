from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


@dataclass
class DocumentMetadata:
    id: Optional[UUID] = None
    source: str = ""
    external_id: Optional[str] = None
    client_id: Optional[UUID] = None
    document_type: str = "other"
    title: Optional[str] = None
    description: Optional[str] = None
    mime_type: Optional[str] = None
    storage_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None
    extracted_text: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class KnowledgeBaseChunk:
    document_id: UUID
    chunk_index: int
    chunk_text: str
    embedding: List[float]
    source: Optional[str] = None


@dataclass
class ClientDocumentChunk:
    client_id: UUID
    document_id: UUID
    chunk_index: int
    chunk_text: str
    embedding: List[float]
