import { Check, Pencil } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import type { SourceDocument } from "../types";

export default function DocumentDomain({document,onChanged}:{document:SourceDocument;onChanged:(document:SourceDocument)=>void}) {
  const [editing,setEditing]=useState(false);
  const [domain,setDomain]=useState(document.confirmed_domain||document.proposed_domain||"");
  const [secondary,setSecondary]=useState(document.secondary_domains.join(", "));
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  const confirmed=document.domain_status==="confirmed"||document.domain_status==="no_reference";
  const domainConfidence=document.domain_evidence.find(item=>item.domain===document.proposed_domain)?.score;
  async function save(noReference=false){
    setBusy(true);setError("");
    try{
      const updated=await api.confirmDomain(document.id,{confirmed_domain:domain,
        secondary_domains:secondary.split(",").map(value=>value.trim()).filter(Boolean),no_suitable_reference:noReference});
      onChanged(updated);setEditing(false);
    }catch(err){setError(err instanceof Error?err.message:String(err));}finally{setBusy(false);}
  }
  return <section className={`domain-decision ${confirmed?"is-confirmed":"needs-confirmation"}`}>
    <div className="section-title"><div><span className="section-kicker">Domaine métier</span><h2>{confirmed?"Domaine confirmé":"Domaine proposé"}</h2></div>
      <span className={`simple-state ${confirmed?"state-validated":"state-review"}`}>{confirmed?"Confirmé":"À confirmer"}</span></div>
    {!editing?<>
      <p className="domain-name">Ce document semble concerner : <strong>{document.confirmed_domain||document.proposed_domain||"Domaine à préciser"}</strong></p>
      {!confirmed&&domainConfidence!==undefined&&<p className="quiet-note">Confiance de la proposition : {Math.round(domainConfidence*100)} %</p>}
      {!!document.secondary_domains.length&&<p className="quiet-note">Domaines secondaires : {document.secondary_domains.join(" · ")}</p>}
      {!confirmed&&<p>Confirmez le domaine pour préparer les exports Echo et les rattachements au bon référentiel.</p>}
      {!!document.domain_evidence.length&&<details><summary>Pourquoi ?</summary><ul>{document.domain_evidence.slice(0,4).map((item,index)=><li key={index}><strong>{item.domain}</strong> · {item.source} : {item.terms.join(", ")}</li>)}</ul></details>}
      <div className="button-row">{!confirmed&&<button disabled={busy||!domain} onClick={()=>void save()}><Check size={16}/>Confirmer ce domaine</button>}
        <button className="ghost-button" disabled={busy} onClick={()=>setEditing(true)}><Pencil size={15}/>{confirmed?"Modifier":"Choisir un autre domaine"}</button>
        {!confirmed&&<button className="ghost-button" disabled={busy} onClick={()=>void save(true)}>Aucun référentiel adapté</button>}</div>
    </>:<div className="domain-form">
      <label>Domaine principal<input value={domain} maxLength={160} onChange={event=>setDomain(event.target.value)} placeholder="Ex. RH, METEO, LOGISTIQUE"/></label>
      <label>Domaines secondaires <small>facultatif, séparés par des virgules</small><input value={secondary} onChange={event=>setSecondary(event.target.value)}/></label>
      <p className="quiet-note">Vous confirmez le domaine métier, pas la validité technique d’une ontologie.</p>
      <div className="button-row"><button disabled={busy||!domain.trim()} onClick={()=>void save()}>Enregistrer</button><button className="ghost-button" disabled={busy} onClick={()=>setEditing(false)}>Annuler</button></div>
    </div>}
    {error&&<p className="error" role="alert">{error}</p>}
  </section>;
}
