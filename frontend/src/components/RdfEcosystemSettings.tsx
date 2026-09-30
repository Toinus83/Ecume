import { Copy, Download, ExternalLink, Network, PlugZap, Save, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { RDFSettings, RDFTestResult } from "../types";

const defaults: RDFSettings = {
  fuseki_enabled: false, fuseki_base_url: "http://localhost:3030", fuseki_dataset: "ecume",
  fuseki_query_endpoint: "/query", fuseki_update_endpoint: "/update", fuseki_write_mode: "disabled",
  graph_echo_owl: "graph:echo:reference:owl", graph_echo_voc: "graph:echo:reference:voc",
  graph_echo_shacl: "graph:echo:reference:shacl", graph_ecume_candidates: "graph:ecume:candidates",
  graph_ecume_validated: "graph:ecume:validated", graph_ecume_rejected: "graph:ecume:rejected",
  graph_ecume_provenance: "graph:ecume:provenance", graph_ecume_review: "graph:ecume:review",
  echo_source: "unconfigured", echo_default_domain: "ECHO_RH", echo_owl_reference: "",
  echo_voc_reference: "", echo_shacl_reference: "", echo_layer_status: { owl: "non chargé", voc: "non chargé", shacl: "non chargé" },
  ontocast_enabled: false, ontocast_mode: "disabled", ontocast_api_url: "", ontocast_api_token: "",
  has_ontocast_api_token: false, ontocast_timeout: 120,
  ontocast_extraction_profile: "default", ontocast_use_fuseki: false, ontocast_local_fallback: true,
  ontosphere_enabled: false, ontosphere_url: "", ontosphere_sparql_url: "",
  ontosphere_review_graph: "graph:ecume:review", rdf_auth_type: "none", rdf_auth_username: "",
  rdf_auth_secret: "", has_rdf_auth_secret: false, rdf_read_only: true,
  rdf_write_candidates_only: true, rdf_write_validated: false
};

function Result({ result }: { result: RDFTestResult | null }) {
  if (!result) return null;
  return <div className={result.ok ? "success inline-result" : "warning inline-result"}>
    {result.message}
    {Array.isArray(result.data) && result.data.length > 0 && <details><summary>Voir le résultat</summary><pre>{JSON.stringify(result.data, null, 2)}</pre></details>}
  </div>;
}

export default function RdfEcosystemSettings({ refreshKey }: { refreshKey: number }) {
  const [settings, setSettings] = useState<RDFSettings>(defaults);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<RDFTestResult | null>(null);

  useEffect(() => {
    api.rdfSettings().then(setSettings).catch((reason) => setError(reason instanceof Error ? reason.message : "Configuration RDF indisponible"));
  }, [refreshKey]);

  async function save() {
    setBusy(true); setError(""); setMessage(""); setResult(null);
    try { setSettings(await api.saveRdfSettings(settings)); setMessage("Configuration RDF enregistrée."); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Enregistrement impossible"); }
    finally { setBusy(false); }
  }

  async function run(operation: () => Promise<RDFTestResult>) {
    setBusy(true); setError(""); setMessage(""); setResult(null);
    try {
      const saved = await api.saveRdfSettings(settings);
      setSettings(saved);
      setMessage("Configuration enregistrée avant le test.");
      setResult(await operation());
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Test impossible"); }
    finally { setBusy(false); }
  }

  async function copy(value: string) {
    await navigator.clipboard.writeText(value);
    setMessage("Valeur copiée.");
  }

  return <section className="panel rdf-admin">
    <div className="section-title"><div><span className="section-kicker">Configuration experte</span><h2>Interopérabilité RDF / Ontologies</h2></div><span>{settings.fuseki_enabled ? "connecté" : "mode local"}</span></div>
    <p className="description">ECUME fonctionne sans service externe. Ces réglages préparent la lecture d’Echo, l’extraction OntoCast et la revue RDF sans exposer cette technique aux utilisateurs métier.</p>
    <p className="doctrine-note">ECUME propose, l’expert métier valide, l’ontologue intègre, Echo reste maîtrisé.</p>
    {error && <p className="error">{error}</p>}{message && <p className="success">{message}</p>}<Result result={result}/>

    <details className="admin-subsection"><summary><Network size={17}/>Fuseki et graphes nommés</summary><div className="admin-subsection-body">
      <label className="toggle-row"><input type="checkbox" checked={settings.fuseki_enabled} onChange={e=>setSettings({...settings,fuseki_enabled:e.target.checked})}/>Activer Fuseki</label>
      <div className="admin-grid"><label>URL Fuseki<input value={settings.fuseki_base_url} onChange={e=>setSettings({...settings,fuseki_base_url:e.target.value})}/></label><label>Dataset<input value={settings.fuseki_dataset} onChange={e=>setSettings({...settings,fuseki_dataset:e.target.value})}/></label><label>Endpoint query<input value={settings.fuseki_query_endpoint} onChange={e=>setSettings({...settings,fuseki_query_endpoint:e.target.value})}/></label><label>Endpoint update<input value={settings.fuseki_update_endpoint} onChange={e=>setSettings({...settings,fuseki_update_endpoint:e.target.value})}/></label><label>Mode d’écriture<select value={settings.fuseki_write_mode} onChange={e=>setSettings({...settings,fuseki_write_mode:e.target.value as RDFSettings["fuseki_write_mode"]})}><option value="disabled">Désactivé</option><option value="candidates">Candidats seulement</option><option value="candidates_validated">Candidats et validés</option></select></label></div>
      <p className="quiet-note">Les graphes Echo restent toujours en lecture seule.</p>
      <div className="named-graphs"><h3>Graphes Echo</h3>{(["graph_echo_owl","graph_echo_voc","graph_echo_shacl"] as const).map(key=><label key={key}>{key.replace("graph_echo_","").toUpperCase()}<input value={settings[key]} onChange={e=>setSettings({...settings,[key]:e.target.value})}/></label>)}<h3>Graphes ECUME</h3>{(["graph_ecume_candidates","graph_ecume_validated","graph_ecume_rejected","graph_ecume_provenance","graph_ecume_review"] as const).map(key=><label key={key}>{key.replace("graph_ecume_","")}<input value={settings[key]} onChange={e=>setSettings({...settings,[key]:e.target.value})}/></label>)}</div>
      <div className="button-row"><button className="ghost-button" disabled={busy} onClick={()=>void run(()=>api.testRdfSettings("connection"))}><PlugZap size={16}/>Tester la connexion</button><button className="ghost-button" disabled={busy} onClick={()=>void run(()=>api.testRdfSettings("query"))}>Tester une requête SPARQL</button><button className="ghost-button" disabled={busy} onClick={()=>void run(()=>api.testRdfSettings("graphs"))}>Lister les graphes</button><button className="ghost-button" disabled={busy} onClick={()=>void run(()=>api.testRdfSettings("read"))}>Tester les droits lecture</button><button className="ghost-button" disabled={busy} onClick={()=>void run(()=>api.testRdfSettings("write"))}>Tester les droits écriture</button></div>
    </div></details>

    <details className="admin-subsection"><summary>Echo, référentiel maîtrisé</summary><div className="admin-subsection-body">
      <div className="admin-grid"><label>Source Echo<select value={settings.echo_source} onChange={e=>setSettings({...settings,echo_source:e.target.value as RDFSettings["echo_source"]})}><option value="unconfigured">Non configuré</option><option value="local">Fichiers locaux</option><option value="fuseki">Fuseki</option><option value="url">URL distante</option></select></label><label>Domaine par défaut<select value={settings.echo_default_domain} onChange={e=>setSettings({...settings,echo_default_domain:e.target.value})}>{["ECHO_RH","ECHO_METEO","ECHO_OPERATIONS","ECHO_LOGISTIQUE","ECHO_C2","autre"].map(value=><option key={value}>{value}</option>)}</select></label><label>Référentiel OWL<input value={settings.echo_owl_reference} onChange={e=>setSettings({...settings,echo_owl_reference:e.target.value})}/><small>{settings.echo_layer_status.owl}</small></label><label>Référentiel VOC<input value={settings.echo_voc_reference} onChange={e=>setSettings({...settings,echo_voc_reference:e.target.value})}/><small>{settings.echo_layer_status.voc}</small></label><label>Référentiel SHACL<input value={settings.echo_shacl_reference} onChange={e=>setSettings({...settings,echo_shacl_reference:e.target.value})}/><small>{settings.echo_layer_status.shacl}</small></label></div>
      <div className="button-row"><button className="ghost-button" disabled={busy} onClick={()=>void run(()=>api.checkEchoProfile("prefixes"))}>Vérifier les préfixes</button><button className="ghost-button" disabled={busy} onClick={()=>void run(()=>api.checkEchoProfile("concept-scheme"))}>Vérifier le ConceptScheme</button><button className="ghost-button" disabled={busy} onClick={()=>void run(()=>api.checkEchoProfile("shapes"))}>Vérifier les shapes SHACL</button><button className="ghost-button" disabled={busy} onClick={()=>void run(()=>api.checkEchoProfile("profile"))}>Vérifier le profil Echo</button></div>
    </div></details>

    <details className="admin-subsection"><summary>OntoCast, extraction RDF</summary><div className="admin-subsection-body">
      <label className="toggle-row"><input type="checkbox" checked={settings.ontocast_enabled} onChange={e=>setSettings({...settings,ontocast_enabled:e.target.checked})}/>Activer OntoCast</label><div className="admin-grid"><label>Mode<select value={settings.ontocast_mode} onChange={e=>setSettings({...settings,ontocast_mode:e.target.value as RDFSettings["ontocast_mode"]})}><option value="disabled">Désactivé</option><option value="simulation">Simulation</option><option value="api">API</option></select></label><label>URL API OntoCast<input value={settings.ontocast_api_url} onChange={e=>setSettings({...settings,ontocast_api_url:e.target.value})}/></label><label>Jeton API OntoCast<input type="password" autoComplete="new-password" placeholder={settings.has_ontocast_api_token ? "Jeton enregistré, saisir pour le remplacer" : "Non renseigné"} value={settings.ontocast_api_token} onChange={e=>setSettings({...settings,ontocast_api_token:e.target.value,clear_ontocast_api_token:false})}/></label><label>Timeout (secondes)<input type="number" min={1} max={3600} value={settings.ontocast_timeout} onChange={e=>setSettings({...settings,ontocast_timeout:Number(e.target.value)})}/></label><label>Profil d’extraction<input value={settings.ontocast_extraction_profile} onChange={e=>setSettings({...settings,ontocast_extraction_profile:e.target.value})}/></label></div>{settings.has_ontocast_api_token&&<label className="toggle-row"><input type="checkbox" checked={Boolean(settings.clear_ontocast_api_token)} onChange={e=>setSettings({...settings,clear_ontocast_api_token:e.target.checked})}/>Effacer le jeton OntoCast enregistré</label>}<label className="toggle-row"><input type="checkbox" checked={settings.ontocast_use_fuseki} onChange={e=>setSettings({...settings,ontocast_use_fuseki:e.target.checked})}/>Utiliser Fuseki comme référentiel</label><label className="toggle-row"><input type="checkbox" checked={settings.ontocast_local_fallback} onChange={e=>setSettings({...settings,ontocast_local_fallback:e.target.checked})}/>Utiliser le moteur local ECUME en fallback</label><div className="button-row"><button className="ghost-button" disabled={busy} onClick={()=>void run(api.testOntocast)}><PlugZap size={16}/>Tester la connexion</button><button className="ghost-button" onClick={()=>setResult({ok:true,message:"Fallback local prêt : ECUME continuera avec son moteur actuel."})}>Tester le fallback local</button></div><p className="quiet-note">L’envoi réel d’un document et l’affichage de la réponse brute seront ajoutés avec l’API OntoCast définitive.</p>
    </div></details>

    <details className="admin-subsection"><summary>Outil de revue RDF</summary><div className="admin-subsection-body">
      <label className="toggle-row"><input type="checkbox" checked={settings.ontosphere_enabled} onChange={e=>setSettings({...settings,ontosphere_enabled:e.target.checked})}/>Activer le lien vers l’outil de revue</label><div className="admin-grid"><label>URL de l’outil<input value={settings.ontosphere_url} onChange={e=>setSettings({...settings,ontosphere_url:e.target.value})}/></label><label>Endpoint SPARQL à ouvrir<input value={settings.ontosphere_sparql_url} onChange={e=>setSettings({...settings,ontosphere_sparql_url:e.target.value})}/></label><label>Graphe de revue par défaut<input value={settings.ontosphere_review_graph} onChange={e=>setSettings({...settings,ontosphere_review_graph:e.target.value})}/></label></div><div className="button-row"><button className="ghost-button" onClick={()=>void copy(settings.ontosphere_review_graph)}><Copy size={16}/>Copier l’URI du graphe</button><button className="ghost-button" onClick={()=>void copy(settings.ontosphere_sparql_url)}><Copy size={16}/>Copier l’endpoint SPARQL</button><button className="ghost-button" disabled={!settings.ontosphere_url} onClick={()=>window.open(settings.ontosphere_url,"_blank","noopener,noreferrer")}><ExternalLink size={16}/>Ouvrir l’outil de revue</button><a className="button-link secondary-link" href={api.exportUrl("ttl")}><Download size={16}/>Exporter le graphe de revue</a></div><p className="quiet-note">L’export actuel est le Turtle générique ECUME. ECUME prépare les liens et les exports ; il ne pilote pas l’outil de revue.</p>
    </div></details>

    <details className="admin-subsection"><summary><ShieldCheck size={17}/>Authentification et sécurité</summary><div className="admin-subsection-body">
      <div className="admin-grid"><label>Authentification<select value={settings.rdf_auth_type} onChange={e=>setSettings({...settings,rdf_auth_type:e.target.value as RDFSettings["rdf_auth_type"]})}><option value="none">Aucune</option><option value="basic">Basic</option><option value="bearer">Bearer token</option><option value="other">Autre</option></select></label><label>Utilisateur<input value={settings.rdf_auth_username} onChange={e=>setSettings({...settings,rdf_auth_username:e.target.value})}/></label><label className="full-row">Mot de passe ou token<input type="password" autoComplete="new-password" placeholder={settings.has_rdf_auth_secret ? "Secret enregistré, saisir pour le remplacer" : "Non renseigné"} value={settings.rdf_auth_secret} onChange={e=>setSettings({...settings,rdf_auth_secret:e.target.value})}/></label></div><label className="toggle-row"><input type="checkbox" checked={settings.rdf_read_only} onChange={e=>setSettings({...settings,rdf_read_only:e.target.checked})}/>Mode lecture seule</label><label className="toggle-row"><input type="checkbox" checked={settings.rdf_write_candidates_only} onChange={e=>setSettings({...settings,rdf_write_candidates_only:e.target.checked})}/>Écriture limitée aux candidats</label><label className="toggle-row"><input type="checkbox" checked={settings.rdf_write_validated} onChange={e=>setSettings({...settings,rdf_write_validated:e.target.checked})}/>Autoriser les graphes validés ECUME</label>{settings.has_rdf_auth_secret&&<label className="toggle-row"><input type="checkbox" checked={Boolean(settings.clear_rdf_auth_secret)} onChange={e=>setSettings({...settings,clear_rdf_auth_secret:e.target.checked})}/>Effacer le secret enregistré</label>}<p className="quiet-note">Les secrets sont masqués dans l’interface et ne sont jamais renvoyés par l’API.</p>
    </div></details>

    <div className="button-row rdf-save"><button onClick={()=>void save()} disabled={busy}><Save size={16}/>Enregistrer l’écosystème RDF</button></div>
  </section>;
}
