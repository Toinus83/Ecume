import { BookOpen, Eraser, FileUp, RotateCw, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { ActionError, Hint } from "./ContextHelp";
import type { AnalysisJob, RetentionPolicy, SourceDocument, ValidationSettings } from "../types";

interface Props {
  validation: ValidationSettings | null;
  extractionMode: string;
  refreshKey: number;
  onAnalyze: (document: SourceDocument, job: AnalysisJob) => void;
  onOpenCards: (document: SourceDocument) => void;
  onChanged: () => void;
}
const states = { queued: "En attente", running: "En cours", completed: "Analyse terminée", failed: "Analyse interrompue ou échouée" };
const sourceStates = { retained: "Source conservée", purged: "Source purgée", missing: "Source absente", purge_pending: "Purge à terminer" };

export default function DocumentLibrary({ refreshKey, validation, extractionMode, onAnalyze, onOpenCards, onChanged }: Props) {
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [readError, setReadError] = useState("");
  const [notice, setNotice] = useState("");
  const [target, setTarget] = useState<SourceDocument | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [deleteKnowledge, setDeleteKnowledge] = useState(false);
  const [knowledgeConfirmation, setKnowledgeConfirmation] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number;
    async function poll() {
      try {
        const result = await api.documents();
        if (!cancelled) { setDocuments(result); setReadError(""); }
      } catch (err) {
        if (!cancelled) setReadError(err instanceof Error ? err.message : "Documents indisponibles");
      } finally {
        if (!cancelled) timer = window.setTimeout(poll, 3000);
      }
    }
    void poll();
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [refreshKey]);

  async function act(id: string, action: () => Promise<unknown>, message: string) {
    setBusy(id); setError(""); setNotice("");
    try {
      await action();
      setNotice(message);
      onChanged();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action impossible");
      return false;
    } finally { setBusy(null); }
  }
  function openDelete(document: SourceDocument) {
    setTarget(document); setConfirmation(""); setDeleteKnowledge(false); setKnowledgeConfirmation("");
    dialog.current?.showModal();
  }
  const filtered = documents.filter(doc => `${doc.filename} ${doc.title}`.toLocaleLowerCase("fr").includes(query.toLocaleLowerCase("fr")));
  return <section className="document-library">
    <div className="section-title"><h2>Documents importés</h2><span>{filtered.length} / {documents.length}</span></div>
    <input className="search-input" aria-label="Rechercher un document" placeholder="Rechercher un document" value={query} onChange={e => setQuery(e.target.value)} />
    {notice && <p className="success" role="status">{notice}</p>}
    <ActionError error={error} />
    <ActionError error={readError} />
    <div className="document-list">
      {!filtered.length && <p>Aucun document.</p>}
      {filtered.map(doc => {
        const job = doc.latest_job;
        const policy = job?.metadata?.validation_policy as ValidationSettings | undefined;
        const active = job?.status === "running" || job?.status === "queued";
        const disabled = busy !== null || active;
        return <article className="document-row" key={doc.id}>
          <div className="document-heading"><h3>{doc.filename}</h3><time>{new Date(doc.created_at).toLocaleString("fr-FR")}</time></div>
          <div className="document-facts">
            <span>{job ? states[job.status] : "Non analysé"}{active ? ` · ${job?.progress}%` : ""}</span>
            <span>{sourceStates[doc.source_status]} {doc.source_status === "purged" && <Hint label="Source purgée">Le fichier original n’est plus conservé. Les cartes et extraits utiles restent disponibles.</Hint>}</span>
            <span>{policy ? `Mode de la dernière analyse : ${{ strict: "Strict", assisted: "Assisté", automatic: "Automatique" }[policy.mode]}` : "Mode historique non enregistré"}</span>
          </div>
          <p className="document-counts">{doc.card_count} cartes · {doc.card_counts?.validated ?? 0} validées · {doc.card_counts?.auto_validated ?? 0} auto-validées · {doc.card_counts?.to_review ?? 0} à revoir · {doc.card_counts?.rejected ?? 0} rejetées</p>
          {job?.status === "failed" && <details className="document-error"><summary>Détail de l'interruption</summary><p className="error">{job.error || job.message}</p></details>}
          {!!job?.warnings.length && <details><summary>{job.warnings.length} points à vérifier</summary>{job.warnings.map((warning, index) => <p className="quiet-note" key={index}>{warning}</p>)}</details>}
          <details className="document-menu"><summary>Actions</summary><div className="document-actions">
            <p className="quiet-note">{doc.can_reanalyze ? "Analyse relançable. Les propositions existantes sont conservées." : "Fournissez à nouveau le fichier pour relancer l’analyse."}</p>
            <button className="ghost-button" onClick={() => onOpenCards(doc)} disabled={!doc.card_count}><BookOpen size={16} />Ouvrir les cartes</button>
            <button className="ghost-button" disabled={disabled || !doc.can_reanalyze || !validation} onClick={() => {
              if (!validation) return;
              void act(doc.id, async () => onAnalyze(doc, await api.analyzeDocument(doc.id, validation, extractionMode)), "Analyse lancée. Vous pouvez changer d’onglet.");
            }}><RotateCw size={16} />Relancer</button>
            {!doc.source_available && doc.file_type !== "manual" && doc.source_status !== "purge_pending" && <label className={`source-upload ${disabled ? "disabled" : ""}`}>
              <FileUp size={16} />Fournir à nouveau le fichier
              <input type="file" accept={`.${doc.file_type}`} disabled={disabled} onChange={e => {
                const file = e.target.files?.[0]; e.target.value = "";
                if (file) void act(doc.id, () => api.restoreSource(doc.id, file), "Source restaurée. L'analyse peut être relancée.");
              }} />
            </label>}
            <button className="ghost-button" disabled={disabled || doc.source_status === "purged"} onClick={() => {
              if (window.confirm("Purger le fichier source et le texte intégral ? Les cartes, concepts, liens et extraits courts seront conservés."))
                void act(doc.id, () => api.purgeSource(doc.id), "Source purgée. La connaissance et ses extraits sont conservés.");
            }}><Eraser size={16} />Purger la source</button>
            <button className="danger-button" disabled={disabled} onClick={() => openDelete(doc)}><Trash2 size={16} />Supprimer</button>
            <label className="retention-field">Conservation
              <select aria-label={`Conservation de ${doc.filename}`} disabled={disabled} value={doc.retention_policy} onChange={e => void act(doc.id,
                () => api.documentRetention(doc.id, e.target.value as RetentionPolicy), "Règle enregistrée pour la prochaine analyse réussie.")}>
                <option value="keep">Conserver la source</option><option value="purge_after_success">Purger après réussite</option>
              </select>
            </label>
          </div></details>
        </article>;
      })}
    </div>
    <dialog ref={dialog} className="document-dialog" onCancel={e => { if (busy) e.preventDefault(); }}>
      <div className="section-title"><h2>Supprimer le document</h2><button className="ghost-button" title="Fermer" aria-label="Fermer" disabled={!!busy} onClick={() => dialog.current?.close()}><X size={18} /></button></div>
      <p>{target?.filename}</p>
      <p>Le fichier source sera purgé. Par défaut, les cartes et la connaissance restent conservées, avec une référence documentaire historique.</p>
      <label className="confirmation-field">Saisir SUPPRIMER<input autoComplete="off" value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label>
      <label className="checkbox-row"><input type="checkbox" checked={deleteKnowledge} onChange={e => setDeleteKnowledge(e.target.checked)} />Supprimer aussi les cartes et les concepts exclusivement associés, y compris validés</label>
      {deleteKnowledge && <><p>Les concepts partagés sont protégés. Cette suppression ne peut pas être annulée.</p><label className="confirmation-field">Saisir SUPPRIMER LES CONNAISSANCES<input autoComplete="off" value={knowledgeConfirmation} onChange={e => setKnowledgeConfirmation(e.target.value)} /></label></>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="button-row"><button className="ghost-button" disabled={!!busy} onClick={() => dialog.current?.close()}>Annuler</button>
        <button className="danger-button" disabled={!!busy || confirmation !== "SUPPRIMER" || (deleteKnowledge && knowledgeConfirmation !== "SUPPRIMER LES CONNAISSANCES")} onClick={async () => {
          if (target && await act(target.id, () => api.deleteDocument(target.id, { confirmation, delete_knowledge: deleteKnowledge, knowledge_confirmation: knowledgeConfirmation }), "Document supprimé. Les références historiques restent disponibles.")) dialog.current?.close();
        }}><Trash2 size={16} />Confirmer la suppression</button></div>
    </dialog>
  </section>;
}
