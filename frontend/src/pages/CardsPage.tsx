import { useEffect, useState } from "react";
import { api } from "../api/client";
import EffectCard from "../components/EffectCard";
import ValidationControls from "../components/ValidationControls";
import { ContextHelp, ActionError } from "../components/ContextHelp";
import type { ExtractedCard, SourceDocument } from "../types";

interface Props {
  refreshKey: number;
  onOpenGraph: () => void;
  documentFilter: SourceDocument | null;
  cardFilter: string | null;
  onClearDocument: () => void;
}

export default function CardsPage({ refreshKey, onOpenGraph, documentFilter, cardFilter, onClearDocument }: Props) {
  const [cards, setCards] = useState<ExtractedCard[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [localRefresh, setLocalRefresh] = useState(0);
  const [statusFilter, setStatusFilter] = useState(documentFilter || cardFilter ? "all" : "pending");
  const [notice, setNotice] = useState("");
  const [visibleCount, setVisibleCount] = useState(12);
  useEffect(() => { setVisibleCount(12); }, [query, statusFilter, documentFilter?.id, cardFilter]);
  useEffect(() => { setStatusFilter(documentFilter || cardFilter ? "all" : "pending"); }, [documentFilter?.id, cardFilter]);

  useEffect(() => {
    let cancelled = false;
    api.cards()
      .then(nextCards => {
        if (cancelled) return;
        setCards(nextCards);
        setError("");
      })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : "Chargement impossible"); });
    return () => { cancelled = true; };
  }, [refreshKey, localRefresh]);

  const scopedCards = cards.filter(card => (!documentFilter || card.document_id === documentFilter.id) && (!cardFilter || card.id === cardFilter));
  const workCards = scopedCards.filter(card => statusFilter === "all" ||
    (statusFilter === "validated" && ["accepted", "accepted_orphan"].includes(card.status) && card.business_validation_status !== "auto_validated") ||
    (statusFilter === "auto" && ["accepted", "accepted_orphan"].includes(card.status) && card.business_validation_status === "auto_validated") ||
    (statusFilter === "review" && card.status === "to_confirm") ||
    (statusFilter === "rejected" && card.status === "rejected") ||
    (statusFilter === "pending" && card.status === "proposed"));
  const filteredCards = workCards.filter((card) => {
    const needle = query.trim().toLowerCase();
    if (!needle) return true;
    return [
      card.theme_label,
      card.main_effect.label,
      card.main_effect.description,
      card.business_category,
      card.business_justification,
      ...card.objects,
      ...card.actions,
      ...card.conditions,
      ...card.tasks,
      ...(card.extraction_details?.concepts?.map(item => item.label) ?? []),
      ...(card.extraction_details?.rule_details ?? []),
    ]
      .join(" ")
      .toLowerCase()
      .includes(needle);
  });

  return (
    <section className="page-stack">
      <ValidationControls cardIds={filteredCards.map(card => card.id)} onApplied={() => setLocalRefresh(value => value + 1)} />
      <p className="work-summary">{scopedCards.filter(card => card.status === "proposed").length} à traiter · {scopedCards.filter(card => card.status === "to_confirm").length} à revoir · {scopedCards.filter(card => ["accepted", "accepted_orphan"].includes(card.status)).length} validées, dont {scopedCards.filter(card => card.business_validation_status === "auto_validated").length} auto-validées</p>
      <ContextHelp>ECUME affiche d’abord les concepts principaux. Les concepts secondaires sont disponibles dans les détails. Validez ce qui est juste, corrigez ou mettez à revoir le reste. Les anciennes cartes ne sont pas reclassées automatiquement.</ContextHelp>
      {statusFilter === "auto" && filteredCards.length === 0 && <p className="quiet-note">Aucune carte auto-validée dans cette sélection. {scopedCards.filter(card => card.business_confidence == null).length} carte(s) sans score métier numérique ; {scopedCards.filter(card => card.business_validation_status === "validated_by_user" || card.business_validation_status === "corrected_by_user").length} carte(s) validées ou corrigées par un utilisateur. Le changement de mode ne retraite pas les cartes automatiquement.</p>}
      <ActionError error={error} />
      {notice && <p className="success" role="status">{notice}</p>}
      {documentFilter && <div className="document-filter"><span>{documentFilter.filename}</span><button className="ghost-button" onClick={onClearDocument}>Tous les documents</button></div>}
      {cardFilter && <div className="document-filter"><span>Carte source</span><button className="ghost-button" onClick={onClearDocument}>Toutes les cartes</button></div>}
      <div className="section-title">
        <h2>Cartes</h2>
        <span>{filteredCards.length} / {workCards.length}</span>
      </div>
      <div className="segmented" aria-label="Statut des cartes">
        {[["pending", "À traiter"], ["validated", "Validées"], ["auto", "Auto-validées"], ["review", "À revoir"], ["rejected", "Rejetées"], ["all", "Toutes"]].map(([value, label]) =>
          <button key={value} aria-pressed={statusFilter === value} className={statusFilter === value ? "active" : ""} onClick={() => setStatusFilter(value)}>{label}</button>)}
      </div>
      <input
        className="search-input"
        placeholder="Rechercher dans les cartes"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="cards-grid">
        {filteredCards.length === 0 ? (
          <p>Aucune carte dans cette sélection.</p>
        ) : filteredCards.slice(0, visibleCount).map((card) => (
          <EffectCard
            key={card.id}
            card={card}
            allCards={cards}
            onOpenGraph={onOpenGraph}
            onChanged={(updated) => {
              if (updated) {
                setCards(current => current.map(item => item.id === updated.id ? updated : item));
                setNotice(["accepted", "accepted_orphan"].includes(updated.status)
                  ? "Carte validée : elle est visible dans les cartes validées et dans le graphe."
                  : updated.status === "to_confirm" ? "Carte déplacée dans À revoir."
                  : updated.status === "rejected" ? "Carte déplacée dans Rejetées." : "Modification enregistrée.");
              }
              setLocalRefresh((value) => value + 1);
            }}
          />
        ))}
      </div>
      {filteredCards.length > visibleCount && <button className="ghost-button" onClick={() => setVisibleCount(visibleCount + 12)}>Voir les cartes suivantes ({visibleCount} / {filteredCards.length})</button>}
    </section>
  );
}
