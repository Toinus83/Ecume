import { FileUp, RotateCw, Square, Wand2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import DocumentLibrary from "../components/DocumentLibrary";
import { ContextHelp, ActionError } from "../components/ContextHelp";
import type { AnalysisJob, RetentionPolicy, SourceDocument, ExtractionMode } from "../types";

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
  const [fillMode, setFillMode] = useState("prefilled");
  const [extractionMode, setExtractionMode] = useState<ExtractionMode>("sober");
  const [manualOpen, setManualOpen] = useState(false);
  const [importing,setImporting]=useState(false);
  const [importStopping,setImportStopping]=useState(false);
  const [importNotice,setImportNotice]=useState("");
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
  const activeImport=useRef("");
  const stopRequested=useRef(false);

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
    if (!file) return;
    setBusy(true);
    setImporting(true);setImportStopping(false);setImportNotice("");stopRequested.current=false;
    const uploadId=crypto.randomUUID();activeImport.current=uploadId;
    setError("");
    try {
      const uploaded = await api.uploadDocument(file,uploadId);
      setImporting(false);activeImport.current="";
      setDocument(uploaded);
      const startedJob = await api.analyzeDocument(uploaded.id, undefined, extractionMode, fillMode);
      analysisStarted(uploaded, startedJob);
      setBusy(false);
    } catch (err) {
      if(stopRequested.current){setImportNotice("Import arrêté. Aucun document incomplet n’a été ajouté.");}
      else {setError(err instanceof Error ? err.message : "Import impossible");setManualOpen(true);}
      setBusy(false);
    } finally {
      setImporting(false);setImportStopping(false);activeImport.current="";
    }
  }

  async function stopImport(){
    if(!activeImport.current||importStopping)return;
    stopRequested.current=true;setImportStopping(true);setImportNotice("Arrêt demandé. ECUME termine l’étape en cours puis s’arrête proprement.");
    try{await api.cancelImport(activeImport.current);}catch(err){setError(err instanceof Error?err.message:"Arrêt impossible");setImportStopping(false);}
  }

  async function retryAnalyze() {
    if (!document) return;
    setBusy(true);
    setError("");
    try {
      const startedJob = await api.analyzeDocument(document.id, undefined, extractionMode, fillMode);
      analysisStarted(document, startedJob);
      setBusy(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analyse impossible");
      setBusy(false);
    }
  }

  async function stopAnalysis() {
    if (!job || !["queued", "running"].includes(job.status)) return;
    if (!window.confirm("Arrêter l’analyse ? ECUME terminera la partie en cours et conservera les premiers concepts détectés.")) return;
    setBusy(true); setError("");
    try {
      const updated = await api.cancelJob(job.id);
      setJob(updated); onAnalyzed();
    } catch (err) { setError(err instanceof Error ? err.message : "Arrêt impossible"); }
    finally { setBusy(false); }
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
        <label className="extraction-mode" title="Large limite le bruit. Fine donne plus de détails et demande plus de relecture.">Granularité d’analyse<select value={extractionMode} disabled={busy} onChange={e => setExtractionMode(e.target.value as ExtractionMode)}>
          <option value="sober">Large</option><option value="balanced">Moyenne</option><option value="exhaustive">Fine</option>
        </select></label>
        <label className="extraction-mode" title="Le pré-remplissage accélère le travail. Tout reste corrigeable.">Remplissage<select value={fillMode} disabled={busy} onChange={e => setFillMode(e.target.value)}><option value="manual">Manuel</option><option value="prefilled">Pré-rempli</option></select></label>
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
          <button onClick={uploadAndAnalyze} disabled={!file || busy || !settingsReady}><Wand2 size={16} />Importer et analyser</button>
          {(job?.status === "failed" || job?.status === "cancelled") && <button className="ghost-button" onClick={retryAnalyze} disabled={!document || busy}><RotateCw size={16} />Reprendre par une nouvelle analyse</button>}
        </div>
      </div>

      {importing&&<div className="job-panel import-progress" role="status"><div className="section-title"><h2>Import et extraction en cours</h2><span>{importStopping?"arrêt demandé":"en cours"}</span></div>
        <div className="indeterminate-progress"><span/></div><p>ECUME transfère le fichier puis extrait son texte.</p><p className="quiet-note">ECUME termine l’étape en cours puis s’arrête proprement.</p>
        {!importStopping&&<button className="ghost-button stop-analysis" onClick={()=>void stopImport()}><Square size={15}/>Arrêter après l’étape en cours</button>}</div>}
      {busy&&!importing&&!job&&<div className="working"><span />ECUME prépare le traitement...</div>}
      {importNotice&&<p className="notice" role="status">{importNotice}</p>}
      {job && ["running", "queued", "cancelling"].includes(job.status) && (
        <div className="job-panel">
          <div className="section-title">
            <h2>Analyse en cours</h2>
            <span>{job.status === "cancelling" ? "arrêt demandé" : "en cours"}</span>
          </div>
          <div className="progress-bar" role="progressbar" aria-label="Progression de l’analyse" aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.progress}>
            <span style={{ width: `${Math.max(0, Math.min(100, job.progress))}%` }} />
          </div>
          <p>{job.step === "chunking" ? "Préparation du document" : job.step === "llm_analysis" ? "Lecture et compréhension du document" : job.step === "card_generation" ? "Préparation des cartes" : job.step === "saving" ? "Enregistrement des propositions" : "Préparation de l’analyse"}</p>
          {job.total_chunks > 0 && (
            <small>Partie {job.current_chunk || 0} / {job.total_chunks} · {job.progress}%</small>
          )}
          <p className="quiet-note">Vous pouvez changer d’onglet : l’analyse continue tant qu’ECUME reste lancé.</p>
          {job.status !== "cancelling" ? <button className="ghost-button stop-analysis" disabled={busy} onClick={() => void stopAnalysis()}><Square size={15}/>Arrêter après la partie en cours</button> :
            <p className="quiet-note">ECUME attend la réponse de la partie en cours, puis sauvegardera les résultats déjà obtenus.</p>}
        </div>
      )}
      {job?.status === "completed" && <p className="success" role="status">{job.message}</p>}
      {job?.status === "cancelled" && <p className="notice" role="status">{job.message}</p>}
      <ActionError error={error} />

      <DocumentLibrary refreshKey={refreshKey} fillMode={fillMode} extractionMode={extractionMode} onAnalyze={analysisStarted} onOpenCards={onOpenCards} onChanged={onAnalyzed} />

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
