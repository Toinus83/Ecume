import type {
  DashboardStats,
  AnalysisJob,
  ExtractedCard,
  GraphPayload,
  KnowledgeEdge,
  KnowledgeNode,
  LLMSettings,
  LLMTestResult,
  SourceDocument
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
  dashboard: () => request<DashboardStats>("/dashboard"),
  documents: () => request<SourceDocument[]>("/documents"),
  uploadDocument: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<SourceDocument>("/documents/upload", { method: "POST", body: data });
  },
  analyzeDocument: (documentId: string) =>
    request<AnalysisJob>(`/documents/${documentId}/analyze`, { method: "POST" }),
  job: (jobId: string) => request<AnalysisJob>(`/jobs/${jobId}`),
  jobs: () => request<AnalysisJob[]>("/jobs"),
  cards: () => request<ExtractedCard[]>("/cards"),
  updateCard: (cardId: string, payload: Partial<ExtractedCard>) =>
    request<ExtractedCard>(`/cards/${cardId}/update`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  acceptCard: (cardId: string, orphan = false) =>
    request<ExtractedCard>(`/cards/${cardId}/accept?orphan=${String(orphan)}`, { method: "POST" }),
  mergeCard: (cardId: string, targetCardId: string) =>
    request<ExtractedCard>(`/cards/${cardId}/merge`, {
      method: "POST",
      body: JSON.stringify({ target_card_id: targetCardId })
    }),
  graph: (filter = "all", nodeId?: string) =>
    request<GraphPayload>(`/graph?filter=${filter}${nodeId ? `&node_id=${nodeId}` : ""}`),
  createEdge: (payload: Partial<KnowledgeEdge>) =>
    request<KnowledgeEdge>("/graph/edges", { method: "POST", body: JSON.stringify(payload) }),
  deleteEdge: (edgeId: string) =>
    request<{ deleted_edge: KnowledgeEdge }>(`/graph/edges/${edgeId}`, { method: "DELETE" }),
  deleteNode: (nodeId: string) =>
    request<{ deleted_node: KnowledgeNode; deleted_edge_ids: string[] }>(`/graph/nodes/${nodeId}`, {
      method: "DELETE"
    }),
  orphans: () => request<KnowledgeNode[]>("/graph/orphans"),
  llmSettings: () => request<LLMSettings>("/admin/llm"),
  saveLlmSettings: (payload: LLMSettings) =>
    request<LLMSettings>("/admin/llm", { method: "PUT", body: JSON.stringify(payload) }),
  testLlmSettings: () => request<LLMTestResult>("/admin/llm/test", { method: "POST" }),
  resetDatabase: (payload: { confirmation: string; delete_uploads: boolean; delete_exports: boolean }) =>
    request<{ ok: boolean; message: string; deleted_uploads: number; deleted_exports: number }>(
      "/admin/database/reset",
      { method: "POST", body: JSON.stringify(payload) }
    ),
  exportUrl: (kind: "json" | "jsonld" | "csv" | "memgraph" | "rdf-skos") =>
    `${API_BASE}/export/${kind}`
};
