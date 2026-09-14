import {
  Check,
  Eye,
  GitMerge,
  Link2,
  Pencil,
  Save,
  Trash2,
  X,
  MoreHorizontal
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { BusinessCategory, ExtractedCard, KnowledgeNode, Level, SuggestedLink } from "../types";
import { LevelPill, StatusPill } from "./StatusPill";
import TagList from "./TagList";
import SuggestionRepair from "./SuggestionRepair";
import ConceptSearch from "./ConceptSearch";
import { ActionError, Hint } from "./ContextHelp";
import CardConcepts from "./CardConcepts";
import EchoMappings from "./EchoMappings";

interface Props {
  card: ExtractedCard;
  allCards: ExtractedCard[];
  onChanged: (updated?: ExtractedCard) => void;
  onOpenGraph: () => void;
}

export const levels: Array<{ value: Level; label: string; help: string }> = [
  { value: "strategic", label: "strategique", help: "Finalite generale, orientation ou ambition de haut niveau." },
  { value: "operational", label: "operatif", help: "Effet attendu dans la conduite d'une mission ou d'un processus." },
  { value: "tactical", label: "tactique", help: "Effet local, coordination terrain ou decision proche de l'action." },
  { value: "operator", label: "operateur", help: "Action concrete realisee par une personne, une equipe ou un systeme." },
  { value: "unknown", label: "a preciser", help: "ECUME n'a pas encore assez d'indices." }
];

export const businessCategories: Array<{ value: BusinessCategory; label: string; questionLabel: string; tooltip: string }> = [
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

export default function EffectCard({ card, allCards, onChanged, onOpenGraph }: Props) {
  const [editing, setEditing] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [secondaryOpen, setSecondaryOpen] = useState(false);
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
  useEffect(() => {
    if (!editing) setDraft({theme_label: card.theme_label, effect_label: card.main_effect.label,
      effect_description: card.main_effect.description, level: card.level, business_category: card.business_category,
      business_justification: card.business_justification, objects: card.objects.join(", "), actions: card.actions.join(", "),
      conditions: card.conditions.join(", "), tasks: card.tasks.join(", ")});
  }, [card.updated_at, editing]);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [parentTarget, setParentTarget] = useState("");
  const [parentNode, setParentNode] = useState<KnowledgeNode | null>(null);
  const [mergeQuery, setMergeQuery] = useState("");
  const [linksOpen, setLinksOpen] = useState(false);
  const [linkFilter, setLinkFilter] = useState("important");
  const [linkLimit, setLinkLimit] = useState(8);
  const [repairId, setRepairId] = useState<string | null>(null);
  const [suggestionNotice, setSuggestionNotice] = useState("");
  const sortedCards = [...allCards]
    .filter((item) => item.id !== card.id)
    .sort((left, right) => scoreCard(right) - scoreCard(left) || left.main_effect.label.localeCompare(right.main_effect.label, "fr"));
  function linkGroup(link: SuggestedLink) {
    if (link.status === "accepted") return "accepted";
    if (["ignored", "rejected"].includes(link.status)) return "ignored";
    if (!link.can_accept) return "incomplete";
    return typeof link.business_confidence === "number" && link.business_confidence >= .9 && link.status === "proposed" ? "supported" : "review";
  }
  const groups = [["supported", "Fiables (estimation)"], ["review", "À vérifier"], ["incomplete", "Incomplets"], ["ignored", "Ignorés / rejetés"], ["accepted", "Acceptés"]];
  const principalIds = new Set([card.graph_node_ids.effect, ...(card.extraction_details?.concepts ?? []).filter(item => item.active && item.importance === "principal").map(item => item.node_id)]);
  const important = card.suggested_links.filter(link => link.can_accept && link.status === "proposed" && principalIds.has(link.source_node_id ?? "") &&
    (typeof link.business_confidence === "number" ? link.business_confidence >= .8 : !card.extraction_details?.managed && link.confidence === "high"))
    .sort((a,b) => (b.business_confidence ?? 0) - (a.business_confidence ?? 0)).slice(0,3);
  const importantIds = new Set(important.map(item => item.id));
  const problems = card.suggested_links.filter(link => linkGroup(link) === "incomplete").length;
  const otherCount = card.suggested_links.length - important.length - problems;
  const visibleSuggestions = card.suggested_links.filter(link => linkFilter === "important" ? importantIds.has(link.id) :
    linkFilter === "others" ? !importantIds.has(link.id) && linkGroup(link) !== "incomplete" : linkGroup(link) === linkFilter)
    .sort((a,b) => groups.findIndex(([key]) => key === linkGroup(a)) - groups.findIndex(([key]) => key === linkGroup(b)) || (b.business_confidence ?? -1) - (a.business_confidence ?? -1));


  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      const result = await action();
      onChanged(result && typeof result === "object" && "main_effect" in result ? result as ExtractedCard : undefined);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action impossible");
      return false;
    } finally {
      setBusy(false);
    }
  }

  function list(value: string) {
    return value.split(",").map((item) => item.trim()).filter(Boolean);
  }

  async function save() {
    const saved = await act(() =>
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
    if (saved) setEditing(false);
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
        relation_type: "contribue à",
        label: "contribue à",
        status: "to_confirm",
        confidence: "medium",
        source_ids: [card.document_id],
        metadata: { card_id: card.id, origin: "user" }
      })
    );
  }

  async function acceptSuggestedLink(link: SuggestedLink) {
    setSuggestionNotice("");
    await act(async () => {
      const result = await api.decideSuggestion(card.id, link.id, "accepted");
      setSuggestionNotice(result.status === "accepted" ? "Rapprochement accepté." : result.invalid_reason || "Rapprochement à revoir. Actualisez la carte.");
      return result;
    });
  }

  async function deleteConcept(
    field: "objects" | "actions" | "conditions" | "tasks",
    label: string,
    index: number
  ) {
    const nodeIds = card.graph_node_ids[field];
    const nodeId = Array.isArray(nodeIds) ? nodeIds[index] : undefined;
    const ok = window.confirm(`Retirer "${label}" de cette carte ? Les autres cartes seront conservees.`);
    if (!ok) return;
    if (nodeId) await act(() => api.detachConcept(card.id, nodeId));
  }

  async function deleteMainEffect() {
    const ok = window.confirm(
      `Supprimer la carte "${card.main_effect.label}" ? Les concepts utilises ailleurs seront conserves.`
    );
    if (!ok) return;
    await act(() => api.deleteCard(card.id));
  }

  function scoreCard(candidate: ExtractedCard) {
    const suggestedIds = new Set(card.suggested_links.map((link) => link.target_existing_node_id));
    const candidateEffectId = candidate.graph_node_ids.effect;
    if (typeof candidateEffectId === "string" && suggestedIds.has(candidateEffectId)) return 100;
    return commonWords(card.main_effect.label, candidate.main_effect.label);
  }

  function commonWords(left: string, right: string) {
    const leftWords = new Set(left.toLowerCase().split(/\W+/).filter((word) => word.length > 3));
    const rightWords = new Set(right.toLowerCase().split(/\W+/).filter((word) => word.length > 3));
    return [...leftWords].filter((word) => rightWords.has(word)).length;
  }

  const selectedCategory = category(card.business_category);
  const selectedLevel = level(card.level);
  const validated = ["accepted", "accepted_orphan"].includes(card.status);

  const primaryActions = (<div className="card-actions primary-actions">
        {editing ? (
          <>
            <button onClick={save} disabled={busy}><Save size={16} />Enregistrer les corrections</button>
            <button className="ghost-button" disabled={busy} onClick={() => setEditing(false)}><X size={16} />Annuler</button>
          </>
        ) : (
          <>
            {!validated && <button onClick={() => act(() => api.acceptCard(card.id))} disabled={busy}><Check size={16} />Valider</button>}
            <button className="ghost-button" disabled={busy} onClick={() => setEditing(true)}><Pencil size={16} />{validated ? "Modifier" : "Corriger"}</button>
            <button className="ghost-button" onClick={markToReview} disabled={busy}>À revoir</button>
          </>
        )}
        <button className="ghost-button icon-button" title="Autres actions" aria-label="Autres actions" aria-expanded={secondaryOpen} onClick={() => setSecondaryOpen(!secondaryOpen)}>
          <MoreHorizontal size={16} />
        </button>
      </div>);

  return (
    <article className="effect-card review-card">
      <div className="card-head">
        <div>
          <p className="theme">{card.theme_label}</p>
          <h2>{card.main_effect.label}</h2>
        </div>
        <div className="pill-row">
          {card.business_validation_status === "auto_validated" ? <span className="pill status-accepted" title="Proposition suffisamment fiable selon le mode choisi.">Auto-validée</span> : <StatusPill value={card.status} />}
          <LevelPill value={card.level} />
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
            <p className={summaryOpen || card.main_effect.description.length <= 200 ? "" : "card-summary-clamped"}>{card.main_effect.description || "Effet propose a preciser."}</p>
            {card.main_effect.description.length > 200 && <button className="ghost-button summary-toggle" onClick={() => setSummaryOpen(!summaryOpen)}>{summaryOpen ? "Réduire la synthèse" : "Lire la synthèse complète"}</button>}
          </section>

          <CardConcepts card={card} busy={busy} onDecision={(id, action) => void act(() => api.decideConcept(card.id, id, action))} />

          <section className="review-section review-decision" title={selectedCategory.tooltip}>
            <span>{["accepted", "accepted_orphan"].includes(card.status) ? "Qualification validée" : "À valider"}</span>
            <p>{["accepted", "accepted_orphan"].includes(card.status) ? `${selectedCategory.label} · ${selectedLevel.label}` : `Est-ce bien ${selectedCategory.questionLabel} de niveau ${selectedLevel.label} ?`}</p>

          </section>

          {primaryActions}
          {!card.extraction_details?.managed && <details className="card-disclosure"><summary>Éléments associés ({card.objects.length + card.actions.length + card.conditions.length + card.tasks.length})</summary>
          <div className="tag-layout readable-tags">
            <TagList title="Ce dont on parle" items={card.objects} disabled={busy} onDelete={validated ? undefined : (item, index) => deleteConcept("objects", item, index)} />
            <TagList title="Ce qui est fait" items={card.actions} disabled={busy} onDelete={validated ? undefined : (item, index) => deleteConcept("actions", item, index)} />
            <TagList title="Dans quel cas" items={card.conditions} disabled={busy} onDelete={validated ? undefined : (item, index) => deleteConcept("conditions", item, index)} />
            <TagList title="Realise concretement" items={card.tasks} disabled={busy} onDelete={validated ? undefined : (item, index) => deleteConcept("tasks", item, index)} />
          </div>

          </details>}
          <CardConcepts details card={card} busy={busy} onDecision={(id, action) => void act(() => api.decideConcept(card.id, id, action))} />
          {validated && <EchoMappings nodes={[{id:typeof card.graph_node_ids.effect === "string" ? card.graph_node_ids.effect : "",label:card.main_effect.label},
            ...(["objects","actions","conditions","tasks"] as const).flatMap(role=>{
              const ids = card.graph_node_ids[role];
              return card[role].map((label,index)=>({id:Array.isArray(ids) ? ids[index] : "",label}));
            })].filter((node,index,all)=>!!node.id && all.findIndex(other=>other.id===node.id)===index)} />}
          {card.suggested_links.length > 0 && <section className="suggestions-summary">
            <div className="section-title"><span>{important.length} rapprochements importants · {otherCount} autres masqués <Hint label="Rapprochement">Les liens complets les plus utiles sont présentés en premier.</Hint></span>
              {important.length > 0 && <button className="ghost-button" aria-expanded={linksOpen && linkFilter === "important"} onClick={() => { setLinksOpen(!linksOpen || linkFilter !== "important"); setLinkFilter("important"); setRepairId(null); }}>Examiner les rapprochements</button>}</div>
            <div className="button-row related-disclosures">{otherCount > 0 && <button className="ghost-button" onClick={() => { setLinksOpen(!linksOpen || linkFilter !== "others"); setLinkFilter("others"); setLinkLimit(8); setRepairId(null); }}>Voir les autres</button>}
              {problems > 0 && <button className="ghost-button" onClick={() => { setLinksOpen(!linksOpen || linkFilter !== "incomplete"); setLinkFilter("incomplete"); setLinkLimit(8); setRepairId(null); }}>À réparer si nécessaire ({problems})</button>}</div>
            {linksOpen && <div className="suggestions-panel">
              {linkFilter === "incomplete" && <p className="quiet-note">ECUME a détecté une idée de lien, mais il manque un concept exploitable ou une relation à préciser.</p>}
              <label>Afficher<select value={linkFilter} onChange={e => { setLinkFilter(e.target.value); setLinkLimit(8); setRepairId(null); }}>
                <option value="important">Rapprochements importants ({important.length})</option><option value="others">Autres rapprochements possibles ({otherCount})</option>{groups.map(([key,label]) => <option key={key} value={key}>{label} ({card.suggested_links.filter(link => linkGroup(link) === key).length})</option>)}
              </select></label>
              {suggestionNotice && <p role="status">{suggestionNotice}</p>}
              {visibleSuggestions.slice(0,linkLimit).map(link => <div className="suggestion-line" key={link.id}>
                <small>{groups.find(([key]) => key === linkGroup(link))?.[1]}</small>
                <p><strong>{link.source_label || "Concept source à retrouver"}</strong> {link.relation_type} <strong>{link.target_label || "Concept cible à retrouver"}</strong></p>
                {link.reason && <p className="quiet-note">{link.reason.length > 240 ? link.reason.slice(0,240) + "…" : link.reason}</p>}
                {typeof link.business_confidence === "number" && <p className="quiet-note">Confiance estimée : {Math.round(link.business_confidence * 100)} % <Hint label="Score métier">Estimation sur la compréhension métier. Ce n’est pas une preuve.</Hint></p>}
                {["accepted", "ignored"].includes(linkGroup(link)) ? <p className="quiet-note">{{accepted:"Accepté",ignored:"Ignoré",rejected:"Rejeté"}[link.status as "accepted"]}</p> : <>
                  {!link.can_accept && <p className="quiet-note">{link.invalid_reason || "Lien incomplet : un concept doit être retrouvé."}</p>}
                  <div className="button-row">
                    {link.can_accept && <button disabled={busy} onClick={() => acceptSuggestedLink(link)}>Accepter</button>}
                    <button className="ghost-button" disabled={busy} onClick={() => setRepairId(repairId === link.id ? null : link.id)}><Pencil size={14} />{link.can_accept ? "Modifier" : link.source_node_id ? "Choisir une cible" : "Corriger le lien"}</button>
                    <button className="ghost-button" disabled={busy} onClick={() => act(() => api.decideSuggestion(card.id, link.id, "ignored"))}>Ignorer</button>
                    {!link.can_accept && <button className="ghost-button" disabled={busy} onClick={() => act(() => api.decideSuggestion(card.id, link.id, "to_review"))}>À revoir</button>}
                  </div>
                  {repairId === link.id && <SuggestionRepair card={card} link={link} onCancel={() => setRepairId(null)} onDone={() => { setRepairId(null); setSuggestionNotice("Lien corrigé, en attente d’acceptation."); onChanged(); }} />}
                </>}
              </div>)}
              {visibleSuggestions.length > linkLimit && <button className="ghost-button" onClick={() => setLinkLimit(linkLimit + 8)}>Voir plus de rapprochements</button>}
            </div>}
          </section>}
        </>
      )}

      {editing && primaryActions}
      {advancedOpen && (
        <div className="advanced-panel">
          {card.business_justification && <section><h4>Pourquoi cette qualification ?</h4><p>{card.business_justification}</p></section>}
          <section><h4>Auto-validation</h4><p>{card.business_confidence == null ? "Aucun score métier numérique : cette carte ne peut pas être auto-validée à partir de ses données actuelles." : `Score métier estimé : ${Math.round(card.business_confidence * 100)} %.`}</p>
            <p>{card.validation_decision?.origin === "user" ? "Décision humaine conservée." : card.validation_decision?.reason === "strict_mode" ? "Analyse en mode Strict : validation manuelle requise." : card.validation_decision?.reason === "insufficient_score" ? "Score inférieur au seuil d'auto-validation utilisé." : !card.validation_decision?.origin ? "Aucune décision automatique enregistrée pour cette carte historique." : "Décision automatique enregistrée avec les réglages de l'analyse."}</p>
            {Array.isArray(card.validation_decision?.blockers) && card.validation_decision.blockers.length > 0 && <p>Points à vérifier : {card.validation_decision.blockers.join(" ; ")}</p>}
          </section>
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
      <ActionError error={error} />

      {secondaryOpen && (
        <>
          <div className="card-actions secondary-actions">
            <button className="ghost-button" onClick={() => setSourceOpen(!sourceOpen)}><Eye size={16} />Voir sources</button>
            <button className="ghost-button" onClick={onOpenGraph}><Link2 size={16} />Voir graphe</button>
            <button className="ghost-button" onClick={() => setAdvancedOpen(!advancedOpen)}>Details avances</button>
            <button onClick={() => act(() => api.acceptCard(card.id, true))} disabled={busy}>Accepter sans rattachement</button>
            <button className="danger-button" onClick={rejectCard} disabled={busy}>Rejeter</button>
            <button className="danger-button" onClick={deleteMainEffect} disabled={busy}><Trash2 size={16} />Supprimer</button>
          </div>

          <div className="relationship-tools">
            <label>
              <GitMerge size={15} />
              <input aria-label="Rechercher une carte à fusionner" placeholder="Rechercher une carte" value={mergeQuery} onChange={e => { setMergeQuery(e.target.value); setMergeTarget(""); }} />
              <select value={mergeTarget} onChange={(event) => setMergeTarget(event.target.value)}>
                <option value="">Fusionner avec...</option>
                {sortedCards.filter(item => mergeQuery.trim().length >= 2 && item.main_effect.label.toLocaleLowerCase("fr").includes(mergeQuery.toLocaleLowerCase("fr"))).slice(0,8).map((item) => (
                  <option key={item.id} value={item.id}>{item.main_effect.label}</option>
                ))}
              </select>
              <button disabled={!mergeTarget || busy} onClick={() => act(() => api.mergeCard(card.id, mergeTarget))}>Fusionner</button>
            </label>
            <div className="parent-search"><strong>Rattacher à un concept</strong>
              <ConceptSearch sourceId={String(card.graph_node_ids.effect || "")} documentId={card.document_id} nodeType="effect" initialScope="validated" value={parentNode} onSelect={node => { setParentNode(node); setParentTarget(node?.id ?? ""); }} />
              <button disabled={!parentTarget || busy} onClick={attachParent}>Rattacher</button>
            </div>
          </div>
        </>
      )}
    </article>
  );
}
