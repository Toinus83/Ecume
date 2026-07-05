import { useEffect, useState } from "react";
import { api } from "../api/client";
import EffectCard from "../components/EffectCard";
import type { ExtractedCard, KnowledgeNode } from "../types";

interface Props {
  refreshKey: number;
  onOpenGraph: () => void;
}

export default function CardsPage({ refreshKey, onOpenGraph }: Props) {
  const [cards, setCards] = useState<ExtractedCard[]>([]);
  const [effectNodes, setEffectNodes] = useState<KnowledgeNode[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [localRefresh, setLocalRefresh] = useState(0);

  useEffect(() => {
    Promise.all([api.cards(), api.graph("effects")])
      .then(([nextCards, graph]) => {
        setCards(nextCards);
        setEffectNodes(graph.nodes);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Chargement impossible"));
  }, [refreshKey, localRefresh]);

  const workCards = cards.filter((card) => !["accepted", "accepted_orphan"].includes(card.status));
  const filteredCards = workCards.filter((card) => {
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
    ]
      .join(" ")
      .toLowerCase()
      .includes(needle);
  });

  return (
    <section className="page-stack">
      {error && <p className="error">{error}</p>}
      <div className="section-title">
        <h2>Cartes à traiter</h2>
        <span>{filteredCards.length} / {workCards.length}</span>
      </div>
      <input
        className="search-input"
        placeholder="Rechercher dans les cartes à traiter"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="cards-grid">
        {filteredCards.length === 0 ? (
          <p>Aucune carte à traiter.</p>
        ) : filteredCards.map((card) => (
          <EffectCard
            key={card.id}
            card={card}
            allCards={workCards}
            effectNodes={effectNodes}
            onOpenGraph={onOpenGraph}
            onChanged={() => setLocalRefresh((value) => value + 1)}
          />
        ))}
      </div>
    </section>
  );
}
