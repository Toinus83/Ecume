import { useEffect, useState } from "react";
import { api } from "../api/client";
import KnowledgeGraph from "../graph/KnowledgeGraph";
import EffectCard from "../components/EffectCard";
import type { ExtractedCard, GraphPayload, KnowledgeNode } from "../types";

interface Props {
  refreshKey: number;
}

const filters = [
  ["all", "Tout"],
  ["effects", "Effets"],
  ["effects_objects", "Effets + objets"],
  ["effects_actions", "Effets + actions"],
  ["orphans", "Orphelins"]
] as const;

export default function GraphPage({ refreshKey }: Props) {
  const [view, setView] = useState<"graph" | "validated">("graph");
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState<KnowledgeNode | null>(null);
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [cards, setCards] = useState<ExtractedCard[]>([]);
  const [query, setQuery] = useState("");
  const [editCardId, setEditCardId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [localRefresh, setLocalRefresh] = useState(0);

  useEffect(() => {
    Promise.all([api.graph(filter, selected?.id), api.cards()])
      .then(([nextGraph, nextCards]) => {
        setGraph(nextGraph);
        setCards(nextCards);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Graphe indisponible"));
  }, [filter, refreshKey, selected?.id, localRefresh]);

  const acceptedCards = cards.filter((card) => ["accepted", "accepted_orphan"].includes(card.status));
  const filteredCards = acceptedCards.filter((card) => {
    const needle = query.trim().toLowerCase();
    if (!needle) return true;
    return [
      card.theme_label,
      card.main_effect.label,
      card.main_effect.description,
      ...card.objects,
      ...card.actions,
      ...card.conditions,
      ...card.tasks,
    ].join(" ").toLowerCase().includes(needle);
  });
  const effectNodes = graph?.nodes.filter((node) => node.type === "effect") ?? [];
  const relatedEdges = selected && graph
    ? graph.edges.filter((edge) => edge.source_node_id === selected.id || edge.target_node_id === selected.id)
    : [];
  const nodeLabel = (nodeId: string) => graph?.nodes.find((node) => node.id === nodeId)?.label ?? nodeId;

  async function deleteRelation(edgeId: string) {
    const ok = window.confirm("Supprimer ce lien du graphe ?");
    if (!ok) return;
    try {
      await api.deleteEdge(edgeId);
      setLocalRefresh((value) => value + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Suppression du lien impossible");
    }
  }

  return (
    <section className="graph-page">
      <div className="graph-toolbar">
        <div className="segmented">
          <button className={view === "graph" ? "active" : ""} onClick={() => setView("graph")}>Graphe</button>
          <button className={view === "validated" ? "active" : ""} onClick={() => setView("validated")}>Cartes validées</button>
        </div>
        {view === "graph" && (
          <div className="segmented">
            {filters.map(([id, label]) => (
              <button key={id} className={filter === id ? "active" : ""} onClick={() => { setFilter(id); setSelected(null); }}>
                {label}
              </button>
            ))}
          </div>
        )}
        {selected && <button className="ghost-button" onClick={() => setSelected(null)}>Afficher le graphe complet</button>}
      </div>
      <input
        className="search-input"
        placeholder={view === "graph" ? "Rechercher dans la fiche sélectionnée ou les cartes validées" : "Rechercher dans les cartes validées"}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      {error && <p className="error">{error}</p>}

      {view === "graph" ? (
        <div className="graph-layout">
          <KnowledgeGraph graph={graph} onSelect={setSelected} />
          <aside className="detail-panel">
            {selected ? (
              <>
                <span>{selected.type}</span>
                <h2>{selected.label}</h2>
                <p>{selected.description || "Aucune description."}</p>
                <dl>
                  <dt>Niveau</dt><dd>{selected.level}</dd>
                  <dt>Statut</dt><dd>{selected.status}</dd>
                  <dt>Confiance</dt><dd>{selected.confidence}</dd>
                </dl>
                <div className="link-list">
                  <h3>Liens</h3>
                  {relatedEdges.length === 0 ? <p>Aucun lien.</p> : relatedEdges.map((edge) => (
                    <article key={edge.id}>
                      <p>{nodeLabel(edge.source_node_id)} · {edge.relation_type} · {nodeLabel(edge.target_node_id)}</p>
                      <button className="danger-button" onClick={() => deleteRelation(edge.id)}>Supprimer</button>
                    </article>
                  ))}
                </div>
                <button className="ghost-button" onClick={() => setView("validated")}>Modifier via les cartes</button>
              </>
            ) : (
              <p>Sélectionne un nœud pour voir sa fiche.</p>
            )}
          </aside>
        </div>
      ) : (
        <div className="validated-layout">
          {filteredCards.length === 0 ? <p>Aucune carte validée.</p> : filteredCards.map((card) => (
            editCardId === card.id ? (
              <EffectCard
                key={card.id}
                card={card}
                allCards={acceptedCards}
                effectNodes={effectNodes}
                onOpenGraph={() => setView("graph")}
                onChanged={() => {
                  setLocalRefresh((value) => value + 1);
                  setEditCardId(null);
                }}
              />
            ) : (
              <article className="validated-card" key={card.id}>
                <div>
                  <span>{card.level}</span>
                  <h2>{card.main_effect.label}</h2>
                  <p>{card.main_effect.description || card.theme_label}</p>
                </div>
                <button className="ghost-button" onClick={() => setEditCardId(card.id)}>Modifier</button>
              </article>
            )
          ))}
        </div>
      )}
    </section>
  );
}
