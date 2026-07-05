import { useEffect, useMemo, useState } from "react";
import { BarChart3, Download, FileUp, GitFork, Layers3, Network, Settings, Sparkles } from "lucide-react";
import { api } from "./api/client";
import Dashboard from "./pages/Dashboard";
import ImportPage from "./pages/ImportPage";
import CardsPage from "./pages/CardsPage";
import GraphPage from "./pages/GraphPage";
import OrphansPage from "./pages/OrphansPage";
import ExportPage from "./pages/ExportPage";
import AdminPage from "./pages/AdminPage";
import type { AnalysisJob } from "./types";

type Page = "dashboard" | "import" | "cards" | "graph" | "orphans" | "exports" | "admin";

const nav = [
  { id: "dashboard", label: "Tableau", icon: BarChart3 },
  { id: "import", label: "Import", icon: FileUp },
  { id: "cards", label: "Cartes", icon: Layers3 },
  { id: "graph", label: "Graphe", icon: Network },
  { id: "orphans", label: "Orphelins", icon: GitFork },
  { id: "exports", label: "Exports", icon: Download },
  { id: "admin", label: "Admin", icon: Settings }
] as const;

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [refreshKey, setRefreshKey] = useState(0);
  const [runningJob, setRunningJob] = useState<AnalysisJob | null>(null);

  useEffect(() => {
    const fromHash = window.location.hash.replace("#", "") as Page;
    if (nav.some((item) => item.id === fromHash)) setPage(fromHash);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function refreshJobs() {
      try {
        const jobs = await api.jobs();
        if (cancelled) return;
        const active = jobs.find((job) => job.status === "running" || job.status === "queued") ?? null;
        setRunningJob(active);
      } catch {
        if (!cancelled) setRunningJob(null);
      }
    }
    refreshJobs();
    const id = window.setInterval(refreshJobs, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [refreshKey]);

  const activeTitle = useMemo(() => nav.find((item) => item.id === page)?.label ?? "ECUME", [page]);

  function navigate(next: Page) {
    setPage(next);
    window.location.hash = next;
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
            {runningJob && (
              <div className="top-job">
                <span style={{ width: `${Math.max(0, Math.min(100, runningJob.progress))}%` }} />
                <p>{runningJob.message} ({runningJob.progress}%)</p>
              </div>
            )}
          </div>
          <button className="ghost-button" onClick={refresh}>Actualiser</button>
        </header>

        {page === "dashboard" && <Dashboard refreshKey={refreshKey} />}
        {page === "import" && <ImportPage onAnalyzed={() => { refresh(); navigate("cards"); }} />}
        {page === "cards" && <CardsPage refreshKey={refreshKey} onOpenGraph={() => navigate("graph")} />}
        {page === "graph" && <GraphPage refreshKey={refreshKey} />}
        {page === "orphans" && <OrphansPage refreshKey={refreshKey} />}
        {page === "exports" && <ExportPage />}
        {page === "admin" && <AdminPage refreshKey={refreshKey} onChanged={refresh} />}
      </main>
    </div>
  );
}
