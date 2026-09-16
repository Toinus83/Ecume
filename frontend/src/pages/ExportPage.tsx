import { useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { api } from "../api/client";
import type { ReferenceRepository, EchoReport } from "../types";
import { ActionError } from "../components/ContextHelp";

const exports = [
  ["json", "Exporter JSON"],
  ["jsonld", "Exporter JSON-LD"],
  ["csv", "Exporter CSV"],
  ["memgraph", "Exporter Memgraph"],
  ["rdf-skos", "Exporter RDF/SKOS"],
  ["archimate-json", "Exporter ArchiMate JSON"]
] as const;

export default function ExportPage() {
  const [references,setReferences]=useState<ReferenceRepository[]>([]);
  const [target,setTarget]=useState("");
  const [report,setReport]=useState<EchoReport|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  useEffect(()=>{api.references().then(setReferences).catch(e=>setError(String(e)));},[]);
  async function check(){setBusy(true);setError("");setReport(null);try{setReport(await api.echoReport(target));}catch(e){setError(String(e));}finally{setBusy(false);}}
  return (
    <section className="page-stack">
      <h2>Graphe validé</h2>
      <div className="export-grid">
        {exports.map(([kind, label]) => (
          <a className="export-button" href={api.exportUrl(kind)} key={kind}>
            <Download size={18} />
            <span>{label}</span>
          </a>
        ))}
      </div>
      <h2>Archive ECUME</h2>
      <a className="button-link" href={api.exportUrl("json")+"?scope=all"}><Download size={16}/>Archive JSON complète</a>
      <h2>Lot d’enrichissement Echo</h2>
      <label>Référentiel cible<select aria-label="Référentiel cible" value={target} disabled={busy} onChange={e=>{setTarget(e.target.value);setReport(null);}}><option value="">Choisir un référentiel</option>{references.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
      <ActionError error={error}/>
      <div className="button-row"><button disabled={!target||busy} onClick={()=>void check()}><RefreshCw size={16}/>{busy?"Contrôle en cours…":"Préparer le bilan"}</button></div>
      {report&&<>
        <p>{report.recognized_existing} éléments reconnus · {report.new_concepts} nouveautés proposées · {report.new_business_rules} règles métier</p>
        <p className="quiet-note">Lot destiné à une revue humaine. Le réimport n’est pas garanti.</p>
        <ul>{Object.entries(report.shacl_counts).map(([status,count])=><li key={status}>{{conformant:"Conformes au contrôle",to_complete:"À compléter",nonconformant:"Non conformes",not_verifiable:"Non vérifiables"}[status]||status} : {count}</li>)}</ul>
        {report.warnings.length>0&&<details><summary>{report.warnings.length} avertissements</summary><ul>{report.warnings.map((w,i)=><li key={i}>{w.message}</li>)}</ul></details>}
        <div className="button-row"><a className="button-link" href={api.echoExportUrl(target,"json")}><Download size={16}/>JSON Echo complet</a><a className="button-link" href={api.echoExportUrl(target,"csv")}><Download size={16}/>ZIP de contrôle</a></div>
      </>}
    </section>
  );
}
