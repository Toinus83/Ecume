import { DatabaseZap, PlugZap, Save, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { KnowledgeNode, LLMSettings, LLMTestResult, NodeType } from "../types";
import RdfEcosystemSettings from "../components/RdfEcosystemSettings";

interface Props {
  refreshKey: number;
  onChanged: () => void;
}

const emptySettings: LLMSettings = {
  llm_enabled: true,
  llm_provider: "ollama",
  ollama_base_url: "http://localhost:11434",
  ollama_model: "llama3.1",
  external_llm_api_key: "",
  has_external_llm_api_key: false,
  external_llm_base_url: "",
  external_llm_model: "",
  allow_llm_fallback: false,
  llm_timeout_seconds: 600,
  llm_json_mode: "auto",
  ollama_endpoint: "auto"
};

const nodeTypes: Array<NodeType | "all"> = ["all", "effect", "object", "action", "condition", "task", "theme"];

export default function AdminPage({ refreshKey, onChanged }: Props) {
  const [settings, setSettings] = useState<LLMSettings>(emptySettings);
  const [nodes, setNodes] = useState<KnowledgeNode[]>([]);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<NodeType | "all">("all");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState<LLMTestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [resetText, setResetText] = useState("");
  const [deleteUploads, setDeleteUploads] = useState(true);
  const [deleteExports, setDeleteExports] = useState(true);

  useEffect(() => {
    Promise.all([api.llmSettings(), api.graph("all", undefined, "all")])
      .then(([nextSettings, graph]) => {
        setSettings(nextSettings);
        setNodes(graph.nodes);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Chargement admin impossible"));
  }, [refreshKey]);

  const filteredNodes = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return nodes.filter((node) => {
      const matchesType = typeFilter === "all" || node.type === typeFilter;
      const matchesQuery = !needle || node.label.toLowerCase().includes(needle);
      return matchesType && matchesQuery;
    });
  }, [nodes, query, typeFilter]);

  async function saveSettings() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const saved = await api.saveLlmSettings(settings);
      setSettings(saved);
      setMessage("Configuration LLM enregistrée.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enregistrement impossible");
    } finally {
      setBusy(false);
    }
  }

  async function testSettings() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const saved = await api.saveLlmSettings(settings);
      setSettings(saved);
      const result = await api.testLlmSettings();
      setTestResult(result);
      setMessage("Configuration enregistrée avant le test.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test impossible");
    } finally {
      setBusy(false);
    }
  }

  async function deleteNode(node: KnowledgeNode) {
    const ok = window.confirm(`Supprimer le concept "${node.label}" et ses liens associés ?`);
    if (!ok) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api.deleteNode(node.id);
      setNodes((current) => current.filter((item) => item.id !== node.id));
      setMessage(
        `Concept supprimé. ${result.deleted_edge_ids.length} lien(s) associé(s) retiré(s).`
      );
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Suppression impossible");
    } finally {
      setBusy(false);
    }
  }

  async function resetDatabase() {
    const ok = window.confirm(
      "Cette action supprime les documents, cartes, concepts, liens, jobs et historique. Continuer ?"
    );
    if (!ok) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api.resetDatabase({
        confirmation: resetText,
        delete_uploads: deleteUploads,
        delete_exports: deleteExports
      });
      setNodes([]);
      setMessage(`${result.message} Uploads supprimés : ${result.deleted_uploads}. Exports supprimés : ${result.deleted_exports}.`);
      setResetText("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Réinitialisation impossible");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-stack admin-page">
      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}

      <section className="panel">
        <div className="section-title">
          <h2>Configuration LLM</h2>
          <span>{!settings.llm_enabled ? "analyse locale simple" : settings.llm_provider === "ollama" ? "local" : "API"}</span>
        </div>

        <div className="admin-grid">
          <label className="toggle-row full-row">
            <input
              type="checkbox"
              checked={settings.llm_enabled}
              onChange={(event) => setSettings({ ...settings, llm_enabled: event.target.checked })}
            />
            Utiliser un LLM pour préremplir l’analyse
          </label>
          <label>
            Fournisseur
            <select
              value={settings.llm_provider}
              onChange={(event) =>
                setSettings({ ...settings, llm_provider: event.target.value as LLMSettings["llm_provider"] })
              }
            >
              <option value="ollama">Ollama local</option>
              <option value="api">API externe compatible OpenAI</option>
            </select>
          </label>

          <label className="toggle-row">
            <input
              type="checkbox"
              checked={settings.allow_llm_fallback}
              disabled={!settings.llm_enabled}
              onChange={(event) => setSettings({ ...settings, allow_llm_fallback: event.target.checked })}
            />
            Analyse heuristique si le LLM échoue
          </label>
        </div>

        {!settings.llm_enabled && (
          <p className="quiet-note">
            Aucun service externe n’est appelé. ECUME extrait localement des propositions simples que l’utilisateur doit vérifier.
          </p>
        )}

        {settings.llm_provider === "ollama" ? (
          <div className="admin-grid">
            <label>
              URL Ollama
              <input
                value={settings.ollama_base_url}
                onChange={(event) => setSettings({ ...settings, ollama_base_url: event.target.value })}
              />
            </label>
            <label>
              Modèle Ollama
              <input
                list="llm-models"
                value={settings.ollama_model}
                onChange={(event) => setSettings({ ...settings, ollama_model: event.target.value })}
              />
            </label>
          </div>
        ) : (
          <div className="admin-grid">
            <label>
              URL API
              <input
                placeholder="https://api.exemple.com/v1"
                value={settings.external_llm_base_url}
                onChange={(event) => setSettings({ ...settings, external_llm_base_url: event.target.value })}
              />
            </label>
            <label>
              Modèle API
              <input
                list="llm-models"
                placeholder="nom-du-modele"
                value={settings.external_llm_model}
                onChange={(event) => setSettings({ ...settings, external_llm_model: event.target.value })}
              />
            </label>
            <label className="full-row">
              Clé API
              <input
                type="password"
                autoComplete="new-password"
                placeholder={settings.has_external_llm_api_key ? "Clé enregistrée, saisir pour la remplacer" : "Non renseignée"}
                value={settings.external_llm_api_key}
                onChange={(event) => setSettings({ ...settings, external_llm_api_key: event.target.value, clear_external_llm_api_key: false })}
              />
            </label>
            {settings.has_external_llm_api_key && (
              <label className="toggle-row full-row">
                <input
                  type="checkbox"
                  checked={Boolean(settings.clear_external_llm_api_key)}
                  onChange={(event) => setSettings({ ...settings, clear_external_llm_api_key: event.target.checked })}
                />
                Effacer la clé API enregistrée
              </label>
            )}
          </div>
        )}

        <datalist id="llm-models">
          {(testResult?.available_models ?? []).map((model) => <option key={model} value={model} />)}
        </datalist>

        <details className="advanced-settings">
          <summary>Réglages avancés</summary>
          <div className="admin-grid">
            <label>
              Timeout de génération (secondes)
              <input
                type="number"
                min={30}
                max={3600}
                value={settings.llm_timeout_seconds}
                onChange={(event) => setSettings({ ...settings, llm_timeout_seconds: Number(event.target.value) })}
              />
            </label>
            <label>
              Récupération JSON
              <select
                value={settings.llm_json_mode}
                onChange={(event) => setSettings({ ...settings, llm_json_mode: event.target.value as LLMSettings["llm_json_mode"] })}
              >
                <option value="auto">Automatique (recommandé)</option>
                <option value="native">JSON natif uniquement</option>
                <option value="prompt">Instruction dans le prompt</option>
              </select>
            </label>
            {settings.llm_provider === "ollama" && (
              <label>
                API Ollama
                <select
                  value={settings.ollama_endpoint}
                  onChange={(event) => setSettings({ ...settings, ollama_endpoint: event.target.value as LLMSettings["ollama_endpoint"] })}
                >
                  <option value="auto">Automatique (recommandé)</option>
                  <option value="generate">Génération</option>
                  <option value="chat">Conversation</option>
                </select>
              </label>
            )}
          </div>
          <p className="quiet-note">
            Le mode automatique essaie le JSON natif, puis utilise une instruction simple si le modèle ne le supporte pas.
          </p>
        </details>

        <div className="button-row">
          <button onClick={saveSettings} disabled={busy}><Save size={16} />Enregistrer</button>
          <button className="ghost-button" onClick={testSettings} disabled={busy}><PlugZap size={16} />Tester le LLM</button>
        </div>
        {testResult && (
          <p className={testResult.ok ? "success inline-result" : "warning inline-result"}>
            {testResult.message}
          </p>
        )}
      </section>

      <RdfEcosystemSettings refreshKey={refreshKey} />

      <section className="panel danger-panel">
        <div className="section-title">
          <h2>RAZ complète de la base</h2>
          <span>action destructive</span>
        </div>
        <p className="description">
          Supprime toute la base locale ECUME : documents, cartes, concepts, liens, jobs et historique.
        </p>
        <div className="admin-grid">
          <label className="full-row">
            Confirmation
            <input
              placeholder="Saisir RESET ECUME"
              value={resetText}
              onChange={(event) => setResetText(event.target.value)}
            />
          </label>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={deleteUploads}
              onChange={(event) => setDeleteUploads(event.target.checked)}
            />
            Supprimer aussi les fichiers importés
          </label>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={deleteExports}
              onChange={(event) => setDeleteExports(event.target.checked)}
            />
            Supprimer aussi les exports
          </label>
        </div>
        <button
          className="danger-button"
          onClick={resetDatabase}
          disabled={busy || resetText !== "RESET ECUME"}
        >
          <DatabaseZap size={16} />
          Lancer la RAZ complète
        </button>
      </section>

      <section className="panel">
        <div className="section-title">
          <h2>Concepts en base</h2>
          <span>{filteredNodes.length} / {nodes.length}</span>
        </div>
        <div className="admin-filters">
          <label>
            <Search size={16} />
            <input
              placeholder="Rechercher un concept"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value as NodeType | "all")}>
            {nodeTypes.map((type) => <option key={type} value={type}>{type === "all" ? "Tous les types" : type}</option>)}
          </select>
        </div>

        <div className="concept-table">
          {filteredNodes.length === 0 ? <p>Aucun concept.</p> : filteredNodes.map((node) => (
            <article key={node.id}>
              <div>
                <b>{node.label}</b>
                <span>{node.type} · {node.level} · {node.status}</span>
              </div>
              <button className="danger-button" onClick={() => deleteNode(node)} disabled={busy} title="Supprimer">
                <Trash2 size={16} />
                Supprimer
              </button>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}
