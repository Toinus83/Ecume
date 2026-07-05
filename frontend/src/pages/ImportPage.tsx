import { FileUp, RotateCw, Wand2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AnalysisJob, SourceDocument } from "../types";

interface Props {
  onAnalyzed: () => void;
}

const steps = [
  "lecture du document",
  "extraction du texte",
  "analyse LLM",
  "génération des cartes",
  "recherche de liens existants",
  "sauvegarde dans la base"
];

export default function ImportPage({ onAnalyzed }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [document, setDocument] = useState<SourceDocument | null>(null);
  const [activeStep, setActiveStep] = useState(-1);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [error, setError] = useState("");
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

  const pollingRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (pollingRef.current) window.clearInterval(pollingRef.current);
    };
  }, []);

  async function uploadAndAnalyze() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      setActiveStep(0);
      const uploaded = await api.uploadDocument(file);
      setDocument(uploaded);
      setActiveStep(2);
      const startedJob = await api.analyzeDocument(uploaded.id);
      setJob(startedJob);
      setBusy(false);
      pollJob(startedJob.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import impossible");
      setManualOpen(true);
      setBusy(false);
    }
  }

  async function retryAnalyze() {
    if (!document) return;
    setBusy(true);
    setError("");
    try {
      setActiveStep(2);
      const startedJob = await api.analyzeDocument(document.id);
      setJob(startedJob);
      setBusy(false);
      pollJob(startedJob.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analyse impossible");
      setBusy(false);
    }
  }

  function pollJob(jobId: string) {
    if (pollingRef.current) window.clearInterval(pollingRef.current);
    pollingRef.current = window.setInterval(async () => {
      try {
        const nextJob = await api.job(jobId);
        setJob(nextJob);
        setActiveStep(stepFromJob(nextJob));
        if (nextJob.status === "completed") {
          if (pollingRef.current) window.clearInterval(pollingRef.current);
          pollingRef.current = null;
          setActiveStep(5);
          onAnalyzed();
        }
        if (nextJob.status === "failed") {
          if (pollingRef.current) window.clearInterval(pollingRef.current);
          pollingRef.current = null;
          setError(nextJob.error || "Analyse impossible");
          setManualOpen(true);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Suivi du job impossible");
      }
    }, 1500);
  }

  function stepFromJob(nextJob: AnalysisJob) {
    if (nextJob.step === "chunking") return 1;
    if (nextJob.step === "llm_analysis") return 2;
    if (nextJob.step === "card_generation") return 3;
    if (nextJob.step === "saving") return 5;
    if (nextJob.step === "completed") return 5;
    return 2;
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
      <div className="import-zone">
        <label className="dropzone">
          <FileUp size={28} />
          <span>{file ? file.name : "Choisir un fichier .txt, .md, .pdf ou .docx"}</span>
          <input type="file" accept=".txt,.md,.pdf,.docx" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        </label>
        <div className="button-row">
          <button onClick={uploadAndAnalyze} disabled={!file || busy}><Wand2 size={16} />Importer et analyser</button>
          <button className="ghost-button" onClick={retryAnalyze} disabled={!document || busy}><RotateCw size={16} />Réessayer l’analyse</button>
        </div>
      </div>

      <div className="progress-list">
        {steps.map((step, index) => (
          <div key={step} className={index <= activeStep ? "done" : ""}>
            <span>{index + 1}</span>
            <p>{step}</p>
          </div>
        ))}
      </div>

      {busy && <div className="working"><span />ECUME prépare le traitement...</div>}
      {job && job.status !== "failed" && (
        <div className="job-panel">
          <div className="section-title">
            <h2>Analyse backend</h2>
            <span>{job.status === "completed" ? "terminée" : "en cours"}</span>
          </div>
          <div className="progress-bar">
            <span style={{ width: `${Math.max(0, Math.min(100, job.progress))}%` }} />
          </div>
          <p>{job.message}</p>
          {job.total_chunks > 0 && (
            <small>Partie {job.current_chunk || 0} / {job.total_chunks} · {job.progress}%</small>
          )}
          {job.status !== "completed" && (
            <p className="quiet-note">Tu peux changer d’onglet : l’analyse continue côté backend.</p>
          )}
        </div>
      )}
      {error && <p className="error">{error}</p>}

      {manualOpen && (
        <section className="panel">
          <div className="section-title">
            <h2>Carte manuelle</h2>
            <span>mode sans LLM</span>
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
