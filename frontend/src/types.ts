export type Level = "strategic" | "operational" | "tactical" | "operator" | "unknown";
export type Confidence = "low" | "medium" | "high";
export type CardStatus = "proposed" | "accepted" | "accepted_orphan" | "linked" | "to_confirm" | "rejected";
export type NodeType = "effect" | "object" | "action" | "condition" | "task" | "theme";
export type BusinessCategory =
  | "resultat_recherche"
  | "objectif_haut_niveau"
  | "capacite_a_obtenir"
  | "action_activite"
  | "chose_metier"
  | "donnee_manipulee"
  | "condition_regle_contrainte"
  | "tache_concrete"
  | "acteur_organisation"
  | "role_tenu"
  | "service_rendu"
  | "service_applicatif"
  | "element_technique"
  | "non_qualifie";
export type BusinessValidationStatus =
  | "auto_validated"
  | "needs_user_validation"
  | "proposed"
  | "validated_by_user"
  | "corrected_by_user"
  | "to_review"
  | "rejected";

export interface ArchimateMapping {
  framework: "ArchiMate" | string;
  version: "3.2" | string;
  candidate_layer: string;
  candidate_element: string;
  confidence: number;
  reason: string;
  status: string;
}

export interface SourceDocument {
  id: string;
  title: string;
  filename: string;
  file_type: string;
  content_text?: string;
  created_at: string;
  metadata: Record<string, unknown>;
  source_status: "retained" | "missing" | "purged" | "purge_pending";
  retention_policy: RetentionPolicy;
  content_hash: string;
  content_length: number;
  source_purged_at?: string;
  source_available: boolean;
  can_reanalyze: boolean;
  latest_job: AnalysisJob | null;
  card_count: number;
  card_counts: Record<"validated" | "auto_validated" | "to_review" | "rejected" | "pending" | "linked", number>;
  concept_counts: Record<"validated" | "auto_validated" | "to_review" | "rejected" | "pending", number>;
}

export type RetentionPolicy = "keep" | "purge_after_success";

export interface ValidationSettings {
  mode: "strict" | "assisted" | "automatic";
  auto_threshold: number;
  review_threshold: number;
}

export interface MainEffect {
  label: string;
  description: string;
  level: Level;
  confidence: Confidence;
}

export interface SuggestedLink {
  business_confidence?: number | null;
  can_accept?: boolean;
  invalid_reason?: string;
  id: string;
  status: "proposed" | "accepted" | "ignored" | "to_review" | "rejected";
  source_node_id?: string;
  source_label: string;
  target_existing_node_id?: string;
  target_label?: string;
  relation_type: string;
  confidence: Confidence;
  reason: string;
}

export type ExtractionMode = "sober" | "balanced" | "exhaustive";
export interface ConceptProposal {
  id: string; role: "objects" | "actions" | "conditions" | "tasks"; label: string;
  importance: "principal" | "secondary" | "weak" | "ignored";
  salience_score: number | null; confidence: number | null; reason: string;
  source_excerpt?: string; active: boolean; retained: boolean; node_id?: string | null;
}

export interface ExtractedCard {
  extraction_details?: { managed?: boolean; mode?: string; concepts?: ConceptProposal[]; rule_details?: string[]; source_excerpts?: string[]; secondary_effects?: string[]; ambiguities?: string[]; source_checks?: { text: string; chunk_index: number; start: number; end: number; origin: string; status: string }[] };
  business_confidence?: number | null;
  validation_decision?: Record<string, unknown>;
  id: string;
  document_id: string;
  theme_label: string;
  main_effect: MainEffect;
  level: Level;
  objects: string[];
  actions: string[];
  conditions: string[];
  tasks: string[];
  secondary_effects: string[];
  suggested_links: SuggestedLink[];
  confidence: Confidence;
  status: CardStatus;
  validation_status: CardStatus;
  business_category: BusinessCategory;
  business_validation_status: BusinessValidationStatus;
  business_justification: string;
  archimate_mapping: ArchimateMapping;
  archimate_mapping_status: string;
  ontology_mapping_status: string;
  source_excerpt: string;
  warnings: string[];
  graph_node_ids: Record<string, string | string[]>;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeNode {
  importance?: "principal" | "secondary" | "weak" | "ignored" | "unclassified";
  business_confidence?: number | null;
  orphan_status?: "" | "accepted_orphan" | "orphan_to_review";
  id: string;
  label: string;
  type: NodeType;
  description: string;
  level: Level;
  status: CardStatus;
  validation_status: CardStatus;
  confidence: Confidence;
  business_category: BusinessCategory;
  business_validation_status: BusinessValidationStatus;
  business_justification: string;
  archimate_mapping: ArchimateMapping;
  archimate_mapping_status: string;
  ontology_mapping_status: string;
  created_at: string;
  updated_at: string;
  source_ids: string[];
  metadata: Record<string, unknown>;
  orphan_kind?: string;
  source_titles?: string[];
  source_card_ids?: string[];
}

export interface GraphSearchResult {
  node: KnowledgeNode;
  neighbors: Array<{ node: KnowledgeNode; edge: KnowledgeEdge }>;
  cards: Array<{ id: string; label: string }>;
}

export interface KnowledgeEdge {
  id: string;
  source_node_id: string;
  target_node_id: string;
  relation_type: string;
  label: string;
  status: CardStatus;
  confidence: Confidence;
  created_at: string;
  updated_at: string;
  source_ids: string[];
  metadata: Record<string, unknown>;
}

export interface GraphPayload {
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
  cytoscape: {
    nodes: Array<{ data: KnowledgeNode }>;
    edges: Array<{ data: KnowledgeEdge & { source: string; target: string } }>;
  };
}

export interface DashboardStats {
  documents: number;
  effects: number;
  objects: number;
  actions: number;
  conditions: number;
  tasks: number;
  links: number;
  orphans: number;
}

export interface LLMSettings {
  llm_provider: "ollama" | "api";
  ollama_base_url: string;
  ollama_model: string;
  external_llm_api_key: string;
  external_llm_base_url: string;
  external_llm_model: string;
  allow_llm_fallback: boolean;
}

export interface LLMTestResult {
  ok: boolean;
  provider: string;
  message: string;
  available_models: string[];
}

export interface AnalysisJob {
  id: string;
  document_id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  step: string;
  message: string;
  current_chunk: number;
  total_chunks: number;
  result_card_ids: string[];
  warnings: string[];
  error: string;
  created_at: string;
  updated_at: string;
  finished_at?: string;
  metadata: Record<string, unknown>;
}
export interface ReferenceProfile {
  status: "partial" | "detected";
  warnings: string[];
  namespaces: Record<string, string>;
  base_uris: string[];
  main_language: string;
  term_count: number;
  relation_count: number;
  triple_count: number;
  owl_class_count: number;
  skos_concept_count: number;
  label_properties: string[];
  alias_properties: string[];
  definition_properties: string[];
  hierarchy_properties: string[];
  associative_properties: string[];
  other_properties: string[];
}

export interface ReferenceRepository {
  id: string; name: string; filename: string; format: string; content_hash: string;
  created_at: string; active: boolean; namespace: string; version: string;
  profile: ReferenceProfile; already_imported?: boolean;
}

export interface ReferenceTerm {
  id: string; repository_id: string; uri: string; label: string; aliases: string[];
  definition: string; comment: string; language: string; types: string[];
}

export interface EchoMapping {
  id: string; node_id: string; node_label: string; repository_id: string; repository_name: string; repository_active: boolean;
  target_uri: string; target_label: string; target_definition: string; target_aliases: string[];
  match_type: string; score: number; reason: string; status: "candidate" | "validated" | "to_review" | "rejected";
  decision_origin: string; created_at: string; updated_at: string; stale: boolean;
}
