import type { CardStatus, Confidence, Level } from "../types";

const statusLabels: Record<CardStatus, string> = {
  proposed: "À traiter",
  accepted: "Validé",
  accepted_orphan: "Validé sans rattachement",
  linked: "Rattaché",
  to_confirm: "À revoir",
  rejected: "Rejeté"
};

const levelLabels: Record<Level, string> = {
  strategic: "strategique",
  operational: "operatif",
  tactical: "tactique",
  operator: "operateur",
  unknown: "a qualifier"
};

const confidenceLabels: Record<Confidence, string> = {
  low: "faible",
  medium: "moyen",
  high: "fort"
};

export function StatusPill({ value }: { value: CardStatus }) {
  return <span className={`pill status-${value}`} title={value === "to_confirm" ? "Un doute ou une information manquante demande une vérification." : undefined}>{statusLabels[value]}</span>;
}

export function LevelPill({ value }: { value: Level }) {
  return <span className="pill level">{levelLabels[value]}</span>;
}

export function ConfidencePill({ value }: { value: Confidence }) {
  return <span className="pill confidence">confiance {confidenceLabels[value]}</span>;
}
