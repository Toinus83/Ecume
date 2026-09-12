import {
  Check,
  ChevronDown,
  ChevronRight,
  Eye,
  GitMerge,
  Link2,
  Pencil,
  Save,
  Trash2,
  X
} from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import type { BusinessCategory, ExtractedCard, KnowledgeNode, Level, SuggestedLink } from "../types";
import { ConfidencePill, LevelPill, StatusPill } from "./StatusPill";
import TagList from "./TagList";

interface Props {
  card: ExtractedCard;
  allCards: ExtractedCard[];
  effectNodes: KnowledgeNode[];
  onChanged: () => void;
  onOpenGraph: () => void;
}

const levels: Array<{ value: Level; label: string; help: string }> = [
  { value: "strategic", label: "strategique", help: "Finalite generale, orientation ou ambition de haut niveau." },
  { value: "operational", label: "operatif", help: "Effet attendu dans la conduite d'une mission ou d'un processus." },
  { value: "tactical", label: "tactique", help: "Effet local, coordination terrain ou decision proche de l'action." },
  { value: "operator", label: "operateur", help: "Action concrete realisee par une personne, une equipe ou un systeme." },
  { value: "unknown", label: "a preciser", help: "ECUME n'a pas encore assez d'indices." }
];

const businessCategories: Array<{ value: BusinessCategory; label: string; questionLabel: string; tooltip: string }> = [
  {
    value: "resultat_recherche",
    label: "resultat recherche",
    questionLabel: "un resultat recherche",
    tooltip: "Ce que l'on cherche a obtenir : reduire un risque, produire une alerte, garantir une capacite."
  },
  {
    value: "objectif_haut_niveau",
    label: "objectif haut niveau",
    questionLabel: "un objectif haut niveau",
    tooltip: "Finalite generale a atteindre, souvent issue d'une directive ou d'un niveau superieur."
  },
  {
    value: "capacite_a_obtenir",
    label: "capacite a obtenir",
    questionLabel: "une capacite a obtenir",
    tooltip: "Ce que l'organisation doit etre capable de faire pour atteindre un objectif."
  },
  {
    value: "action_activite",
    label: "action / activite",
    questionLabel: "une action ou activite",
    tooltip: "Ce qui est fait pour produire ou contribuer a un resultat."
  },
  {
    value: "chose_metier",
    label: "chose metier",
    questionLabel: "une chose metier",
    tooltip: "Element dont on parle ou sur lequel on agit : signal, zone, emetteur, menace."
  },
  {
    value: "donnee_manipulee",
    label: "donnee manipulee",
    questionLabel: "une donnee manipulee",
    tooltip: "Information utilisee, produite ou echangee : position, frequence, identifiant, statut."
  },
  {
    value: "condition_regle_contrainte",
    label: "condition / regle",
    questionLabel: "une condition, regle ou contrainte",
    tooltip: "Situation, critere ou regle qui precise quand une action doit etre realisee."
  },
  {
    value: "tache_concrete",
    label: "tache concrete",
    questionLabel: "une tache concrete",
    tooltip: "Action realisee concretement par un operateur, une equipe ou un systeme."
  },
  {
    value: "acteur_organisation",
    label: "acteur / organisation",
    questionLabel: "un acteur ou une organisation",
    tooltip: "Personne, unite, organisme ou systeme qui agit ou porte une responsabilite."
  },
  {
    value: "role_tenu",
    label: "role tenu",
    questionLabel: "un role tenu",
    tooltip: "Fonction assumee par un acteur dans un contexte donne."
  },
  {
    value: "service_rendu",
    label: "service rendu",
    questionLabel: "un service rendu",
    tooltip: "Service fourni a un utilisateur ou a un metier pour produire un resultat."
  },
  {
    value: "service_applicatif",
    label: "service applicatif",
    questionLabel: "un service applicatif",
    tooltip: "Service fourni par une application."
  },
  {
    value: "element_technique",
    label: "element technique",
    questionLabel: "un element technique",
    tooltip: "Element technique utile au fonctionnement."
  },
  {
    value: "non_qualifie",
    label: "non qualifie",
    questionLabel: "un element a qualifier",
    tooltip: "ECUME n'a pas encore assez d'indices pour proposer une categorie fiable."
  }
];

function category(value: BusinessCategory) {
  return businessCategories.find((item) => item.value === value) ?? businessCategories[businessCategories.length - 1];
}

function level(value: Level) {
  return levels.find((item) => item.value === value) ?? levels[levels.length - 1];
}

function confidencePercent(value?: number) {
  return Math.round(Math.max(0, Math.min(1, value ?? 0)) * 100);
}

export default function EffectCard({ card, allCards, effectNodes, onChanged, onOpenGraph }: Props) {
  const [editing, setEditing] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [secondaryOpen, setSecondaryOpen] = useState(false);
  const [ignoredSuggestions, setIgnoredSuggestions] = useState<Set<number>>(new Set());
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
  const visibleSuggestions = card.suggested_links
    .map((link, index) => ({ link, index }))
    .filter((item) => !ignoredSuggestions.has(item.index));

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
        archimate_mapping_status: "inferred_from_user_answer",
        ontology_mapping_status: "to_map_later"
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
        archimate_mapping_status: "to_review",
        ontology_mapping_status: card.ontology_mapping_status === "candidate" ? "to_review" : card.ontology_mapping_status
      })
    );
  }

  async function rejectCard() {
    const ok = window.confirm("Rejeter cette carte ? Elle ne sera plus proposee comme concept valide.");
    if (!ok) return;
    await act(() =>
      api.updateCard(card.id, {
        status: "rejected",
        validation_status: "rejected",
        business_validation_status: "rejected",
        archimate_mapping_status: "rejected",
        ontology_mapping_status: "to_map_later"
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
        relation_type: "contribue Ã ",
        label: "contribue Ã ",
        status: "to_confirm",
        confidence: "medium",
        source_ids: [card.document_id],
        metadata: { card_id: card.id, origin: "user" }
      })
    );
  }

  async function acceptSuggestedLink(link: SuggestedLink) {
    const effectId = card.graph_node_ids.effect;
    if (!effectId || typeof effectId !== "string" || !link.target_existing_node_id) return;
    await act(() =>
      api.createEdge({
        source_node_id: effectId,
        target_node_id: link.target_existing_node_id,
        relation_type: link.relation_type,
        label: link.relation_type,
        status: "to_confirm",
        confidence: link.confidence,
        source_ids: [card.document_id],
        metadata: { card_id: card.id, origin: "user", reason: link.reason }
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

  const selectedCategory = category(card.business_category);
  const selectedLevel = level(card.level);

  return (
    <article className="effect-card review-card">
      <div className="card-head">
        <div>
          <p className="theme">{card.theme_label}</p>
          <h2>{card.main_effect.label}</h2>
        </div>
        <div className="pill-row">
          <StatusPill value={card.status} />
          <LevelPill value={card.level} />
          <ConfidencePill value={card.confidence} />
        </div>
      </div>

      {editing ? (
        <div className="correction-panel">
          <section>
            <h3>Comprehension generale</h3>
            <label>
              Theme ou domaine
              <input value={draft.theme_label} onChange={(event) => setDraft({ ...draft, theme_label: event.target.value })} />
            </label>
            <label>
              Concept principal
              <input value={draft.effect_label} onChange={(event) => setDraft({ ...draft, effect_label: event.target.value })} />
            </label>
            <label className="full-row">
              Resume metier
              <textarea value={draft.effect_description} onChange={(event) => setDraft({ ...draft, effect_description: event.target.value })} />
            </label>
          </section>

          <section>
            <h3>Qualification</h3>
            <label>
              Niveau
              <select value={draft.level} onChange={(event) => setDraft({ ...draft, level: event.target.value as Level })}>
                {levels.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <small>{level(draft.level).help}</small>
            </label>
            <label>
              Categorie metier
              <select
                title={category(draft.business_category).tooltip}
                value={draft.business_category}
                onChange={(event) => setDraft({ ...draft, business_category: event.target.value as BusinessCategory })}
              >
                {businessCategories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <small>{category(draft.business_category).tooltip}</small>
            </label>
            <label className="full-row">
              Pourquoi cette qualification
              <textarea value={draft.business_justification} onChange={(event) => setDraft({ ...draft, business_justification: event.target.value })} />
            </label>
          </section>

          <section>
            <h3>Elements extraits</h3>
            <label>
              Ce dont on parle
              <input value={draft.objects} onChange={(event) => setDraft({ ...draft, objects: event.target.value })} placeholder="Elements separes par des virgules" />
            </label>
            <label>
              Ce qui est fait
              <input value={draft.actions} onChange={(event) => setDraft({ ...draft, actions: event.target.value })} placeholder="Actions separees par des virgules" />
            </label>
            <label>
              Dans quel cas
              <input value={draft.conditions} onChange={(event) => setDraft({ ...draft, conditions: event.target.value })} placeholder="Conditions separees par des virgules" />
            </label>
            <label>
              Ce qui est realise concretement
              <input value={draft.tasks} onChange={(event) => setDraft({ ...draft, tasks: event.target.value })} placeholder="Taches separees par des virgules" />
            </label>
          </section>
        </div>
      ) : (
        <>
          <section className="review-section">
            <span>ECUME a compris</span>
            <p>{card.main_effect.description || "Effet propose a preciser."}</p>
          </section>

          <section className="review-section review-decision" title={selectedCategory.tooltip}>
            <span>A valider</span>
            <p>Est-ce bien {selectedCategory.questionLabel} de niveau {selectedLevel.label} ?</p>
            <small>{card.business_justification || "Qualification proposee automatiquement par ECUME."}</small>
          </section>

          <section className="review-section review-impact">
            <span>Ce que cela alimente</span>
            <p>Votre validation aide ECUME a construire progressivement le graphe des usages metier.</p>
          </section>

          <div className="tag-layout readable-tags">
            <TagList title="Ce dont on parle" items={card.objects} disabled={busy} onDelete={(item, index) => deleteConcept("objects", item, index)} />
            <TagList title="Ce qui est fait" items={card.actions} disabled={busy} onDelete={(item, index) => deleteConcept("actions", item, index)} />
            <TagList title="Dans quel cas" items={card.conditions} disabled={busy} onDelete={(item, index) => deleteConcept("conditions", item, index)} />
            <TagList title="Realise concretement" items={card.tasks} disabled={busy} onDelete={(item, index) => deleteConcept("tasks", item, index)} />
          </div>

          {visibleSuggestions.length > 0 && (
            <section className="suggestions readable-suggestions">
              <span>Rapprochements proposes</span>
              {visibleSuggestions.map(({ link, index }) => (
                <div className="suggestion-line" key={`${link.target_existing_node_id}-${index}`}>
                  <p>
                    {link.source_label} <b>{link.relation_type}</b> {link.target_label ?? link.target_existing_node_id}
                  </p>
                  {link.reason && <small>{link.reason}</small>}
                  <div>
                    <button disabled={busy || !link.target_existing_node_id} onClick={() => acceptSuggestedLink(link)}>Accepter</button>
                    <button className="ghost-button" disabled={busy} onClick={() => setIgnoredSuggestions(new Set(ignoredSuggestions).add(index))}>Ignorer</button>
                    <button className="ghost-button" disabled={busy} onClick={markToReview}>A revoir</button>
                  </div>
                </div>
              ))}
            </section>
          )}
        </>
      )}

      {advancedOpen && (
        <div className="advanced-panel">
          <section>
            <span>Traduction architecture</span>
            <dl>
              <dt>Reference</dt>
              <dd>{card.archimate_mapping?.framework ?? "ArchiMate"} {card.archimate_mapping?.version ?? "3.2"}</dd>
              <dt>Couche proposee</dt>
              <dd>{card.archimate_mapping?.candidate_layer ?? "A preciser"}</dd>
              <dt>Element propose</dt>
              <dd>{card.archimate_mapping?.candidate_element ?? "A preciser"}</dd>
              <dt>Statut</dt>
              <dd>{card.archimate_mapping_status}</dd>
              <dt>Confiance</dt>
              <dd>{confidencePercent(card.archimate_mapping?.confidence)} %</dd>
              <dt>Pourquoi</dt>
              <dd>{card.archimate_mapping?.reason || "Mapping candidat deduit par ECUME."}</dd>
            </dl>
          </section>
          <section>
            <span>Referentiels / ontologies</span>
            <dl>
              <dt>Statut</dt>
              <dd>{card.ontology_mapping_status}</dd>
              <dt>Correspondances</dt>
              <dd>Aucune pour l'instant.</dd>
            </dl>
            <p>Le rapprochement avec les referentiels sera disponible dans un prochain lot.</p>
          </section>
        </div>
      )}
      {sourceOpen && <pre className="source-panel">{card.source_excerpt}</pre>}
      {error && <p className="error">{error}</p>}

      <div className="card-actions primary-actions">
        {editing ? (
          <>
            <button onClick={save} disabled={busy}><Save size={16} />Enregistrer les corrections</button>
            <button className="ghost-button" onClick={() => setEditing(false)}><X size={16} />Annuler</button>
          </>
        ) : (
          <>
            <button onClick={() => act(() => api.acceptCard(card.id))} disabled={busy}><Check size={16} />Valider la proposition</button>
            <button className="ghost-button" onClick={() => setEditing(true)}><Pencil size={16} />Corriger</button>
            <button className="ghost-button" onClick={markToReview} disabled={busy}>A revoir</button>
          </>
        )}
        <button className="ghost-button" onClick={() => setSecondaryOpen(!secondaryOpen)}>
          {secondaryOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          Actions
        </button>
      </div>

      {secondaryOpen && (
        <>
          <div className="card-actions secondary-actions">
            <button className="ghost-button" onClick={() => setSourceOpen(!sourceOpen)}><Eye size={16} />Voir sources</button>
            <button className="ghost-button" onClick={onOpenGraph}><Link2 size={16} />Voir graphe</button>
            <button className="ghost-button" onClick={() => setAdvancedOpen(!advancedOpen)}>Details avances</button>
            <button onClick={() => act(() => api.acceptCard(card.id, true))} disabled={busy}>Orphelin OK</button>
            <button className="danger-button" onClick={rejectCard} disabled={busy}>Rejeter</button>
            <button className="danger-button" onClick={deleteMainEffect} disabled={busy}><Trash2 size={16} />Supprimer</button>
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
        </>
      )}
    </article>
  );
}
