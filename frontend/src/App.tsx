import { useEffect, useMemo, useRef, useState } from "react";
import { BarChart3, BookOpen, Download, FileUp, GitFork, Layers3, Network, Settings, Sparkles } from "lucide-react";
import Dashboard from "./pages/Dashboard";
import ImportPage from "./pages/ImportPage";
import CardsPage from "./pages/CardsPage";
import GraphPage from "./pages/GraphPage";
import OrphansPage from "./pages/OrphansPage";
import ExportPage from "./pages/ExportPage";
import AdminPage from "./pages/AdminPage";
import ReferencesPage from "./pages/ReferencesPage";
import type { SourceDocument } from "./types";
import { useAnalysisJobs } from "./hooks/useAnalysisJobs";
import { ActionError } from "./components/ContextHelp";

type Page = "dashboard" | "import" | "cards" | "graph" | "orphans" | "exports" | "references" | "admin";

const nav = [
  { id: "dashboard", label: "Tableau", icon: BarChart3 },
  { id: "import", label: "Import", icon: FileUp },
  { id: "cards", label: "Cartes", icon: Layers3 },
  { id: "graph", label: "Graphe", icon: Network },
  { id: "orphans", label: "Orphelins", icon: GitFork },
  { id: "exports", label: "Exports", icon: Download },
  { id: "references", label: "Referentiels", icon: BookOpen },
  { id: "admin", label: "Admin", icon: Settings }
] as const;

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [refreshKey, setRefreshKey] = useState(0);
  const { jobs, error: jobsError } = useAnalysisJobs(refreshKey);
  const runningJob = jobs.find(job => job.status === "running" || job.status === "queued") ?? null;
  const latestJob = runningJob ?? jobs[0];
  const [documentFilter, setDocumentFilter] = useState<SourceDocument | null>(null);
  const [cardFilter, setCardFilter] = useState<string | null>(null);
  const terminalJobs = useRef("");
  useEffect(() => {
    const signature = jobs.filter(job => job.status === "completed" || job.status === "failed").map(job => `${job.id}:${job.status}`).sort().join("|");
    if (signature !== terminalJobs.current) {
      terminalJobs.current = signature;
      setRefreshKey(value => value + 1);
    }
  }, [jobs]);

  useEffect(() => {
    const fromHash = window.location.hash.replace("#", "") as Page;
    if (nav.some((item) => item.id === fromHash)) setPage(fromHash);
  }, []);

  const activeTitle = useMemo(() => nav.find((item) => item.id === page)?.label ?? "ECUME", [page]);

  useEffect(() => { window.scrollTo({ top: 0, left: 0 }); }, [page]);

  function navigate(next: Page) {
    setPage(next);
    window.location.hash = next;
  }

  function openDocumentCards(document: SourceDocument) {
    setDocumentFilter(document); setCardFilter(null); navigate("cards");
  }

  function openCard(cardId: string) {
    setCardFilter(cardId); setDocumentFilter(null); navigate("cards");
  }

  function refresh() {
    setRefreshKey((value) => value + 1);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Sparkles size={19} /></div>
          <div>
            <strong>ECUME</strong>
            <span>Connaissance usage</span>
          </div>
        </div>
        <nav className="nav-list">
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={page === item.id ? "active" : ""}
                onClick={() => navigate(item.id)}
                title={item.label}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">MVP local</p>
            <h1>{activeTitle}</h1>
            {jobsError ? <ActionError error={jobsError} /> : runningJob ? (
              <div className="top-job">
                <span style={{ width: `${Math.max(0, Math.min(100, runningJob.progress))}%` }} />
                <p>Analyse {runningJob.status === "queued" ? "en attente" : "en cours"} · {runningJob.progress} %</p>
              </div>
            ) : latestJob && <p className={latestJob.status === "failed" ? "error" : "quiet-note"} role="status">
              {latestJob.status === "completed" ? "Dernière analyse terminée · 100 %" : "Dernière analyse interrompue. Consulte le document dans Import."}
            </p>}
          </div>
          <button className="ghost-button" onClick={refresh}>Actualiser</button>
        </header>

        {page === "dashboard" && <Dashboard refreshKey={refreshKey} />}
        {page === "import" && <ImportPage jobs={jobs} refreshKey={refreshKey} onAnalyzed={refresh} onOpenCards={openDocumentCards} />}
        {page === "cards" && <CardsPage refreshKey={refreshKey} documentFilter={documentFilter} cardFilter={cardFilter} onClearDocument={() => { setDocumentFilter(null); setCardFilter(null); }} onOpenGraph={() => navigate("graph")} />}
        {page === "graph" && <GraphPage refreshKey={refreshKey} onOpenCard={openCard} />}
        {page === "orphans" && <OrphansPage refreshKey={refreshKey} onOpenCard={openCard} />}
        {page === "exports" && <ExportPage />}
        {page === "references" && <ReferencesPage />}
        {page === "admin" && <AdminPage refreshKey={refreshKey} onChanged={refresh} />}
      </main>
    </div>
  );
}
