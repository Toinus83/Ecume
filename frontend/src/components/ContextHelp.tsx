import type { ReactNode } from "react";
import { CircleHelp } from "lucide-react";

export function ContextHelp({ children, title = "Que dois-je faire ici ?" }: { children: ReactNode; title?: string }) {
  return <details className="context-help"><summary><CircleHelp size={15} />{title}</summary><div>{children}</div></details>;
}

export function Hint({ label, children }: { label: string; children: string }) {
  return <span className="hint" tabIndex={0} aria-label={`${label} : ${children}`}><CircleHelp size={14} /><span role="tooltip">{children}</span></span>;
}

export function ActionError({ error }: { error: string }) {
  if (!error) return null;
  const connection = /fetch|network|connection|connexion/i.test(error);
  return <div className="error" role="alert"><p>{connection ? "ECUME ne répond pas. Vérifiez qu’il est lancé, puis réessayez." : "L’action n’a pas abouti. Consultez le détail avant de réessayer."}</p><details><summary>Détail de l’erreur</summary><p>{error}</p></details></div>;
}
