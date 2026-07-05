import { useEffect, useState } from "react";
import { api } from "../api/client";
import { StatusPill } from "../components/StatusPill";
import type { KnowledgeNode } from "../types";

interface Props {
  refreshKey: number;
}

export default function OrphansPage({ refreshKey }: Props) {
  const [orphans, setOrphans] = useState<KnowledgeNode[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.orphans().then(setOrphans).catch((err) => setError(err instanceof Error ? err.message : "Chargement impossible"));
  }, [refreshKey]);

  const filteredOrphans = orphans.filter((node) => {
    const needle = query.trim().toLowerCase();
    if (!needle) return true;
    return [node.label, node.description, node.type, node.level, node.status, node.orphan_kind ?? ""]
      .join(" ")
      .toLowerCase()
      .includes(needle);
  });

  return (
    <section className="page-stack">
      <div className="section-title">
        <h2>Orphelins</h2>
        <span>{filteredOrphans.length} / {orphans.length}</span>
      </div>
      <input
        className="search-input"
        placeholder="Rechercher dans les orphelins"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      {error && <p className="error">{error}</p>}
      <div className="orphan-list">
        {filteredOrphans.length === 0 ? <p>Aucun orphelin détecté.</p> : filteredOrphans.map((node) => (
          <article key={node.id}>
            <div>
              <span>{node.orphan_kind ?? "orphelin"}</span>
              <h3>{node.label}</h3>
              <p>{node.type} · {node.level}</p>
            </div>
            <StatusPill value={node.status} />
          </article>
        ))}
      </div>
    </section>
  );
}
