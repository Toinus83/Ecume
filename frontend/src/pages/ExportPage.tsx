import { useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { api } from "../api/client";
import type { ReferenceRepository, EchoReport, RDFSettings } from "../types";
import { ActionError } from "../components/ContextHelp";

export default function ExportPage() {
  const [references,setReferences]=useState<ReferenceRepository[]>([]);
  const [target,setTarget]=useState("");
  const [report,setReport]=useState<EchoReport|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [rdf,setRdf]=useState<RDFSettings|null>(null);
  useEffect(()=>{api.references().then(setReferences).catch(e=>setError(String(e)));},[]);
  useEffect(()=>{api.rdfSettings().then(setRdf).catch(()=>setRdf(null));},[]);
  async function check(){setBusy(true);setError("");setReport(null);try{setReport(await api.echoReport(target));}catch(e){setError(String(e));}finally{setBusy(false);}}
  return <section className="page-stack export-page">
    <p className="page-intro">Choisissez le fichier selon son destinataire. Les formats techniques restent soumis à contrôle humain.</p>

    <section className="export-family"><div><span className="section-kicker">Export maître ECUME</span><h2>JSON maître ECUME</h2>
      <p>Contient toute la connaissance validée : documents, concepts, relations, sources, décisions utilisateur et mappings candidats.</p>
      <code>ecume_knowledge.json</code></div>
      <a className="button-link" href={api.exportUrl("json")}><Download size={16}/>Télécharger le JSON maître</a>
      <details><summary>Archive complète et JSON-LD</summary><div className="button-row">
        <a className="button-link secondary-link" href={api.exportUrl("json")+"?scope=all"}><Download size={16}/>Archive JSON complète</a>
        <a className="button-link secondary-link" href={api.exportUrl("jsonld")}><Download size={16}/>JSON-LD</a>
      </div></details>
    </section>

    <section className="export-family"><div><span className="section-kicker">Graphe lié</span><h2>Turtle RDF générique ECUME</h2>
      <p>Export RDF du graphe ECUME. Utile pour charger les connaissances dans un outil RDF. Ce fichier n’est pas un lot Echo conforme.</p>
      <code>ecume_export.ttl</code></div>
      <a className="button-link" href={api.exportUrl("ttl")}><Download size={16}/>Télécharger le Turtle générique</a>
      <p className="quiet-note">Ce fichier peut être chargé dans un outil RDF ou inspecté dans un outil de revue tel qu’Ontosphere.</p>
    </section>

    <section className="export-family"><div><span className="section-kicker">Revue experte</span><h2>Lot de revue OWL / VOC / SHACL</h2>
      <p>Brouillon technique pour revue par un expert ontologie. Les fichiers ne doivent pas être réimportés automatiquement dans l’ontologie de référence.</p>
      <p className="review-warning"><strong>Proposition à revoir, pas une ontologie approuvée.</strong><br/>Revue humaine avant tout réimport. Aucun fichier référentiel source modifié.</p></div>
      <a className="button-link" href={api.exportUrl("ontology-draft")}><Download size={16}/>Télécharger le lot de revue</a>
      <details><summary>Contenu du lot</summary><ul className="file-list"><li><code>ecume_draft.owl.ttl</code></li><li><code>ecume_draft.voc.ttl</code></li><li><code>ecume_draft.shacl.ttl</code></li><li><code>ecume_knowledge.json</code></li><li><code>README.txt</code></li><li><code>manifest.json</code></li><li><code>proposals.csv</code></li><li><code>control_report.html</code></li></ul></details>
      {rdf?.fuseki_enabled&&<details><summary>Graphes Fuseki préparés pour la revue</summary><dl className="export-graphs"><div><dt>Candidats</dt><dd><code>{rdf.graph_ecume_candidates}</code></dd></div><div><dt>Validés métier</dt><dd><code>{rdf.graph_ecume_validated}</code></dd></div><div><dt>Rejets</dt><dd><code>{rdf.graph_ecume_rejected}</code></dd></div><div><dt>Provenance</dt><dd><code>{rdf.graph_ecume_provenance}</code></dd></div><div><dt>Revue ontologue</dt><dd><code>{rdf.graph_ecume_review}</code></dd></div></dl><p className="quiet-note">Affichage informatif : cette version n’envoie encore aucun SPARQL Update.</p></details>}
    </section>

    <section className="export-family future-export"><div><span className="section-kicker">À venir</span><h2>Lot Echo conforme OWL / VOC / SHACL</h2>
      <p>Produira un lot aligné sur les gabarits Echo fournis. Il nécessitera confirmation du domaine, profil de référentiel et revue humaine.</p>
      <p className="echo-unavailable"><strong>Non disponible dans cette version.</strong> Les TTL du lot de revue ci-dessus ne constituent pas ce lot Echo.</p></div>
      <details><summary>Fichiers attendus</summary><ul className="file-list"><li><code>echo_[domaine]_enrichment.owl.ttl</code></li><li><code>echo_[domaine]_enrichment.voc.ttl</code></li><li><code>echo_[domaine]_enrichment.shacl.ttl</code></li><li><code>manifest.json</code></li><li><code>proposals.csv</code></li><li><code>control_report.html</code></li></ul></details>
      <details><summary>Outils Echo expérimentaux actuels</summary>
        <label>Référentiel cible<select aria-label="Référentiel cible" value={target} disabled={busy} onChange={e=>{setTarget(e.target.value);setReport(null);}}><option value="">Choisir un référentiel</option>{references.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
        <ActionError error={error}/><div className="button-row"><button disabled={!target||busy} onClick={()=>void check()}><RefreshCw size={16}/>{busy?"Contrôle en cours…":"Préparer le bilan expérimental"}</button></div>
        {report&&<><p>{report.recognized_existing} éléments reconnus · {report.new_concepts} nouveautés proposées · {report.new_business_rules} règles métier</p>
          <p className="quiet-note">Ce bilan ne produit pas les trois fichiers TTL conformes aux gabarits Echo.</p>
          <div className="button-row"><a className="button-link secondary-link" href={api.echoExportUrl(target,"json")}><Download size={16}/>JSON Echo expérimental</a><a className="button-link secondary-link" href={api.echoExportUrl(target,"csv")}><Download size={16}/>ZIP CSV expérimental</a></div></>}
      </details>
    </section>

    <details><summary>Autres formats</summary><div className="export-grid">
      <a className="export-button" href={api.exportUrl("csv")}><Download size={18}/>Export CSV graphe</a>
      <a className="export-button" href={api.exportUrl("memgraph")}><Download size={18}/>Export Memgraph</a>
      <a className="export-button" href={api.exportUrl("archimate-json")}><Download size={18}/>Export ArchiMate candidat</a>
    </div><p className="quiet-note">Les correspondances ArchiMate restent candidates jusqu’à leur contrôle par un architecte.</p></details>
  </section>;
}
