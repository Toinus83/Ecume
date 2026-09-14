import { useState } from "react";
import { Save } from "lucide-react";
import { api } from "../api/client";
import type { ExtractedCard, KnowledgeNode, SuggestedLink } from "../types";
import ConceptSearch from "./ConceptSearch";
import { ActionError } from "./ContextHelp";

const relations = ["contribue à", "se décompose en", "concerne", "nécessite", "déclenche", "proche de", "équivalent à"];

export default function SuggestionRepair({ card, link, onDone, onCancel }: {
  card: ExtractedCard; link: SuggestedLink; onDone: () => void; onCancel: () => void;
}) {
  const [source, setSource] = useState(link.source_node_id ?? "");
  const [target, setTarget] = useState<KnowledgeNode | null>(null);
  const [relation, setRelation] = useState(relations.includes(link.relation_type) ? link.relation_type : "proche de");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [label, setLabel] = useState(link.target_label ?? "");
  const [type, setType] = useState("object");
  const [description, setDescription] = useState("");
  const sourceOptions = Object.entries(card.graph_node_ids).flatMap(([role, ids]) => {
    const labels = role === "effect" ? [card.main_effect.label] : role === "theme" ? [card.theme_label] : (card[role as "objects"] ?? []);
    return (Array.isArray(ids) ? ids : [ids]).map((id, i) => ({ id, label: labels[i] || "Concept de la carte" }));
  });
  const sources = [...new Map(sourceOptions.filter(node => node.id).map(node => [node.id, node])).values()]
    .sort((a, b) => a.label.localeCompare(b.label, "fr"));
  return <form className="orphan-edit" onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      if (creating) await api.createSuggestionTarget(card.id, link.id, { source_node_id: source, relation_type: relation, label, type, description });
      else { if (!target) return; await api.repairSuggestion(card.id, link.id, { source_node_id: source, target_node_id: target.id, relation_type: relation }); }
      onDone();
    }
    catch (err) { setError(String(err)); } finally { setBusy(false); }
  }}>
    <label>Concept source<select required value={source} onChange={e => { setSource(e.target.value); setTarget(null); }}><option value="">Choisir dans la carte</option>{sources.map(node => <option key={node.id} value={node.id}>{node.label}</option>)}</select></label>
    <label>Relation<select value={relation} onChange={e => setRelation(e.target.value)}>{relations.map(value => <option key={value}>{value}</option>)}</select></label>
    <div className="full-row"><ConceptSearch sourceId={source} documentId={card.document_id} value={target} onSelect={node => { setTarget(node); setCreating(false); }} /></div>
    {!link.can_accept && <div className="full-row"><label className="checkbox-label"><input type="checkbox" checked={creating} onChange={e => setCreating(e.target.checked)} />Créer comme concept à vérifier</label></div>}
    {creating && <>
      <label>Nom du concept<input required maxLength={240} value={label} onChange={e => setLabel(e.target.value)} /></label>
      <label>Catégorie<select value={type} onChange={e => setType(e.target.value)}><option value="object">Objet métier</option><option value="effect">Effet</option><option value="action">Action</option><option value="condition">Condition</option><option value="task">Tâche</option></select></label>
      <label className="full-row">Description<textarea maxLength={3000} value={description} onChange={e => setDescription(e.target.value)} /></label>
      <p className="quiet-note full-row">Le concept et le lien resteront à vérifier. Aucun ajout au graphe validé à cette étape.</p>
    </>}
    <ActionError error={error} />
    <div className="button-row full-row"><button disabled={busy || !sources.some(node => node.id === source) || (creating ? !label.trim() : !target)}><Save size={16} />{creating ? "Créer et garder à vérifier" : "Corriger le rapprochement"}</button><button type="button" className="ghost-button" disabled={busy} onClick={onCancel}>Annuler</button></div>
  </form>;
}
