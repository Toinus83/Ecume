import { Check, Eye, GitMerge, Link2, Pencil, Save, Trash2, X } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import type { ExtractedCard, KnowledgeNode, Level } from "../types";
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

export default function EffectCard({ card, allCards, effectNodes, onChanged, onOpenGraph }: Props) {
  const [editing, setEditing] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState({
    theme_label: card.theme_label,
    effect_label: card.main_effect.label,
    effect_description: card.main_effect.description,
    level: card.level,
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
        validation_status: "to_confirm"
      })
    );
    setEditing(false);
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
      `Supprimer l'effet principal "${card.main_effect.label}" de la base ? La carte passera en statut à confirmer.`
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
          <input value={draft.objects} onChange={(event) => setDraft({ ...draft, objects: event.target.value })} />
          <input value={draft.actions} onChange={(event) => setDraft({ ...draft, actions: event.target.value })} />
          <input value={draft.conditions} onChange={(event) => setDraft({ ...draft, conditions: event.target.value })} />
          <input value={draft.tasks} onChange={(event) => setDraft({ ...draft, tasks: event.target.value })} />
        </div>
      ) : (
        <>
          <p className="description">{card.main_effect.description || "Effet proposé à préciser."}</p>
          <div className="tag-layout">
            <TagList title="Objets" items={card.objects} disabled={busy} onDelete={(item, index) => deleteConcept("objects", item, index)} />
            <TagList title="Actions" items={card.actions} disabled={busy} onDelete={(item, index) => deleteConcept("actions", item, index)} />
            <TagList title="Conditions" items={card.conditions} disabled={busy} onDelete={(item, index) => deleteConcept("conditions", item, index)} />
            <TagList title="Tâches" items={card.tasks} disabled={busy} onDelete={(item, index) => deleteConcept("tasks", item, index)} />
          </div>
          {card.suggested_links.length > 0 && (
            <div className="suggestions">
              <span>Rapprochements proposés</span>
              {card.suggested_links.map((link, index) => (
                <p key={`${link.target_existing_node_id}-${index}`}>
                  {link.source_label} · {link.relation_type} · {link.target_label ?? link.target_existing_node_id}
                </p>
              ))}
            </div>
          )}
        </>
      )}

      {sourceOpen && <pre className="source-panel">{card.source_excerpt}</pre>}
      {error && <p className="error">{error}</p>}

      <div className="card-actions">
        <button onClick={() => act(() => api.acceptCard(card.id))} disabled={busy}><Check size={16} />Valider</button>
        <button onClick={() => act(() => api.acceptCard(card.id, true))} disabled={busy}>Orphelin OK</button>
        <button className="danger-button" onClick={deleteMainEffect} disabled={busy}><Trash2 size={16} />Supprimer l’effet</button>
        {editing ? (
          <>
            <button onClick={save} disabled={busy}><Save size={16} />Enregistrer</button>
            <button className="ghost-button" onClick={() => setEditing(false)}><X size={16} />Annuler</button>
          </>
        ) : (
          <button className="ghost-button" onClick={() => setEditing(true)}><Pencil size={16} />Corriger</button>
        )}
        <button className="ghost-button" onClick={() => setSourceOpen(!sourceOpen)}><Eye size={16} />Sources</button>
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
            <option value="">Rattacher à...</option>
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
