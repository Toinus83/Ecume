import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AnalysisJob } from "../types";

export function useAnalysisJobs(refreshKey: number) {
  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    let timer: number;
    async function poll() {
      try {
        const result = await api.jobs();
        if (!cancelled) { setJobs(result); setError(""); }
      } catch {
        if (!cancelled) setError("Suivi indisponible : connexion au backend interrompue. Nouvelle tentative en cours.");
      } finally {
        if (!cancelled) timer = window.setTimeout(poll, 2000);
      }
    }
    void poll();
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [refreshKey]);
  return { jobs, error };
}
