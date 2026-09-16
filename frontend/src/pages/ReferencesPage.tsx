import { useEffect, useState } from "react";
import { FileUp, Trash2, ChevronLeft, ChevronRight, Download } from "lucide-react";
import { api } from "../api/client";
import type { ReferenceRepository, ReferenceTerm } from "../types";
import { ActionError, ContextHelp } from "../components/ContextHelp";
import EchoMappings from "../components/EchoMappings";

export default function ReferencesPage() {
  const [repositories, setRepositories] = useState<ReferenceRepository[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState("");
  const [layer, setLayer] = useState("auto");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("");
  const [termQuery, setTermQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [terms, setTerms] = useState<ReferenceTerm[]>([]);
  const [total, setTotal] = useState(0);
  const [more, setMore] = useState(false);
  const [loadingTerms, setLoadingTerms] = useState(false);
  useEffect(() => {
    let cancelled = false;
    api.references().then(items => { if (!cancelled) setRepositories(items); })
      .catch(err => { if (!cancelled) setError(String(err)); });
    return () => { cancelled = true; };
  }, [refresh]);
  useEffect(() => {
    let cancelled = false;
    setTerms([]); setTotal(0); setMore(false);
    if (!selected) return;
    setLoadingTerms(true);
    const timer = setTimeout(() => {
      api.referenceTerms(selected, termQuery, offset).then(result => {
        if (!cancelled) { setTerms(result.items); setTotal(result.total); setMore(result.has_more); }
      }).catch(err => { if (!cancelled) setError(String(err)); })
        .finally(() => { if (!cancelled) setLoadingTerms(false); });
    }, 200);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [selected, termQuery, offset, refresh]);
  async function act(action: () => Promise<unknown>, message: string) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); setNotice(message); setRefresh(value => value+1); }
    catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  }
  const filtered = repositories.filter(item => (item.name+" "+item.filename).toLocaleLowerCase("fr").includes(query.toLocaleLowerCase("fr")));
  return <section className="page-stack">
    <ContextHelp>ECUME utilise une copie locale pour préparer des correspondances. Vos référentiels originaux ne sont jamais modifiés.</ContextHelp>
    <form className="reference-import" onSubmit={event => {
      event.preventDefault(); if (!file) return;
      void act(async () => {
        const result = await api.importReference(file,target,layer);
        setTarget(result.id);
        setSelected(result.id); setOffset(0); setTermQuery("");
      }, "Référentiel disponible. Une copie identique déjà importée est réutilisée.");
    }}>
      <label>Référentiel Echo<select value={target} disabled={busy} onChange={event=>setTarget(event.target.value)}><option value="">Nouveau / regrouper par nom de fichier</option>{repositories.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
      <label>Couche<select value={layer} disabled={busy} onChange={event=>setLayer(event.target.value)}><option value="auto">Détection automatique</option><option value="owl">OWL · modèle conceptuel</option><option value="voc">VOC · vocabulaire métier</option><option value="shacl">SHACL · règles de contrôle</option><option value="mixed">Plusieurs couches</option></select></label>
      <label>Charger un fichier<input type="file" accept=".ttl,.rdf,.owl,.xml,.shacl" disabled={busy} onChange={event => setFile(event.target.files?.[0] ?? null)} /></label>
      <button disabled={!file || busy}><FileUp size={16} />{busy ? "Traitement…" : "Importer la copie"}</button>
    </form>
    <ActionError error={error} />
    {notice && <p className="success" role="status">{notice}</p>}
    <div className="section-title"><h2>Référentiels disponibles</h2><span>{filtered.length} / {repositories.length}</span></div>
    <input className="search-input" aria-label="Rechercher un référentiel" placeholder="Rechercher un référentiel" value={query} onChange={event => setQuery(event.target.value)} />
    {!filtered.length && <p className="quiet-note">Aucun référentiel dans cette sélection.</p>}
    <div className="reference-list">{filtered.map(repository => <article className="reference-row" key={repository.id}>
      <div className="section-title"><h3>{repository.name}</h3><label className="checkbox-row"><input type="checkbox" checked={repository.active} disabled={busy} onChange={event => void act(() => api.activateReference(repository.id,event.target.checked), "Activation enregistrée. Les décisions existantes sont conservées.")} />Actif pour les correspondances</label></div>
      <p className="quiet-note">{new Date(repository.created_at).toLocaleString("fr-FR")} · {repository.profile.term_count} termes · {repository.profile.relation_count} relations · {repository.profile.status === "partial" ? "Profil partiel" : "Profil détecté"}</p>
      <div className="button-row"><button className="ghost-button" onClick={() => { setSelected(selected === repository.id ? "" : repository.id); setOffset(0); setTermQuery(""); }}>Examiner</button>
        <button className="ghost-button" disabled={busy} onClick={() => {
          const confirmation = window.prompt("Supprimer la copie locale et ses correspondances ? La connaissance ECUME et le fichier original sont conservés. Saisissez SUPPRIMER.");
          if (confirmation === "SUPPRIMER") void act(async () => { await api.deleteReference(repository.id, confirmation); if (selected === repository.id) setSelected(""); }, "Copie locale supprimée. Connaissance ECUME conservée.");
        }}><Trash2 size={15} />Supprimer la copie</button></div>
      {selected === repository.id && <div className="reference-inspection">
        {repository.profile.echo && <>
          <p>Profil : {{sufficient:"suffisant",partial:"partiel",insufficient:"insuffisant"}[repository.profile.echo.confidence]} · Correspondances : {repository.profile.echo.alignment_ready ? "exploitables" : "à vérifier"}</p>
          <dl className="echo-layers">{Object.entries(repository.profile.echo.layers).map(([name,info])=><div key={name}><dt>{name.toUpperCase()}</dt><dd>{{not_provided:"Non fournie",imported:"Importée",partial:"Partiellement comprise",insufficient:"Insuffisante"}[info.state] || info.state}</dd></div>)}</dl>
          <p className="quiet-note">{repository.profile.echo.owl.classes.length} classes · {repository.profile.echo.owl.properties.length} propriétés · {repository.profile.echo.voc.term_count} termes · {repository.profile.echo.shacl.interpreted} formes interprétées · {repository.profile.echo.shacl.uninterpreted} non interprétées</p>
          <details><summary>Fichiers associés ({repository.profile.echo.files?.length || 1}) et limites</summary>
            <ul>{repository.profile.echo.files?.map(f=><li key={f.id}>{f.filename} · {f.layer} · {f.format}</li>)}</ul>
            <ul>{repository.profile.echo.warnings.map((w,i)=><li key={i}>{w}</li>)}</ul>
            <p>{repository.profile.echo.rdf_export_reason}</p>
            {repository.profile.echo.shacl.shapes.filter(s=>s.status!=="interpreted").map(s=><p key={s.uri}>{s.label} : {s.unsupported.join(", ")}</p>)}
          </details>
        </>}
        {repository.profile.warnings.length > 0 && <details><summary>{repository.profile.warnings.length} points à vérifier</summary><ul>{repository.profile.warnings.map((warning,i) => <li key={i}>{warning}</li>)}</ul></details>}
        <p className="quiet-note">Langue principale : {repository.profile.main_language || "non détectée"} · Version : {repository.version || "non détectée"}</p>
        <EchoMappings repositoryId={repository.id} />
        <details className="echo-export"><summary>Préparer un lot d’enrichissement</summary>
          <p className="quiet-note">Propositions à relire avant réimport externe. Aucune modification du référentiel original.</p>
          <div className="button-row"><a className="button-link" href={api.echoExportUrl(repository.id,"json")} download><Download size={16} />Lot JSON Echo</a><a className="button-link" href={api.echoExportUrl(repository.id,"csv")} download><Download size={16} />CSV de contrôle</a></div>
        </details>
        <details className="reference-technical"><summary>Détails techniques du profil</summary>
          <dl><dt>Format</dt><dd>{repository.format}</dd><dt>Namespace principal</dt><dd>{repository.namespace || "Non détecté"}</dd>
            <dt>Libellés</dt><dd>{repository.profile.label_properties.join(", ") || "Non reconnus"}</dd><dt>Synonymes</dt><dd>{repository.profile.alias_properties.join(", ") || "Non reconnus"}</dd>
            <dt>Définitions</dt><dd>{repository.profile.definition_properties.join(", ") || "Non reconnues"}</dd><dt>Hiérarchie</dt><dd>{repository.profile.hierarchy_properties.join(", ") || "Non reconnue"}</dd>
            <dt>Associations</dt><dd>{repository.profile.associative_properties.join(", ") || "Non reconnues"}</dd>
            <dt>Namespaces</dt><dd>{Object.entries(repository.profile.namespaces).map(([prefix,uri]) => <div key={prefix}>{prefix || "(défaut)"} : {uri}</div>)}</dd>
          </dl>
        </details>
        <label>Rechercher dans les termes<input value={termQuery} onChange={event => { setTermQuery(event.target.value); setOffset(0); }} /></label>
        <p className="quiet-note" role="status">{loadingTerms ? "Chargement…" : total+" termes"}</p>
        <ul className="reference-terms">{terms.map(term => <li key={term.id}><strong>{term.label}</strong>
          <p>{term.definition || term.comment || "Définition non renseignée."}</p>
          {!!term.aliases.length && <p className="quiet-note">Autres noms : {term.aliases.join(", ")}</p>}
          <details><summary>Détails techniques</summary><p>{term.uri}</p><p>{term.types.join(", ")}</p></details>
        </li>)}</ul>
        {(offset > 0 || more) && <div className="button-row"><button className="ghost-button" disabled={loadingTerms || !offset} onClick={() => setOffset(Math.max(0,offset-8))}><ChevronLeft size={16} />Précédents</button><button className="ghost-button" disabled={loadingTerms || !more} onClick={() => setOffset(offset+8)}>Voir plus<ChevronRight size={16} /></button></div>}
      </div>}
    </article>)}</div>
  </section>;
}
