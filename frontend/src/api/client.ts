import type {
  DashboardStats,
  AnalysisJob,
  ExtractedCard,
  GraphPayload,
  KnowledgeEdge,
  KnowledgeNode,
  LLMSettings,
  LLMTestResult,
  SourceDocument,
  RetentionPolicy,
  ValidationSettings,
  GraphSearchResult,
  SuggestedLink,
  ReferenceRepository,
  ReferenceTerm,
  EchoMapping
} from "../types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: options?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `Erreur HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  baseUrl: API_BASE,
  references: () => request<ReferenceRepository[]>("/references"),
  echoExportUrl: (id: string, format: "json" | "csv") => API_BASE+"/references/"+encodeURIComponent(id)+"/export/"+format,
  echoMappings: (node_id = "", repository_id = "") => request<EchoMapping[]>(`/references/mappings?${new URLSearchParams({node_id,repository_id})}`),
  searchEchoMappings: (node_id = "", repository_id = "") => request<Record<string,number>>("/references/mappings/search", {method:"POST",body:JSON.stringify({node_id,repository_id})}),
  decideEchoMapping: (id: string, match_type: string, status: string) => request<EchoMapping>(`/references/mappings/${id}`, {method:"PATCH",body:JSON.stringify({match_type,status})}),
  importReference: (file: File) => {
    const body = new FormData(); body.append("file", file);
    return request<ReferenceRepository>("/references/import", { method: "POST", body });
  },
  referenceTerms: (id: string, q = "", offset = 0) => request<{ items: ReferenceTerm[]; total: number; has_more: boolean }>(`/references/${id}/terms?${new URLSearchParams({q, offset: String(offset)})}`),
  activateReference: (id: string, active: boolean) => request<ReferenceRepository>(`/references/${id}`, {method:"PATCH", body:JSON.stringify({active})}),
  deleteReference: (id: string, confirmation: string) => request(`/references/${id}`, {method:"DELETE", body:JSON.stringify({confirmation})}),
  validationSettings: () => request<ValidationSettings>("/validation/settings"),
  saveValidationSettings: (settings: ValidationSettings) => request<ValidationSettings>("/validation/settings", {
    method: "PUT", body: JSON.stringify(settings)
  }),
  applyValidation: (settings: ValidationSettings, card_ids: string[]) => request<{ counts: Record<string, number> }>("/validation/apply", {
    method: "POST", body: JSON.stringify({ settings, card_ids })
  }),
  dashboard: () => request<DashboardStats>("/dashboard"),
  documents: () => request<SourceDocument[]>("/documents"),
  importSettings: () => request<{ retention_policy: RetentionPolicy }>("/imports/settings"),
  saveImportSettings: (retention_policy: RetentionPolicy) => request("/imports/settings", {
    method: "PUT", body: JSON.stringify({ retention_policy })
  }),
  documentRetention: (id: string, retention_policy: RetentionPolicy) => request<SourceDocument>(`/documents/${id}/retention`, {
    method: "PUT", body: JSON.stringify({ retention_policy })
  }),
  purgeSource: (id: string) => request<SourceDocument>(`/documents/${id}/purge`, { method: "POST" }),
  restoreSource: (id: string, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<SourceDocument>(`/documents/${id}/source`, { method: "POST", body: data });
  },
  deleteDocument: (id: string, payload: { confirmation: string; delete_knowledge: boolean; knowledge_confirmation: string }) =>
    request<{ deleted_cards: number; deleted_nodes: number }>(`/documents/${id}`, { method: "DELETE", body: JSON.stringify(payload) }),
  uploadDocument: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<SourceDocument>("/documents/upload", { method: "POST", body: data });
  },
  analyzeDocument: (documentId: string, settings?: ValidationSettings, extractionMode = "sober") =>
    request<AnalysisJob>(`/documents/${documentId}/analyze?extraction_mode=${encodeURIComponent(extractionMode)}`, { method: "POST", body: settings ? JSON.stringify(settings) : undefined }),
  decideConcept: (cardId: string, proposalId: string, action: "retain" | "ignore") => request<ExtractedCard>(`/cards/${cardId}/concept-proposals/${proposalId}/${action}`, { method: "POST" }),
  job: (jobId: string) => request<AnalysisJob>(`/jobs/${jobId}`),
  jobs: () => request<AnalysisJob[]>("/jobs"),
  cards: () => request<ExtractedCard[]>("/cards"),
  deleteCard: (cardId: string) => request(`/cards/${cardId}`, { method: "DELETE" }),
  detachConcept: (cardId: string, nodeId: string) =>
    request<ExtractedCard>(`/cards/${cardId}/concepts/${nodeId}`, { method: "DELETE" }),
  decideSuggestion: (cardId: string, suggestionId: string, status: SuggestedLink["status"]) =>
    request<SuggestedLink>(`/cards/${cardId}/suggestions/${suggestionId}/decision`, {
      method: "POST", body: JSON.stringify({ status })
    }),
  updateCard: (cardId: string, payload: Partial<ExtractedCard>) =>
    request<ExtractedCard>(`/cards/${cardId}/update`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  repairSuggestion: (cardId: string, suggestionId: string, payload: { source_node_id: string; target_node_id: string; relation_type: string }) =>
    request<SuggestedLink>(`/cards/${cardId}/suggestions/${suggestionId}/repair`, { method: "POST", body: JSON.stringify(payload) }),
  createSuggestionTarget: (cardId: string, suggestionId: string, payload: { source_node_id: string; relation_type: string; label: string; type: string; description: string }) =>
    request<SuggestedLink>(`/cards/${cardId}/suggestions/${suggestionId}/target`, { method: "POST", body: JSON.stringify(payload) }),
  acceptCard: (cardId: string, orphan = false) =>
    request<ExtractedCard>(`/cards/${cardId}/accept?orphan=${String(orphan)}`, { method: "POST" }),
  mergeCard: (cardId: string, targetCardId: string) =>
    request<ExtractedCard>(`/cards/${cardId}/merge`, {
      method: "POST",
      body: JSON.stringify({ target_card_id: targetCardId })
    }),
  graph: (filter = "all", nodeId?: string, scope = "validated") =>
    request<GraphPayload>(`/graph?filter=${filter}&scope=${scope}${nodeId ? `&node_id=${nodeId}` : ""}`),
  createEdge: (payload: Partial<KnowledgeEdge>) =>
    request<KnowledgeEdge>("/graph/edges", { method: "POST", body: JSON.stringify(payload) }),
  deleteEdge: (edgeId: string) =>
    request<{ deleted_edge: KnowledgeEdge }>(`/graph/edges/${edgeId}`, { method: "DELETE" }),
  deleteNode: (nodeId: string) =>
    request<{ deleted_node: KnowledgeNode; deleted_edge_ids: string[] }>(`/graph/nodes/${nodeId}`, {
      method: "DELETE"
    }),
  orphans: () => request<KnowledgeNode[]>("/graph/orphans"),
  searchGraph: (query: string) => request<GraphSearchResult[]>(`/graph/search?q=${encodeURIComponent(query)}`),
  searchTargets: (query: string, sourceId = "", documentId = "", scope = "all", offset = 0, nodeType = "") =>
    request<{ items: (KnowledgeNode & { already_linked: boolean })[]; total: number; has_more: boolean }>(`/graph/targets?${new URLSearchParams({ q: query, source_id: sourceId, document_id: documentId, scope, offset: String(offset), node_type: nodeType })}`),
  updateOrphan: (nodeId: string, payload: { label?: string; business_category?: string; level?: string; target_node_id?: string; relation_type?: string; orphan_status?: string }) =>
    request(`/graph/nodes/${nodeId}/orphan`, { method: "POST", body: JSON.stringify(payload) }),
  llmSettings: () => request<LLMSettings>("/admin/llm"),
  saveLlmSettings: (payload: LLMSettings) =>
    request<LLMSettings>("/admin/llm", { method: "PUT", body: JSON.stringify(payload) }),
  testLlmSettings: () => request<LLMTestResult>("/admin/llm/test", { method: "POST" }),
  resetDatabase: (payload: { confirmation: string; delete_uploads: boolean; delete_exports: boolean }) =>
    request<{ ok: boolean; message: string; deleted_uploads: number; deleted_exports: number }>(
      "/admin/database/reset",
      { method: "POST", body: JSON.stringify(payload) }
    ),
  exportUrl: (kind: "json" | "jsonld" | "csv" | "memgraph" | "rdf-skos" | "archimate-json") =>
    `${API_BASE}/export/${kind}`
};
