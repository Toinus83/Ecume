import { useEffect, useState } from "react";
import { Search, ChevronLeft, ChevronRight, Check } from "lucide-react";
import { api } from "../api/client";
import type { KnowledgeNode } from "../types";
import { StatusPill } from "./StatusPill";
import { ActionError } from "./ContextHelp";

interface Props {
  sourceId?: string; documentId?: string; nodeType?: string; initialScope?: string;
  value: KnowledgeNode | null; onSelect: (node: KnowledgeNode | null) => void;
}
export default function ConceptSearch({ sourceId = "", documentId = "", nodeType = "", initialScope = "all", value, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState(initialScope);
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<(KnowledgeNode & { already_linked: boolean })[]>([]);
  const [total, setTotal] = useState(0);
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    setItems([]); setTotal(0); setMore(false); setError("");
    if (query.trim().length < 2) { setBusy(false); return; }
    setBusy(true);
    const timer = window.setTimeout(async () => {
      try {
        const result = await api.searchTargets(query, sourceId, documentId, scope, offset, nodeType);
        if (!cancelled) { setItems(result.items); setTotal(result.total); setMore(result.has_more); }
      } catch (err) { if (!cancelled) setError(String(err)); }
      finally { if (!cancelled) setBusy(false); }
    }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [query, sourceId, documentId, scope, offset, nodeType]);
  if (value) return <div className="target-selected"><span><Check size={15} />{value.label}</span><button type="button" className="ghost-button" onClick={() => onSelect(null)}>Changer de cible</button></div>;
  return <div className="concept-search">
    <label className="search-field"><Search size={16} /><input aria-label="Rechercher un concept cible" placeholder="Rechercher un concept cible" maxLength={200} value={query} onChange={e => { setQuery(e.target.value); setOffset(0); }} /></label>
    <details><summary>Filtrer les résultats</summary><select aria-label="Filtrer les concepts" value={scope} onChange={e => { setScope(e.target.value); setOffset(0); }}>
      <option value="all">Tous</option><option value="validated">Concepts validés seulement</option><option value="document" disabled={!documentId}>Même document</option><option value="close">Libellés proches</option>
    </select></details>
    <ActionError error={error} />
    <p className="quiet-note" role="status">{busy ? "Recherche…" : query.trim().length < 2 ? "Saisissez au moins deux lettres." : total ? total + " résultats" : error ? "Recherche indisponible." : "Aucun concept trouvé. Essayez un autre libellé ou laissez le lien à revoir."}</p>
    <ul className="target-results">{items.map(node => <li key={node.id}><button type="button" onClick={() => onSelect(node)}>
      <span className="result-title"><strong>{node.label}</strong>{node.business_validation_status === "auto_validated" ? <span className="pill">Auto-validé</span> : <StatusPill value={node.status} />}</span>
      {node.importance && node.importance !== "unclassified" && <span className="quiet-note">{node.importance === "principal" ? "Principal dans une carte" : "Secondaire retenu"}</span>}
      <span className="quiet-note">{node.business_category.replace(/_/g, " ")}{node.already_linked ? " · Déjà lié" : ""}</span>
      <span className="result-description">{node.description || "Description non renseignée."}</span>
      <span className="quiet-note">{node.source_titles?.join(", ") || "Source non renseignée"}</span>
    </button></li>)}</ul>
    {(offset > 0 || more) && <div className="button-row"><button type="button" className="ghost-button" disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - 8))}><ChevronLeft size={16} />Précédents</button><button type="button" className="ghost-button" disabled={busy || !more} onClick={() => setOffset(offset + 8)}>Voir plus<ChevronRight size={16} /></button></div>}
  </div>;
}
