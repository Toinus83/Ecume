import { useEffect, useState } from "react";
import { api } from "../api/client";
import SimpleConcept from "../components/SimpleConcept";
import DocumentDomain from "../components/DocumentDomain";
import { ActionError } from "../components/ContextHelp";
import type { SourceDocument, ReviewWorkspace } from "../types";

function explainAnalysisIssue(message: string) {
  if (message.includes("aucun concept")) return "ECUME n'a pas trouvé de concept suffisamment clair dans cette partie du document.";
  if (message.includes("n a pas pu etre analysee")) return "ECUME n'a pas réussi à lire cette partie avec le modèle configuré.";
  if (message.includes("Valeur ou exception")) return "Un nombre, un seuil ou une exception apparaît dans le texte, mais ECUME n'a pas pu le rattacher avec certitude à un concept.";
  if (message.includes("Message de controle ecarte")) return "Une proposition ressemblait à un message de contrôle plutôt qu'à un concept métier ; ECUME l'a écartée.";
  return message;
}

interface Props {
  refreshKey: number;
  onOpenGraph: () => void;
  documentFilter: SourceDocument | null;
  cardFilter: string | null;
  onClearDocument: () => void;
}

export default function CardsPage({ refreshKey, onOpenGraph, documentFilter, cardFilter, onClearDocument }: Props) {
  const [data, setData] = useState<ReviewWorkspace>({ items: [], reports: [], issues: [] });
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [limit, setLimit] = useState(12);
  const [currentDocument,setCurrentDocument]=useState<SourceDocument|null>(documentFilter);
  useEffect(()=>setCurrentDocument(documentFilter),[documentFilter]);
  useEffect(() => {
    let alive = true;
    api.review(documentFilter?.id).then(result => { if (alive) { setData(result); setError(""); } })
      .catch(err => { if (alive) setError(String(err)); });
    return () => { alive = false; };
  }, [refreshKey, revision, documentFilter?.id]);
  useEffect(() => setLimit(12), [query, documentFilter?.id, cardFilter]);
  const items = data.items.filter(item => (!cardFilter || item.card_id === cardFilter) &&
    `${item.label} ${item.description} ${item.target?.label ?? ""}`.toLocaleLowerCase("fr").includes(query.toLocaleLowerCase("fr")));
  const report = documentFilter ? data.reports[0] : undefined;
  const history = items.filter(item => ["validated", "ignored"].includes(item.status));
  const issues = [...data.issues, ...(report?.issues ?? [])];
  function cards(status: string) {
    const selected = items.filter(item => item.status === status);
    return <>{selected.length === 0 ? <p className="quiet-note">Aucun élément dans cette rubrique.</p> :
      <div className="cards-grid">{selected.slice(0, limit).map(item =>
        <SimpleConcept key={item.id + item.updated_at} item={item} onChanged={() => setRevision(v => v + 1)} />)}</div>}
      {selected.length > limit && <button className="ghost-button" onClick={() => setLimit(v => v + 12)}>Voir la suite ({selected.length - limit})</button>}</>;
  }
  return <section className="page-stack">
    <ActionError error={error} />
    <details className="page-help">
      <summary>Que dois-je faire ici ?</summary>
      <p><strong>Nouveaux concepts :</strong> validez uniquement les notions utiles à mémoriser.</p>
      <p><strong>Déjà reconnus :</strong> vérifiez seulement si le rattachement proposé paraît faux.</p>
      <p><strong>À vérifier :</strong> ECUME vous indique précisément ce qu'il n'a pas réussi à confirmer.</p>
    </details>
    {currentDocument && <div className="document-filter"><strong>{currentDocument.filename}</strong><button className="ghost-button" onClick={onClearDocument}>Tous les documents</button></div>}
    {cardFilter && <button className="ghost-button" onClick={onClearDocument}>Toutes les cartes</button>}
    {currentDocument&&report&&<DocumentDomain document={currentDocument} onChanged={setCurrentDocument}/>}
    {report && <section className="analysis-summary" aria-label="Bilan de l'analyse">
      <h2>Bilan de l'analyse</h2><p role="status">{report.message}</p>
      <dl className="report-counts">
        <div><dt>Texte lu</dt><dd>{report.text_read ? "Oui" : "Non"}</dd></div>
        <div><dt>Concepts repérés</dt><dd>{report.concepts_found}</dd></div>
        <div><dt>Nouveaux</dt><dd>{report.new}</dd></div>
        <div><dt>Connus dans ECUME</dt><dd>{report.known_ecume}</dd></div>
        <div><dt>Reconnus dans Echo</dt><dd>{report.known_echo}</dd></div>
        <div><dt>À vérifier</dt><dd>{report.review + report.issues.length}</dd></div>
      </dl>
      {report.analysis_problem && <p className="error">Analyse incomplète. La source est conservée pour permettre une nouvelle tentative.</p>}
      <details className="report-help"><summary>Comment lire ce bilan ?</summary>
        <p>« Concepts repérés » compte toutes les notions vues dans le document. Une notion déjà connue est montrée pour contrôle, mais ne crée pas de doublon. « À vérifier » regroupe uniquement les ambiguïtés et les informations qu'ECUME n'a pas pu justifier.</p>
      </details>
    </section>}
    {documentFilter && !report && <p className="quiet-note">Aucun bilan détaillé enregistré pour cette ancienne analyse. Un résultat vide ne signifie pas que tous les concepts étaient déjà connus.</p>}
    <input className="search-input" aria-label="Rechercher un concept" placeholder="Rechercher un concept" value={query} onChange={e => setQuery(e.target.value)} />
    <section className="review-section"><h2>Nouveaux concepts proposés <small>({items.filter(i => i.status === "new").length})</small></h2>{cards("new")}</section>
    <section className="review-section"><h2>Déjà reconnus <small>({items.filter(i => i.status === "known").length})</small></h2>{cards("known")}</section>
    <section className="review-section"><h2>À vérifier <small>({items.filter(i => i.status === "review").length + issues.length})</small></h2>
      {cards("review")}
      {issues.length > 0 && <details><summary>Points de lecture à vérifier ({issues.length})</summary>{issues.map((issue, index) =>
        <div className="analysis-issue" key={index}><p>{explainAnalysisIssue(issue.message)}</p>{issue.source_excerpt && <blockquote>{issue.source_excerpt}</blockquote>}{issue.detail && <details><summary>Détail technique</summary><p>{issue.detail}</p></details>}</div>)}</details>}
    </section>
    <details><summary>Décisions prises ({history.length})</summary><div className="cards-grid">
      {history.slice(0, limit).map(item => <SimpleConcept key={item.id + item.updated_at} item={item} onChanged={() => setRevision(v => v + 1)} />)}
    </div>{history.length > limit && <button className="ghost-button" onClick={() => setLimit(v => v + 12)}>Voir la suite</button>}</details>
    <button className="ghost-button" onClick={onOpenGraph}>Ouvrir la connaissance validée</button>
  </section>;
}
