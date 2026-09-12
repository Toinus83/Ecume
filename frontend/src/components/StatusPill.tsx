import type { CardStatus, Confidence, Level } from "../types";

const statusLabels: Record<CardStatus, string> = {
  proposed: "propose",
  accepted: "valide",
  accepted_orphan: "orphelin accepte",
  linked: "rattache",
  to_confirm: "a confirmer",
  rejected: "rejete"
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
  return <span className={`pill status-${value}`}>{statusLabels[value]}</span>;
}

export function LevelPill({ value }: { value: Level }) {
  return <span className="pill level">{levelLabels[value]}</span>;
}

export function ConfidencePill({ value }: { value: Confidence }) {
  return <span className="pill confidence">confiance {confidenceLabels[value]}</span>;
}
