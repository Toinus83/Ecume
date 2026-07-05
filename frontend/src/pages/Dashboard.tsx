import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DashboardStats } from "../types";

interface Props {
  refreshKey: number;
}

const labels: Array<[keyof DashboardStats, string]> = [
  ["documents", "Documents"],
  ["effects", "Effets"],
  ["objects", "Objets"],
  ["actions", "Actions"],
  ["conditions", "Conditions"],
  ["tasks", "Tâches"],
  ["links", "Liens"],
  ["orphans", "Orphelins"]
];

export default function Dashboard({ refreshKey }: Props) {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [changes, setChanges] = useState<Array<{ id: string; action: string; entity_type: string; created_at: string; details: Record<string, unknown> }>>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.dashboard(), fetch(`${api.baseUrl}/changes?limit=8`).then((response) => response.json())])
      .then(([nextStats, nextChanges]) => {
        setStats(nextStats);
        setChanges(nextChanges);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Chargement impossible"));
  }, [refreshKey]);

  if (error) return <p className="error">{error}</p>;

  return (
    <section className="page-stack">
      <div className="stats-grid">
        {labels.map(([key, label]) => (
          <div className="stat-card" key={key}>
            <span>{label}</span>
            <strong>{stats ? stats[key] : "..."}</strong>
          </div>
        ))}
      </div>
      <section className="panel">
        <div className="section-title">
          <h2>Derniers changements</h2>
          <span>{changes.length} événements</span>
        </div>
        <div className="timeline">
          {changes.length === 0 ? <p>Aucun changement enregistré.</p> : changes.map((change) => (
            <article key={change.id}>
              <b>{change.entity_type}</b>
              <span>{change.action}</span>
              <time>{new Date(change.created_at).toLocaleString()}</time>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}
