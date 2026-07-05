export type Level = "strategic" | "operational" | "tactical" | "operator" | "unknown";
export type Confidence = "low" | "medium" | "high";
export type CardStatus = "proposed" | "accepted" | "accepted_orphan" | "linked" | "to_confirm";
export type NodeType = "effect" | "object" | "action" | "condition" | "task" | "theme";

export interface SourceDocument {
  id: string;
  title: string;
  filename: string;
  file_type: string;
  content_text: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface MainEffect {
  label: string;
  description: string;
  level: Level;
  confidence: Confidence;
}

export interface SuggestedLink {
  source_label: string;
  target_existing_node_id?: string;
  target_label?: string;
  relation_type: string;
  confidence: Confidence;
  reason: string;
}

export interface ExtractedCard {
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
  source_excerpt: string;
  warnings: string[];
  graph_node_ids: Record<string, string | string[]>;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeNode {
  id: string;
  label: string;
  type: NodeType;
  description: string;
  level: Level;
  status: CardStatus;
  validation_status: CardStatus;
  confidence: Confidence;
  created_at: string;
  updated_at: string;
  source_ids: string[];
  metadata: Record<string, unknown>;
  orphan_kind?: string;
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
