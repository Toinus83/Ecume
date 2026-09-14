import { useEffect, useState } from "react";
import { Search, Check, X, Clock3 } from "lucide-react";
import { api } from "../api/client";
import type { EchoMapping } from "../types";
import { ActionError } from "./ContextHelp";

const kinds = [["exactMatch","Même sens"],["closeMatch","Proche"],["broadMatch","Référence plus générale"],["narrowMatch","Référence plus précise"],["relatedMatch","Lié"]];
const statuses = {candidate:"À confirmer",validated:"Correspondance validée",to_review:"À revoir",rejected:"Pas le bon concept"};

export default function EchoMappings({ nodes = [], repositoryId = "" }: {nodes?: {id:string;label:string}[]; repositoryId?:string}) {
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState(nodes[0]?.id ?? "");
  const [choosing, setChoosing] = useState(false);
  const [sourceQuery, setSourceQuery] = useState("");
  const [sourceOffset, setSourceOffset] = useState(0);
  const [items, setItems] = useState<EchoMapping[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("pending");
  const [limit, setLimit] = useState(8);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [draft, setDraft] = useState<Record<string,string>>({});
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setItems([]); setDraft({}); setError("");
    api.echoMappings(source,repositoryId).then(next => { if (!cancelled) { setItems(next); setDraft({}); } })
      .catch(err => { if (!cancelled) setError(String(err)); });
    return () => { cancelled = true; };
  }, [source,repositoryId,open,refresh]);
  async function decide(item: EchoMapping, status: string) {
    setBusy(true); setError("");
    try { await api.decideEchoMapping(item.id,draft[item.id] ?? item.match_type,status); setRefresh(value=>value+1); }
    catch (err) { setError(String(err)); } finally { setBusy(false); }
  }
  const sources = nodes.filter(node=>node.label.toLocaleLowerCase("fr").includes(sourceQuery.toLocaleLowerCase("fr")));
  const filtered = items.filter(item => (filter === "all" || filter === "pending" && (item.stale || ["candidate","to_review"].includes(item.status)) || filter === item.status)
    && (item.node_label+" "+item.target_label+" "+item.repository_name).toLocaleLowerCase("fr").includes(query.toLocaleLowerCase("fr")));
  return <details className="echo-mappings card-disclosure" onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary>Correspondances possibles dans les référentiels Echo</summary>
    {open && <div className="echo-workspace">
      {nodes.length>0 && <div><strong>{nodes.find(node=>node.id===source)?.label}</strong>{nodes.length>1 && <button className="ghost-button" onClick={()=>setChoosing(!choosing)}>Changer de concept</button>}</div>}
      {choosing && <div><input aria-label="Chercher un concept de cette carte" value={sourceQuery} onChange={event=>{setSourceQuery(event.target.value);setSourceOffset(0);}} placeholder="Chercher dans cette carte" />
        <ul className="echo-source-list">{sources.slice(sourceOffset,sourceOffset+8).map(node=><li key={node.id}><button className="ghost-button" onClick={()=>{setSource(node.id);setChoosing(false);setLimit(8);}}>{node.label}</button></li>)}</ul>
        <div className="button-row">{sourceOffset>0 && <button className="ghost-button" onClick={()=>setSourceOffset(Math.max(0,sourceOffset-8))}>Précédents</button>}{sources.length>sourceOffset+8 && <button className="ghost-button" onClick={()=>setSourceOffset(sourceOffset+8)}>Voir les suivants</button>}</div>
      </div>}
      <p className="quiet-note">Aucune correspondance n’est obligatoire. Le sens métier et le rôle architectural restent des décisions séparées.</p>
      <button className="ghost-button" disabled={busy} onClick={async()=>{
        setBusy(true);setError("");setNotice("");
        try { const result=await api.searchEchoMappings(source,repositoryId); setRefresh(value=>value+1);
          setNotice(result.created+" nouveaux candidats · "+result.human_decisions_preserved+" décisions humaines conservées · "+result.without_candidate+" concepts sans candidat.");
        } catch(err) {setError(String(err));} finally {setBusy(false);}
      }}><Search size={16} />{busy?"Recherche…":"Chercher des correspondances"}</button>
      <ActionError error={error} />{notice && <p role="status" className="success">{notice}</p>}
      <div className="echo-filters"><input aria-label="Filtrer les correspondances Echo" placeholder="Rechercher une correspondance" value={query} onChange={event=>{setQuery(event.target.value);setLimit(8);}} />
        <select aria-label="Statut des correspondances Echo" value={filter} onChange={event=>{setFilter(event.target.value);setLimit(8);}}><option value="pending">À examiner</option><option value="validated">Validées</option><option value="rejected">Rejetées</option><option value="all">Toutes</option></select></div>
      {!filtered.length && <p className="quiet-note">Aucune correspondance dans cette sélection. Le concept garde sa valeur métier.</p>}
      <ul className="echo-mapping-list">{filtered.slice(0,limit).map(item=><li key={item.id}>
        {!nodes.length && <p className="quiet-note">Concept ECUME : {item.node_label}</p>}
        <strong>{item.target_label}</strong><span className="quiet-note"> · {item.repository_name} · {statuses[item.status]}{!item.repository_active?" · Référentiel inactif":""}</span>
        <p>{item.target_definition || "Définition non renseignée."}</p>
        <p className="quiet-note">{Math.round(item.score*100)} % · {item.reason}</p>
        {item.stale && <p className="error">Le concept a changé depuis cette proposition ou décision. Vérifiez à nouveau la correspondance.</p>}
        <div className="echo-decisions"><select aria-label={"Sens de la correspondance avec "+item.target_label} value={draft[item.id] ?? item.match_type} onChange={event=>setDraft({...draft,[item.id]:event.target.value})}>{kinds.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select>
          <button disabled={busy || !item.repository_active} onClick={()=>void decide(item,"validated")}><Check size={15} />Valider la correspondance</button>
          <button className="ghost-button" disabled={busy || !item.repository_active} onClick={()=>void decide(item,"to_review")}><Clock3 size={15} />À revoir</button>
          <button className="ghost-button" disabled={busy || !item.repository_active} onClick={()=>void decide(item,"rejected")}><X size={15} />Rejeter</button></div>
        <details><summary>Détails techniques</summary><p>{item.target_uri}</p><p>ECUME → Echo : {draft[item.id] ?? item.match_type}</p></details>
      </li>)}</ul>
      {filtered.length>limit && <button className="ghost-button" onClick={()=>setLimit(limit+8)}>Voir les suivants</button>}
    </div>}
  </details>;
}
