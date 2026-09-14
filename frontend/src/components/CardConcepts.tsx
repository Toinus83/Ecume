import { useState } from "react";
import type { ExtractedCard } from "../types";
import { Hint } from "./ContextHelp";

interface Props { card: ExtractedCard; details?: boolean; busy: boolean; onDecision: (id: string, action: "retain" | "ignore") => void; }
const roles = { objects: "Objet", actions: "Action", conditions: "Condition", tasks: "Tâche" };

export default function CardConcepts({ card, details = false, busy, onDecision }: Props) {
  const [limit, setLimit] = useState(8);
  const info = card.extraction_details;
  if (!info?.managed) return null;
  const concepts = info.concepts ?? [];
  const counts = { objects: 0, actions: 0, conditions: 0, tasks: 0 };
  const caps = { objects: 5, actions: 3, conditions: 3, tasks: 3 };
  const principal = concepts.filter(item => item.active && item.importance === "principal" && ++counts[item.role] <= caps[item.role]);
  const visible = new Set(principal.map(item => item.id));
  const secondary = concepts.filter(item => !visible.has(item.id));
  if (!details) return principal.length ? <section className="principal-concepts">
    <span>Concepts principaux <Hint label="Importance">Central pour comprendre cette carte, indépendamment de la confiance estimée.</Hint></span>
    <ul>{principal.map(item => <li key={item.id}><strong>{item.label}</strong><Hint label={item.label}>{item.reason}</Hint></li>)}</ul>
  </section> : null;
  return <div className="card-evidence">
    {secondary.length > 0 && <details className="card-disclosure"><summary>Autres concepts détectés ({secondary.length})</summary>
      <p className="quiet-note">Les concepts non retenus restent hors du graphe. Retenir un concept remet la carte à revoir.</p>
      {secondary.slice(0, limit).map(item => <div className="secondary-concept" key={item.id}>
        <div><strong>{item.label}</strong><span>{roles[item.role]} · {item.active ? "Retenu explicitement" : item.importance === "ignored" ? "Ignoré" : item.importance === "weak" ? "Faible intérêt" : "Secondaire"}</span><p>{item.reason}</p></div>
        {!item.active && <div className="button-row"><button className="ghost-button" disabled={busy || ["rejected", "linked"].includes(card.status)} onClick={() => onDecision(item.id, "retain")}>Retenir ce concept</button>{item.importance !== "ignored" && <button className="ghost-button" disabled={busy || ["rejected", "linked"].includes(card.status)} onClick={() => onDecision(item.id, "ignore")}>Ignorer</button>}</div>}
      </div>)}
      {secondary.length > limit && <button className="ghost-button" onClick={() => setLimit(limit + 8)}>Voir les suivants</button>}
    </details>}
    {!!info.rule_details?.length && <details className="card-disclosure"><summary>Règles, seuils et exceptions ({info.rule_details.length})</summary><ul>{info.rule_details.map((rule,i) => <li key={i}>{rule}</li>)}</ul></details>}
    {!!info.ambiguities?.length && <details className="card-disclosure"><summary>Points à éclaircir ({info.ambiguities.length})</summary><ul>{info.ambiguities.map((text,i) => <li key={i}>{text}</li>)}</ul></details>}
    {!!info.source_checks?.length && <details className="card-disclosure"><summary>Passages sources à vérifier ({info.source_checks.length})</summary><p className="quiet-note">Valeurs ou exceptions non entièrement reprises dans la synthèse. Vérifiez leur portée dans ces extraits avant de valider.</p>{info.source_checks.map((check,i) => <blockquote key={i}>{check.text}</blockquote>)}</details>}
    {!!info.source_excerpts?.length && <details className="card-disclosure"><summary>Extraits sources ({info.source_excerpts.length})</summary>{info.source_excerpts.map((text,i) => <blockquote key={i}>{text}</blockquote>)}</details>}
  </div>;
}
