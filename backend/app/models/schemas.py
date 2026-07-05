from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


NodeType = Literal["effect", "object", "action", "condition", "task", "theme"]
Level = Literal["strategic", "operational", "tactical", "operator", "unknown"]
Confidence = Literal["low", "medium", "high"]
Status = Literal["proposed", "accepted", "accepted_orphan", "linked", "to_confirm"]
RelationType = Literal[
    "contribue à",
    "se décompose en",
    "concerne",
    "nécessite",
    "déclenche",
    "proche de",
    "équivalent à",
]


class SourceDocument(BaseModel):
    id: str
    title: str
    filename: str
    file_type: str
    content_text: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SuggestedLink(BaseModel):
    source_label: str
    target_existing_node_id: str | None = None
    target_label: str | None = None
    relation_type: str = "proche de"
    confidence: Confidence = "medium"
    reason: str = ""


class MainEffect(BaseModel):
    label: str
    description: str = ""
    level: Level = "unknown"
    confidence: Confidence = "medium"


class ExtractedCard(BaseModel):
    id: str
    document_id: str
    theme_label: str
    main_effect: MainEffect
    level: Level
    objects: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    secondary_effects: list[str] = Field(default_factory=list)
    suggested_links: list[SuggestedLink] = Field(default_factory=list)
    confidence: Confidence = "medium"
    status: Status = "proposed"
    validation_status: Status = "proposed"
    source_excerpt: str = ""
    warnings: list[str] = Field(default_factory=list)
    graph_node_ids: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class KnowledgeNodeIn(BaseModel):
    label: str
    type: NodeType
    description: str = ""
    level: Level = "unknown"
    status: Status = "proposed"
    confidence: Confidence = "medium"
    source_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeNode(KnowledgeNodeIn):
    id: str
    validation_status: Status = "proposed"
    created_at: str
    updated_at: str


class KnowledgeEdgeIn(BaseModel):
    source_node_id: str
    target_node_id: str
    relation_type: str
    label: str | None = None
    status: Status = "proposed"
    confidence: Confidence = "medium"
    source_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeEdge(KnowledgeEdgeIn):
    id: str
    label: str
    created_at: str
    updated_at: str


class CardUpdate(BaseModel):
    theme_label: str | None = None
    main_effect: MainEffect | None = None
    level: Level | None = None
    objects: list[str] | None = None
    actions: list[str] | None = None
    conditions: list[str] | None = None
    tasks: list[str] | None = None
    suggested_links: list[SuggestedLink] | None = None
    status: Status | None = None
    validation_status: Status | None = None


class MergeCardRequest(BaseModel):
    target_card_id: str


class ManualCardRequest(BaseModel):
    document_id: str | None = None
    theme_label: str
    main_effect: MainEffect
    level: Level = "unknown"
    objects: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    source_excerpt: str = ""


class MergeNodeRequest(BaseModel):
    target_node_id: str
    relation_note: str = ""


class AliasRequest(BaseModel):
    label: str
    kind: Literal["synonym", "variant", "former_label"] = "variant"
    source_id: str | None = None


class LLMSettings(BaseModel):
    llm_provider: Literal["ollama", "api"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    external_llm_api_key: str = ""
    external_llm_base_url: str = ""
    external_llm_model: str = ""
    allow_llm_fallback: bool = False


class ResetDatabaseRequest(BaseModel):
    confirmation: str
    delete_uploads: bool = True
    delete_exports: bool = True


class AnalysisResponse(BaseModel):
    document_id: str
    cards: list[ExtractedCard]
    warnings: list[str] = Field(default_factory=list)


class DashboardStats(BaseModel):
    documents: int
    effects: int
    objects: int
    actions: int
    conditions: int
    tasks: int
    links: int
    orphans: int
