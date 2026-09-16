import { useEffect, useState } from "react";
import { Pencil, Save, X } from "lucide-react";
import type { ExtractedCard, BusinessRule, EchoCardReport } from "../types";
import { api } from "../api/client";
import { ActionError } from "./ContextHelp";

export default function EchoCard({card,onChange}:{card:ExtractedCard;onChange:()=>void}) {
  const [reports,setReports]=useState<EchoCardReport[]>([]);
  const [draft,setDraft]=useState<BusinessRule|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const validated=["accepted","accepted_orphan"].includes(card.status);
  useEffect(()=>{let cancelled=false;setReports([]);setError("");if(validated)api.echoCard(card.id).then(r=>{if(!cancelled)setReports(r);}).catch(e=>{if(!cancelled)setError(String(e));});return()=>{cancelled=true;};},[card.id,card.updated_at,validated]);
  async function save(){if(!draft)return;setBusy(true);setError("");try{await api.correctRule(card.id,draft);setDraft(null);onChange();}catch(e){setError(String(e));}finally{setBusy(false);}}
  const rules=card.extraction_details?.business_rules||[];
  const recognized=new Set(reports.flatMap(r=>r.recognized.map(m=>m.node_id))).size;
  const proposals=reports.flatMap(r=>r.new_concepts).filter((n,i,all)=>all.findIndex(other=>other.id===n.id)===i);
  if(!rules.length&&!reports.length&&!error)return null;
  return <section className="echo-card">
    <ActionError error={error}/>
    {rules.length>0&&<details open={rules.length===1}><summary>Règle détectée ({rules.length})</summary>{rules.map(rule=><div className="echo-rule" key={rule.id}>
      <strong>{rule.label}</strong><p>{rule.value} {rule.unit}</p><p>{rule.description}</p>
      {rule.condition&&<p>Condition : {rule.condition}</p>}{rule.exception&&<p>Exception : {rule.exception}</p>}
      <details><summary>Source</summary><p>{rule.source_excerpt||card.source_excerpt}</p></details>
      <button className="ghost-button" title="Corriger la règle et remettre la carte à revoir" onClick={()=>setDraft({...rule})}><Pencil size={14}/>Corriger</button>
    </div>)}</details>}
    {draft&&<div className="rule-editor">
      {(["label","description","value","unit","condition","exception"] as const).map(key=><label key={key}>{{label:"Intitulé",description:"Description",value:"Valeur",unit:"Unité",condition:"Condition",exception:"Exception"}[key]}<input value={draft[key]} onChange={e=>setDraft({...draft,[key]:e.target.value})}/></label>)}
      <div className="button-row"><button disabled={busy} onClick={()=>void save()}><Save size={15}/>Enregistrer et revoir</button><button className="ghost-button" disabled={busy} onClick={()=>setDraft(null)}><X size={15}/>Annuler</button></div>
    </div>}
    {recognized>0&&<p className="quiet-note">{recognized} éléments déjà reconnus dans Echo</p>}
    {proposals.length>0&&<details><summary>Nouveautés proposées pour Echo ({proposals.length})</summary><ul>{proposals.map(n=><li key={n.id}>{n.label}{n.classification==="to_review"?" · correspondances à vérifier":" · nouveau terme proposé"}</li>)}</ul></details>}
    {!!reports.length&&<details><summary>Contrôles et détails Echo</summary>{reports.map(r=><div key={r.repository_id}><h4>{r.name}</h4><ul>{r.checks.slice(0,12).map((c,i)=><li key={i}>{{conformant:"Conforme au contrôle",to_complete:"À compléter",nonconformant:"Non conforme",not_verifiable:"Non vérifiable"}[c.status]||c.status} : {c.message}</li>)}</ul>{r.checks.length>12&&<p>Suite des contrôles dans le lot exporté.</p>}</div>)}</details>}
  </section>;
}
