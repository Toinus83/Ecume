import { Check, Eye, GitMerge, Link2, Pencil, Save, Trash2, X } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import type { BusinessCategory, ExtractedCard, KnowledgeNode, Level } from "../types";
import { ConfidencePill, LevelPill, StatusPill } from "./StatusPill";
import TagList from "./TagList";

interface Props {
  card: ExtractedCard;
  allCards: ExtractedCard[];
  effectNodes: KnowledgeNode[];
  onChanged: () => void;
  onOpenGraph: () => void;
}

const levels: Level[] = ["strategic", "operational", "tactical", "operator", "unknown"];
const businessCategories: Array<{ value: BusinessCategory; label: string; tooltip: string }> = [
  { value: "resultat_recherche", label: "resultat recherche", tooltip: "Ce que l'on cherche a obtenir : detecter une menace, produire une alerte, garantir une capacite." },
  { value: "objectif_haut_niveau", label: "objectif haut niveau", tooltip: "Finalite generale a atteindre, souvent issue d'une directive ou d'un niveau superieur." },
  { value: "capacite_a_obtenir", label: "capacite a obtenir", tooltip: "Ce que l'organisation doit etre capable de faire pour atteindre un objectif." },
  { value: "action_activite", label: "action / activite", tooltip: "Ce qui est fait pour produire ou contribuer a un resultat." },
  { value: "chose_metier", label: "chose metier manipulee", tooltip: "Element dont on parle ou sur lequel on agit : signal, zone, emetteur, menace." },
  { value: "donnee_manipulee", label: "donnee manipulee", tooltip: "Information utilisee, produite ou echangee : position, frequence, identifiant, statut." },
  { value: "condition_regle_contrainte", label: "condition / regle / contrainte", tooltip: "Situation, critere ou regle qui precise quand une action doit etre realisee." },
  { value: "tache_concrete", label: "tache concrete", tooltip: "Action realisee concretement par un operateur, une equipe ou un systeme." },
  { value: "acteur_organisation", label: "acteur / organisation", tooltip: "Personne, unite, organisme ou systeme qui agit ou porte une responsabilite." },
  { value: "role_tenu", label: "role tenu", tooltip: "Fonction assumee par un acteur dans un contexte donne." },
  { value: "service_rendu", label: "service rendu", tooltip: "Capacite fournie a un utilisateur ou a un metier pour produire un resultat." },
  { value: "service_applicatif", label: "service applicatif", tooltip: "Service fourni par une application." },
  { value: "element_technique", label: "element technique", tooltip: "Element technique utile au fonctionnement." },
  { value: "non_qualifie", label: "non qualifie", tooltip: "ECUME n'a pas encore assez d'indices pour proposer une categorie fiable." }
];

function categoryLabel(value: BusinessCategory) {
  return businessCategories.find((item) => item.value === value)?.label ?? value;
}

function categoryTooltip(value: BusinessCategory) {
  return businessCategories.find((item) => item.value === value)?.tooltip ?? "";
}

export default function EffectCard({ card, allCards, effectNodes, onChanged, onOpenGraph }: Props) {
  const [editing, setEditing] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState({
    theme_label: card.theme_label,
    effect_label: card.main_effect.label,
    effect_description: card.main_effect.description,
    level: card.level,
    business_category: card.business_category,
    business_justification: card.business_justification,
    objects: card.objects.join(", "),
    actions: card.actions.join(", "),
    conditions: card.conditions.join(", "),
    tasks: card.tasks.join(", ")
  });
  const [mergeTarget, setMergeTarget] = useState("");
  const [parentTarget, setParentTarget] = useState("");
  const sortedCards = [...allCards]
    .filter((item) => item.id !== card.id)
    .sort((left, right) => scoreCard(right) - scoreCard(left) || left.main_effect.label.localeCompare(right.main_effect.label, "fr"));
  const sortedEffectNodes = [...effectNodes]
    .filter((node) => node.id !== card.graph_node_ids.effect)
    .sort((left, right) => scoreNode(right) - scoreNode(left) || left.label.localeCompare(right.label, "fr"));

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action impossible");
    } finally {
      setBusy(false);
    }
  }

  function list(value: string) {
    return value.split(",").map((item) => item.trim()).filter(Boolean);
  }

  async function save() {
    await act(() =>
      api.updateCard(card.id, {
        theme_label: draft.theme_label,
        level: draft.level,
        main_effect: {
          label: draft.effect_label,
          description: draft.effect_description,
          level: draft.level,
          confidence: card.main_effect.confidence
        },
        objects: list(draft.objects),
        actions: list(draft.actions),
        conditions: list(draft.conditions),
        tasks: list(draft.tasks),
        status: "to_confirm",
        validation_status: "to_confirm",
        business_category: draft.business_category,
        business_validation_status: "corrected_by_user",
        business_justification: draft.business_justification,
        archimate_mapping_status: "inferred_from_user_answer"
      })
    );
    setEditing(false);
  }

  async function markToReview() {
    await act(() =>
      api.updateCard(card.id, {
        status: "to_confirm",
        validation_status: "to_confirm",
        business_validation_status: "to_review",
        archimate_mapping_status: "to_review"
      })
    );
  }

  async function rejectCard() {
    const ok = window.confirm("Rejeter cette carte ? Elle ne sera plus dans les cartes a traiter.");
    if (!ok) return;
    await act(() =>
      api.updateCard(card.id, {
        status: "rejected",
        validation_status: "rejected",
        business_validation_status: "rejected",
        archimate_mapping_status: "rejected"
      })
    );
  }

  async function attachParent() {
    const effectId = card.graph_node_ids.effect;
    if (!effectId || typeof effectId !== "string" || !parentTarget) return;
    await act(() =>
      api.createEdge({
        source_node_id: effectId,
        target_node_id: parentTarget,
        relation_type: "contribue à",
        label: "contribue à",
        status: "to_confirm",
        confidence: "medium",
        source_ids: [card.document_id],
        metadata: { card_id: card.id, origin: "user" }
      })
    );
  }

  async function deleteConcept(
    field: "objects" | "actions" | "conditions" | "tasks",
    label: string,
    index: number
  ) {
    const nodeIds = card.graph_node_ids[field];
    const nodeId = Array.isArray(nodeIds) ? nodeIds[index] : undefined;
    const ok = window.confirm(`Supprimer le concept "${label}" de la base et de cette carte ?`);
    if (!ok) return;
    await act(async () => {
      if (nodeId) {
        await api.deleteNode(nodeId);
      }
      const nextValues = card[field].filter((_, itemIndex) => itemIndex !== index);
      await api.updateCard(card.id, { [field]: nextValues });
    });
  }

  async function deleteMainEffect() {
    const effectId = card.graph_node_ids.effect;
    if (!effectId || typeof effectId !== "string") return;
    const ok = window.confirm(
      `Supprimer l'effet principal "${card.main_effect.label}" de la base ? La carte passera en statut a confirmer.`
    );
    if (!ok) return;
    await act(async () => {
      await api.deleteNode(effectId);
      await api.updateCard(card.id, { status: "to_confirm", validation_status: "to_confirm" });
    });
  }

  function scoreCard(candidate: ExtractedCard) {
    const suggestedIds = new Set(card.suggested_links.map((link) => link.target_existing_node_id));
    const candidateEffectId = candidate.graph_node_ids.effect;
    if (typeof candidateEffectId === "string" && suggestedIds.has(candidateEffectId)) return 100;
    return commonWords(card.main_effect.label, candidate.main_effect.label);
  }

  function scoreNode(candidate: KnowledgeNode) {
    const direct = card.suggested_links.find((link) => link.target_existing_node_id === candidate.id);
    if (direct?.confidence === "high") return 100;
    if (direct?.confidence === "medium") return 80;
    if (direct) return 60;
    return commonWords(card.main_effect.label, candidate.label);
  }

  function commonWords(left: string, right: string) {
    const leftWords = new Set(left.toLowerCase().split(/\W+/).filter((word) => word.length > 3));
    const rightWords = new Set(right.toLowerCase().split(/\W+/).filter((word) => word.length > 3));
    return [...leftWords].filter((word) => rightWords.has(word)).length;
  }

  return (
    <article className="effect-card">
      <div className="card-head">
        <div>
          {editing ? (
            <input value={draft.theme_label} onChange={(event) => setDraft({ ...draft, theme_label: event.target.value })} />
          ) : (
            <p className="theme">{card.theme_label}</p>
          )}
          {editing ? (
            <input className="effect-input" value={draft.effect_label} onChange={(event) => setDraft({ ...draft, effect_label: event.target.value })} />
          ) : (
            <h2>{card.main_effect.label}</h2>
          )}
        </div>
        <div className="pill-row">
          <StatusPill value={card.status} />
          <LevelPill value={card.level} />
          <ConfidencePill value={card.confidence} />
        </div>
      </div>

      {editing ? (
        <div className="edit-grid">
          <textarea value={draft.effect_description} onChange={(event) => setDraft({ ...draft, effect_description: event.target.value })} />
          <select value={draft.level} onChange={(event) => setDraft({ ...draft, level: event.target.value as Level })}>
            {levels.map((level) => <option key={level} value={level}>{level}</option>)}
          </select>
          <select
            title={categoryTooltip(draft.business_category)}
            value={draft.business_category}
            onChange={(event) => setDraft({ ...draft, business_category: event.target.value as BusinessCategory })}
          >
            {businessCategories.map((category) => <option key={category.value} value={category.value}>{category.label}</option>)}
          </select>
          <textarea value={draft.business_justification} onChange={(event) => setDraft({ ...draft, business_justification: event.target.value })} />
          <input value={draft.objects} onChange={(event) => setDraft({ ...draft, objects: event.target.value })} />
          <input value={draft.actions} onChange={(event) => setDraft({ ...draft, actions: event.target.value })} />
          <input value={draft.conditions} onChange={(event) => setDraft({ ...draft, conditions: event.target.value })} />
          <input value={draft.tasks} onChange={(event) => setDraft({ ...draft, tasks: event.target.value })} />
        </div>
      ) : (
        <>
          <p className="description">{card.main_effect.description || "Effet propose a preciser."}</p>
          <div className="business-summary" title={categoryTooltip(card.business_category)}>
            <span>{categoryLabel(card.business_category)}</span>
            <p>{card.business_justification || "Qualification proposee automatiquement par ECUME."}</p>
          </div>
          <div className="tag-layout">
            <TagList title="Objets" items={card.objects} disabled={busy} onDelete={(item, index) => deleteConcept("objects", item, index)} />
            <TagList title="Actions" items={card.actions} disabled={busy} onDelete={(item, index) => deleteConcept("actions", item, index)} />
            <TagList title="Conditions" items={card.conditions} disabled={busy} onDelete={(item, index) => deleteConcept("conditions", item, index)} />
            <TagList title="Taches" items={card.tasks} disabled={busy} onDelete={(item, index) => deleteConcept("tasks", item, index)} />
          </div>
          {card.suggested_links.length > 0 && (
            <div className="suggestions">
              <span>Rapprochements proposes</span>
              {card.suggested_links.map((link, index) => (
                <p key={`${link.target_existing_node_id}-${index}`}>
                  {link.source_label} · {link.relation_type} · {link.target_label ?? link.target_existing_node_id}
                </p>
              ))}
            </div>
          )}
        </>
      )}

      {advancedOpen && (
        <div className="advanced-panel">
          <span>Mapping candidat</span>
          <p>{card.archimate_mapping?.candidate_layer ?? "Unknown"} · {card.archimate_mapping?.candidate_element ?? "Unknown"}</p>
          <p>{card.archimate_mapping?.reason || "Mapping candidat deduit par ECUME."}</p>
          <p>Confiance : {Math.round((card.archimate_mapping?.confidence ?? 0) * 100)} % · Statut : {card.archimate_mapping_status}</p>
        </div>
      )}
      {sourceOpen && <pre className="source-panel">{card.source_excerpt}</pre>}
      {error && <p className="error">{error}</p>}

      <div className="card-actions">
        <button onClick={() => act(() => api.acceptCard(card.id))} disabled={busy}><Check size={16} />Valider</button>
        <button className="ghost-button" onClick={markToReview} disabled={busy}>A revoir</button>
        <button className="danger-button" onClick={rejectCard} disabled={busy}>Rejeter</button>
        <button onClick={() => act(() => api.acceptCard(card.id, true))} disabled={busy}>Orphelin OK</button>
        <button className="danger-button" onClick={deleteMainEffect} disabled={busy}><Trash2 size={16} />Supprimer l'effet</button>
        {editing ? (
          <>
            <button onClick={save} disabled={busy}><Save size={16} />Enregistrer</button>
            <button className="ghost-button" onClick={() => setEditing(false)}><X size={16} />Annuler</button>
          </>
        ) : (
          <button className="ghost-button" onClick={() => setEditing(true)}><Pencil size={16} />Corriger</button>
        )}
        <button className="ghost-button" onClick={() => setSourceOpen(!sourceOpen)}><Eye size={16} />Sources</button>
        <button className="ghost-button" onClick={() => setAdvancedOpen(!advancedOpen)}>Details</button>
        <button className="ghost-button" onClick={onOpenGraph}><Link2 size={16} />Graphe</button>
      </div>

      <div className="relationship-tools">
        <label>
          <GitMerge size={15} />
          <select value={mergeTarget} onChange={(event) => setMergeTarget(event.target.value)}>
            <option value="">Fusionner avec...</option>
            {sortedCards.map((item) => (
              <option key={item.id} value={item.id}>{item.main_effect.label}</option>
            ))}
          </select>
          <button disabled={!mergeTarget || busy} onClick={() => act(() => api.mergeCard(card.id, mergeTarget))}>Fusionner</button>
        </label>
        <label>
          <Link2 size={15} />
          <select value={parentTarget} onChange={(event) => setParentTarget(event.target.value)}>
            <option value="">Rattacher a...</option>
            {sortedEffectNodes.map((node) => (
              <option key={node.id} value={node.id}>{node.label}</option>
            ))}
          </select>
          <button disabled={!parentTarget || busy} onClick={attachParent}>Rattacher</button>
        </label>
      </div>
    </article>
  );
}
