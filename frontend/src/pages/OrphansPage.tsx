import { useEffect, useState } from "react";
import { BookOpen, Link2, Pencil, Save } from "lucide-react";
import { api } from "../api/client";
import { LevelPill, StatusPill } from "../components/StatusPill";
import { businessCategories, levels } from "../components/EffectCard";
import ConceptSearch from "../components/ConceptSearch";
import { ActionError, ContextHelp } from "../components/ContextHelp";
import type { KnowledgeNode } from "../types";

interface Props { refreshKey: number; onOpenCard: (cardId: string) => void }
const relations = ["contribue à", "se décompose en", "concerne", "nécessite", "déclenche", "proche de", "équivalent à"];

export default function OrphansPage({ refreshKey, onOpenCard }: Props) {
  const [orphans, setOrphans] = useState<KnowledgeNode[]>([]);
  const [targetNode, setTargetNode] = useState<KnowledgeNode | null>(null);
  const [visibleCount, setVisibleCount] = useState(20);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState("pending");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [localRefresh, setLocalRefresh] = useState(0);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ label: "", business_category: "", level: "", target_node_id: "", relation_type: "contribue à" });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let cancelled = false;
    api.orphans().then(items => {
      if (!cancelled) setOrphans(items);
    }).catch(err => { if (!cancelled) setError(String(err)); });
    return () => { cancelled = true; };
  }, [refreshKey, localRefresh]);

  const filtered = orphans.filter(node => (scope === "all" || (scope === "secondary" ? node.importance === "secondary" : scope === "accepted" ? node.orphan_status === "accepted_orphan" : node.orphan_status !== "accepted_orphan" && (node.importance !== "secondary" || ["accepted", "accepted_orphan"].includes(node.status)))) &&
    [node.label, node.description, ...(node.source_titles ?? [])].join(" ").toLocaleLowerCase("fr").includes(query.toLocaleLowerCase("fr")));
  useEffect(() => setVisibleCount(20), [query, scope]);
  async function act(nodeId: string, payload: Parameters<typeof api.updateOrphan>[1], message: string) {
    setBusy(true); setError(""); setNotice("");
    try { await api.updateOrphan(nodeId, payload); setEditing(null); setNotice(message); setLocalRefresh(value => value + 1); }
    catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  }
  return <section className="page-stack">
    <div className="section-title"><h2>Orphelins</h2><span>{filtered.length} / {orphans.length}</span></div>
    <ContextHelp><p>Un concept sans lien peut être pertinent. Rattachez-le à un autre concept, acceptez-le sans rattachement ou mettez-le à revoir.</p></ContextHelp>
    <div className="segmented">{[["pending", "Prioritaires / à revoir"], ["secondary", "Secondaires retenus"], ["accepted", "Acceptés sans rattachement"], ["all", "Tous"]].map(([value, label]) =>
      <button key={value} aria-pressed={scope === value} className={scope === value ? "active" : ""} onClick={() => setScope(value)}>{label}</button>)}</div>
    <input className="search-input" aria-label="Rechercher dans les orphelins" placeholder="Rechercher un concept ou une source" value={query} onChange={e => setQuery(e.target.value)} />
    <ActionError error={error} />{notice && <p className="success" role="status">{notice}</p>}
    <div className="orphan-worklist">
      {!filtered.length && <p>Aucun orphelin dans cette sélection.</p>}
      {filtered.slice(0, visibleCount).map(node => <article key={node.id}>
        <div className="section-title"><h3>{node.label}</h3><div className="pill-row"><StatusPill value={node.status} /><LevelPill value={node.level} /></div></div>
        <p>{node.description || "Description à préciser."}</p>
        <p className="quiet-note">{businessCategories.find(item => item.value === node.business_category)?.label} · {node.source_titles?.join(", ") || "Source non renseignée"}</p>
        <p className="quiet-note">{node.orphan_kind} · {node.orphan_status === "accepted_orphan" ? "Accepté sans rattachement" : node.orphan_status === "orphan_to_review" ? "À revoir" : "En attente de rattachement"}</p>
        {editing === node.id ? <form className="orphan-edit" onSubmit={e => { e.preventDefault(); void act(node.id,
          {...draft, target_node_id: draft.target_node_id || undefined}, draft.target_node_id ? "Rattachement enregistré. Le graphe et les exports suivent le statut de validation des concepts." : "Correction enregistrée, à valider depuis la carte source."); }}>
          <label>Libellé<input required value={draft.label} onChange={e => setDraft({...draft, label: e.target.value})} /></label>
          <label>Catégorie<select value={draft.business_category} onChange={e => setDraft({...draft, business_category: e.target.value})}>{businessCategories.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label>Niveau<select value={draft.level} onChange={e => setDraft({...draft, level: e.target.value})}>{levels.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label>Relation<select value={draft.relation_type} onChange={e => setDraft({...draft, relation_type: e.target.value})}>{relations.map(item => <option key={item}>{item}</option>)}</select></label>
          <div className="full-row"><ConceptSearch sourceId={node.id} documentId={node.source_ids[0]} value={targetNode} onSelect={target => { setTargetNode(target); setDraft({...draft, target_node_id: target?.id ?? ""}); }} /></div>
          {draft.target_node_id && <p className="full-row">{draft.label} → {draft.relation_type} → {targetNode?.label}</p>}
          {(node.source_card_ids?.length ?? 0) > 1 && <p className="quiet-note full-row">Concept partagé : les corrections de contenu se font depuis une carte source.</p>}
          <div className="button-row full-row"><button disabled={busy}><Save size={16} />Enregistrer</button><button type="button" className="ghost-button" disabled={busy} onClick={() => setEditing(null)}>Annuler</button></div>
        </form> : <div className="button-row">
          <button disabled={busy} onClick={() => { setEditing(node.id); setTargetNode(null); setDraft({ label: node.label, business_category: node.business_category, level: node.level, target_node_id: "", relation_type: node.type === "effect" ? "contribue à" : "concerne" }); }}><Pencil size={16} />Modifier / rattacher</button>
          <button className="ghost-button" disabled={busy || node.orphan_status === "accepted_orphan"} onClick={() => {
            if (window.confirm("Accepter ce concept sans rattachement pour l'instant ? Il sera exportable comme connaissance validée.")) void act(node.id, {orphan_status: "accepted_orphan"}, "Concept accepté sans rattachement, consultable dans le filtre dédié.");
          }}><Link2 size={16} />Laisser orphelin pour l'instant</button>
          <button className="ghost-button" disabled={busy} onClick={() => void act(node.id, {orphan_status: "orphan_to_review"}, "Orphelin mis à revoir, exclu du graphe validé et des exports principaux.")}>À revoir</button>
          {!!node.source_card_ids?.length && <button className="ghost-button" onClick={() => onOpenCard(node.source_card_ids![0])}><BookOpen size={16} />Ouvrir une carte source</button>}
        </div>}
      </article>)}
    </div>
    {filtered.length > visibleCount && <button className="ghost-button load-more" onClick={() => setVisibleCount(visibleCount + 20)}>Voir 20 concepts supplémentaires</button>}
  </section>;
}
