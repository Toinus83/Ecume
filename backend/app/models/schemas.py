from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


NodeType = Literal["effect", "object", "action", "condition", "task", "theme"]
Level = Literal["strategic", "operational", "tactical", "operator", "unknown"]
Confidence = Literal["low", "medium", "high"]
Status = Literal["proposed", "accepted", "accepted_orphan", "linked", "to_confirm", "rejected"]
BusinessCategory = Literal[
    "resultat_recherche",
    "objectif_haut_niveau",
    "capacite_a_obtenir",
    "action_activite",
    "chose_metier",
    "donnee_manipulee",
    "condition_regle_contrainte",
    "tache_concrete",
    "acteur_organisation",
    "role_tenu",
    "service_rendu",
    "service_applicatif",
    "element_technique",
    "non_qualifie",
]
BusinessValidationStatus = Literal[
    "proposed",
    "validated_by_user",
    "corrected_by_user",
    "to_review",
    "rejected",
]
MappingStatus = Literal[
    "proposed_by_llm",
    "inferred_from_user_answer",
    "validated_by_user",
    "corrected_by_user",
    "validated_by_architect",
    "rejected",
    "to_review",
    "candidate",
    "unmapped",
    "to_map_later",
]
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


class ArchimateMapping(BaseModel):
    framework: str = "ArchiMate"
    version: str = "3.2"
    candidate_layer: str = "Unknown"
    candidate_element: str = "Unknown"
    confidence: float = 0.3
    reason: str = ""
    status: MappingStatus = "inferred_from_user_answer"


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
    business_category: BusinessCategory = "resultat_recherche"
    business_validation_status: BusinessValidationStatus = "proposed"
    business_justification: str = ""
    archimate_mapping: ArchimateMapping | dict[str, Any] = Field(default_factory=ArchimateMapping)
    archimate_mapping_status: MappingStatus = "proposed_by_llm"
    ontology_mapping_status: MappingStatus = "to_map_later"
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
    business_category: BusinessCategory = "non_qualifie"
    business_validation_status: BusinessValidationStatus = "proposed"
    business_justification: str = ""
    archimate_mapping: ArchimateMapping | dict[str, Any] = Field(default_factory=ArchimateMapping)
    archimate_mapping_status: MappingStatus = "proposed_by_llm"
    ontology_mapping_status: MappingStatus = "to_map_later"
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
    business_category: BusinessCategory | None = None
    business_validation_status: BusinessValidationStatus | None = None
    business_justification: str | None = None
    archimate_mapping: ArchimateMapping | dict[str, Any] | None = None
    archimate_mapping_status: MappingStatus | None = None
    ontology_mapping_status: MappingStatus | None = None


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
