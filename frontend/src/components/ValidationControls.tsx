import { useEffect, useState } from "react";
import { RotateCcw, Save, CheckCheck } from "lucide-react";
import { api } from "../api/client";
import { ActionError, ContextHelp, Hint } from "./ContextHelp";
import type { ValidationSettings } from "../types";

const modes = [
  ["strict", "Strict", "Vous validez toutes les cartes vous-même."],
  ["assisted", "Assisté", "ECUME valide les évidences et vous montre les cas incertains."],
  ["automatic", "Automatique", "ECUME valide les propositions fiables. Vous contrôlez ensuite le résultat."]
] as const;
const percent = (value: number) => Number((value * 100).toPrecision(12));
interface Props { onSettingsChange?: (settings: ValidationSettings) => void; cardIds?: string[]; onApplied?: () => void; }

export default function ValidationControls({ onSettingsChange, cardIds, onApplied }: Props) {
  const [settings, setSettings] = useState<ValidationSettings | null>(null);
  const [auto, setAuto] = useState(90);
  const [review, setReview] = useState(60);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [changing, setChanging] = useState(false);
  const [kept, setKept] = useState(false);
  const [report, setReport] = useState<Record<string, number> | null>(null);
  useEffect(() => {
    let cancelled = false;
    api.validationSettings().then(value => {
      if (!cancelled) { setSettings(value); setAuto(percent(value.auto_threshold)); setReview(percent(value.review_threshold)); onSettingsChange?.(value); }
    }).catch(err => { if (!cancelled) setError(String(err)); });
    return () => { cancelled = true; };
  }, []);
  async function save(value: ValidationSettings) {
    setBusy(true); setError(""); setNotice(""); setReport(null);
    try {
      const saved = onSettingsChange ? value : await api.saveValidationSettings(value);
      setSettings(saved); setAuto(percent(saved.auto_threshold)); setReview(percent(saved.review_threshold));
      onSettingsChange?.(saved); setChanging(false); setKept(false);
      setNotice(onSettingsChange ? "Choix enregistré pour cette analyse." : "Choix enregistré pour les prochaines analyses. Les cartes existantes sont conservées.");
    } catch (err) { setError(String(err)); } finally { setBusy(false); }
  }
  async function apply() {
    if (!settings || !cardIds?.length) return;
    setBusy(true); setError(""); setNotice(""); setReport(null);
    try { const result = await api.applyValidation(settings, cardIds); setReport(result.counts); onApplied?.(); }
    catch (err) { setError(String(err)); } finally { setBusy(false); }
  }
  const mode = modes.find(item => item[0] === settings?.mode);
  const custom = !!settings && (settings.auto_threshold !== .9 || settings.review_threshold !== .6);
  return <section className="validation-controls">
    <div className="validation-heading"><div><h2>{onSettingsChange ? "Mode de cette analyse" : "Mode de validation"}</h2>
      <p>Mode actuel : <strong>{mode?.[1] ?? "Chargement…"}</strong> <span className="requirement">Niveau d’exigence : {settings ? custom ? "Personnalisé" : "Recommandé" : "…"}</span></p></div>
      <button className="ghost-button" aria-expanded={changing} disabled={!settings || busy} onClick={() => setChanging(!changing)}>Changer le mode</button></div>
    <p className="mode-description">{mode?.[2]}</p>
    {changing && <div className="mode-choices">{modes.map(([value, label, help]) => <button key={value} disabled={busy} aria-pressed={settings?.mode === value} className={settings?.mode === value ? "active" : "ghost-button"} onClick={() => settings && void save({ ...settings, mode: value })}><strong>{label}</strong><span>{help}</span></button>)}</div>}
    <ContextHelp title="Pourquoi reste-t-il des cartes à valider ?">
      <ul><li>Sans score métier, une ancienne carte reste à traiter.</li><li>Une carte ambiguë ou insuffisamment fiable reste à vérifier.</li><li>Les décisions humaines sont protégées.</li><li>Les rapprochements incertains se décident séparément.</li></ul>
      <p>Changer le mode ne retraite pas les anciennes cartes. En mode Strict, vous validez tout vous-même.</p>
      {cardIds && <><button disabled={!settings || busy || !cardIds.length} onClick={() => void apply()}><CheckCheck size={16} />Appliquer aux cartes non décidées ({cardIds.length} dans la sélection)</button><p className="quiet-note">Sans nouvelle analyse. Les cartes sans score et les décisions existantes sont conservées.</p></>}
    </ContextHelp>
    <details className="advanced-settings"><summary>Réglages avancés</summary>
      {settings && <p>En {mode?.[1]}, {settings.mode === "strict" ? "aucune carte n’est auto-validée." : "le seuil utilisé est " + percent(settings.mode === "assisted" ? settings.auto_threshold : settings.review_threshold) + " %. Plus le seuil est élevé, plus la sélection est stricte."}</p>}
      {custom && <div className="settings-warning"><p>{kept ? "Vos seuils actuels sont conservés." : "Vos seuils sont personnalisés. Les seuils recommandés sont 90 % / 60 %."}</p><div className="button-row">{!kept && <button type="button" className="ghost-button" onClick={() => setKept(true)}>Conserver mes seuils</button>}<button disabled={busy} onClick={() => settings && void save({ ...settings, auto_threshold: .9, review_threshold: .6 })}><RotateCcw size={15} />Rétablir 90 % / 60 %</button></div></div>}
      <form className="threshold-form" onSubmit={e => { e.preventDefault(); if (settings) void save({ ...settings, auto_threshold: auto / 100, review_threshold: review / 100 }); }}>
        <label>Auto-validation en Assisté (%)<input type="number" min={0} max={100} step="any" required value={auto} onChange={e => setAuto(Number(e.target.value))} /></label>
        <label>À revoir / Automatique (%)<input type="number" min={0} max={auto} step="any" required value={review} onChange={e => setReview(Number(e.target.value))} /></label>
        <button disabled={!settings || busy || review > auto}><Save size={16} />Enregistrer</button>
      </form><p className="quiet-note">Score métier <Hint label="Score métier">Estimation de confiance sur la compréhension métier. Ce n’est pas une preuve.</Hint> Un score absent n’est jamais inventé. Aucun réglage ne remplace une décision humaine.</p>
    </details>
    {notice && <p className="quiet-note" role="status">{notice}</p>}
    {report && <div className="validation-report" role="status"><strong>Application du mode {mode?.[1]}</strong>
      <ul><li>{report.auto_validated} cartes auto-validées</li><li>{report.to_review + report.needs_user_validation} cartes restent à vérifier</li><li>{report.missing_score} cartes conservées car sans score métier</li><li>{report.human_decision} cartes protégées par une décision humaine</li>
        {(report.already_decided + report.uncertain_history + report.missing_card) > 0 && <li>{report.already_decided} déjà décidées, {report.uncertain_history} historiques incertains, {report.missing_card} indisponibles</li>}</ul>
      {report.auto_validated === 0 && <p>Aucune auto-validation : {report.missing_score > 0 ? "des cartes n’ont pas de score métier. Une nouvelle analyse est nécessaire pour obtenir de nouvelles propositions évaluées." : settings?.mode === "strict" ? "le mode Strict demande une validation humaine." : "les cartes sont déjà décidées, incertaines ou sous le seuil choisi."}</p>}
    </div>}
    <ActionError error={error} />
  </section>;
}
