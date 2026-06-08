from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


@dataclass
class User:
    id: Optional[UUID] = None
    auth_id: Optional[UUID] = None
    role: str = "client"
    email: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class Client:
    id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    telegram_id: Optional[int] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    language: str = "ru"
    timezone: str = "Asia/Dubai"
    payment_status: str = "trial"
    access_status: str = "active"
    client_status: str = "lead"
    nutritionist_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class ClientProfile:
    client_id: Optional[UUID] = None
    age: Optional[int] = None
    weight: Optional[float] = None
    height: Optional[int] = None
    gender: Optional[str] = None
    goals: Optional[str] = None
    restrictions: List[str] = field(default_factory=list)
    allergies: List[str] = field(default_factory=list)
    chronic_conditions: List[str] = field(default_factory=list)
    onboarding_completed_at: Optional[datetime] = None
    custom_alert_thresholds: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WellnessPlan:
    id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    sleep_target: Optional[str] = None
    activity_target: Optional[str] = None
    recovery: Optional[str] = None
    stress_level: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Conversation:
    id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    message_timestamp: Optional[datetime] = None
    channel: Optional[str] = None
    conversation_type: Optional[str] = None
    role: Optional[str] = None
    thread_id: Optional[str] = None
    message_text: Optional[str] = None
    metadata_json: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None


@dataclass
class ClientEvent:
    id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    event_type: Optional[str] = None
    severity: Optional[str] = None
    event_date: Optional[datetime] = None
    payload_json: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None


@dataclass
class NutritionPlan:
    id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    version: Optional[int] = None
    title: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    is_active: Optional[bool] = True
    plan_json: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[str] = "pending"
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class NotificationSchedule:
    id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    notification_type: Optional[str] = None
    scheduled_time: Optional[str] = None
    timezone: Optional[str] = None
    is_active: Optional[bool] = True
    updated_at: Optional[datetime] = None


@dataclass
class AuditLog:
    id: Optional[UUID] = None
    actor_type: Optional[str] = None
    actor_id: Optional[UUID] = None
    action: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    old_value: Dict[str, Any] = field(default_factory=dict)
    new_value: Dict[str, Any] = field(default_factory=dict)
    action_timestamp: Optional[datetime] = None


@dataclass
class SystemSetting:
    key: str
    value: Optional[str] = None
    description: Optional[str] = None
    updated_at: Optional[datetime] = None


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
