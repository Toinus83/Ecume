import { FileUp, RotateCw, Wand2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import DocumentLibrary from "../components/DocumentLibrary";
import ValidationControls from "../components/ValidationControls";
import { ContextHelp, ActionError } from "../components/ContextHelp";
import type { AnalysisJob, RetentionPolicy, SourceDocument, ValidationSettings, ExtractionMode } from "../types";

interface Props {
  onAnalyzed: () => void;
  refreshKey: number;
  jobs: AnalysisJob[];
  onOpenCards: (document: SourceDocument) => void;
}

export default function ImportPage({ onAnalyzed, refreshKey, jobs, onOpenCards }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [document, setDocument] = useState<SourceDocument | null>(null);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [error, setError] = useState("");
  const [retention, setRetention] = useState<RetentionPolicy>("keep");
  const [settingsReady, setSettingsReady] = useState(false);
  const [validation, setValidation] = useState<ValidationSettings | null>(null);
  const [extractionMode, setExtractionMode] = useState<ExtractionMode>("sober");
  const [manualOpen, setManualOpen] = useState(false);
  const [manual, setManual] = useState({
    theme_label: "",
    label: "",
    description: "",
    objects: "",
    actions: "",
    conditions: "",
    tasks: ""
  });

  const lastStarted = useRef<AnalysisJob | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.importSettings().then(settings => {
      if (!cancelled) { setRetention(settings.retention_policy); setSettingsReady(true); }
    }).catch(err => { if (!cancelled) setError(String(err)); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const tracked = lastStarted.current ? jobs.find(item => item.id === lastStarted.current?.id) ?? lastStarted.current : jobs[0];
    if (tracked) {
      setJob(tracked);
      if (tracked.status === "failed") { setError(tracked.error || "Analyse interrompue"); setManualOpen(true); }
    } else { setJob(null); }
  }, [jobs]);

  function analysisStarted(source: SourceDocument, started: AnalysisJob) {
    lastStarted.current = started;
    setDocument(source); setJob(started); setError(""); onAnalyzed();
  }

  async function uploadAndAnalyze() {
    if (!file || !validation) return;
    setBusy(true);
    setError("");
    try {
      const uploaded = await api.uploadDocument(file);
      setDocument(uploaded);
      const startedJob = await api.analyzeDocument(uploaded.id, validation, extractionMode);
      analysisStarted(uploaded, startedJob);
      setBusy(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import impossible");
      setManualOpen(true);
      setBusy(false);
    }
  }

  async function retryAnalyze() {
    if (!document || !validation) return;
    setBusy(true);
    setError("");
    try {
      const startedJob = await api.analyzeDocument(document.id, validation, extractionMode);
      analysisStarted(document, startedJob);
      setBusy(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analyse impossible");
      setBusy(false);
    }
  }

  function split(value: string) {
    return value.split(",").map((item) => item.trim()).filter(Boolean);
  }

  async function createManualCard() {
    setBusy(true);
    setError("");
    try {
      await fetch(`${api.baseUrl}/cards`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id: document?.id,
          theme_label: manual.theme_label,
          main_effect: {
            label: manual.label,
            description: manual.description,
            level: "unknown",
            confidence: "medium"
          },
          level: "unknown",
          objects: split(manual.objects),
          actions: split(manual.actions),
          conditions: split(manual.conditions),
          tasks: split(manual.tasks),
          source_excerpt: manual.description
        })
      }).then((response) => {
        if (!response.ok) throw new Error("Création manuelle impossible");
      });
      onAnalyzed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Création impossible");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-stack">
      <ContextHelp>Les sources peuvent être conservées ou purgées sans perdre les cartes et leurs extraits utiles.</ContextHelp>
      <div className="import-zone"><h2>Charger un document</h2>
        <label className="dropzone">
          <FileUp size={28} />
          <span>{file ? file.name : "Choisir un fichier .txt, .md, .pdf ou .docx"}</span>
          <input type="file" accept=".txt,.md,.pdf,.docx" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        </label>
        <ValidationControls onSettingsChange={setValidation} />
        <label className="extraction-mode">Mode d’extraction<select value={extractionMode} disabled={busy} onChange={e => setExtractionMode(e.target.value as ExtractionMode)}>
          <option value="sober">Sobre · les essentiels</option><option value="balanced">Équilibré · davantage de contexte</option><option value="exhaustive">Exhaustif · pour un examen approfondi</option>
        </select></label>
        <p className="quiet-note extraction-help">Plus l’extraction est exhaustive, plus il y aura de choses à vérifier. Pour commencer, privilégiez Sobre.</p>
        <details className="source-options"><summary>Conservation du fichier source</summary>        <label className="retention-field">Conservation des prochains imports
          <select value={retention} disabled={busy || !settingsReady} onChange={async e => {
            const policy = e.target.value as RetentionPolicy;
            setBusy(true); setError("");
            try { await api.saveImportSettings(policy); setRetention(policy); }
            catch (err) { setError(String(err)); }
            finally { setBusy(false); }
          }}>
            <option value="keep">Conserver les sources</option>
            <option value="purge_after_success">Purger les sources après analyse réussie</option>
          </select>
        </label>
</details>
        <div className="button-row">
          <button onClick={uploadAndAnalyze} disabled={!file || busy || !settingsReady || !validation}><Wand2 size={16} />Importer et analyser</button>
          {job?.status === "failed" && <button className="ghost-button" onClick={retryAnalyze} disabled={!document || !validation || busy}><RotateCw size={16} />Réessayer l’analyse</button>}
        </div>
      </div>

      {busy && <div className="working"><span />ECUME prépare le traitement...</div>}
      {job && (job.status === "running" || job.status === "queued") && (
        <div className="job-panel">
          <div className="section-title">
            <h2>Analyse en cours</h2>
            <span>en cours</span>
          </div>
          <div className="progress-bar" role="progressbar" aria-label="Progression de l’analyse" aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.progress}>
            <span style={{ width: `${Math.max(0, Math.min(100, job.progress))}%` }} />
          </div>
          <p>{job.step === "chunking" ? "Préparation du document" : job.step === "llm_analysis" ? "Lecture et compréhension du document" : job.step === "card_generation" ? "Préparation des cartes" : job.step === "saving" ? "Enregistrement des propositions" : "Préparation de l’analyse"}</p>
          {job.total_chunks > 0 && (
            <small>Partie {job.current_chunk || 0} / {job.total_chunks} · {job.progress}%</small>
          )}
          <p className="quiet-note">Vous pouvez changer d’onglet : l’analyse continue tant qu’ECUME reste lancé.</p>
        </div>
      )}
      {job?.status === "completed" && <p className="success" role="status">Analyse terminée. Les cartes sont disponibles dans la liste des documents.</p>}
      <ActionError error={error} />

      <DocumentLibrary refreshKey={refreshKey} validation={validation} extractionMode={extractionMode} onAnalyze={analysisStarted} onOpenCards={onOpenCards} onChanged={onAnalyzed} />

      {manualOpen && (
        <section className="panel">
          <div className="section-title">
            <h2>Carte manuelle</h2>
            <span>Création manuelle</span>
          </div>
          <div className="manual-grid">
            <input placeholder="Thème" value={manual.theme_label} onChange={(event) => setManual({ ...manual, theme_label: event.target.value })} />
            <input placeholder="Effet principal" value={manual.label} onChange={(event) => setManual({ ...manual, label: event.target.value })} />
            <textarea placeholder="Description ou extrait source" value={manual.description} onChange={(event) => setManual({ ...manual, description: event.target.value })} />
            <input placeholder="Objets séparés par virgules" value={manual.objects} onChange={(event) => setManual({ ...manual, objects: event.target.value })} />
            <input placeholder="Actions séparées par virgules" value={manual.actions} onChange={(event) => setManual({ ...manual, actions: event.target.value })} />
            <input placeholder="Conditions séparées par virgules" value={manual.conditions} onChange={(event) => setManual({ ...manual, conditions: event.target.value })} />
            <input placeholder="Tâches séparées par virgules" value={manual.tasks} onChange={(event) => setManual({ ...manual, tasks: event.target.value })} />
          </div>
          <button onClick={createManualCard} disabled={busy || !manual.label}>Créer la carte</button>
        </section>
      )}
    </section>
  );
}
