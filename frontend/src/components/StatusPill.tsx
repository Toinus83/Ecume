import type { CardStatus, Confidence, Level } from "../types";

const statusLabels: Record<CardStatus, string> = {
  proposed: "proposé",
  accepted: "validé",
  accepted_orphan: "orphelin accepté",
  linked: "rattaché",
  to_confirm: "à confirmer"
};

const levelLabels: Record<Level, string> = {
  strategic: "stratégique",
  operational: "opératif",
  tactical: "tactique",
  operator: "opérateur",
  unknown: "à qualifier"
};

const confidenceLabels: Record<Confidence, string> = {
  low: "faible",
  medium: "moyen",
  high: "fort"
};

export function StatusPill({ value }: { value: CardStatus }) {
  return <span className={`pill status-${value}`}>{statusLabels[value]}</span>;
}

export function LevelPill({ value }: { value: Level }) {
  return <span className="pill level">{levelLabels[value]}</span>;
}

export function ConfidencePill({ value }: { value: Confidence }) {
  return <span className="pill confidence">confiance {confidenceLabels[value]}</span>;
}
