import { CircleHelp, X } from "lucide-react";
import { useRef } from "react";

const pageHelp: Record<string, { title: string; body: JSX.Element }> = {
  import: { title: "Importer et analyser un document", body: <>
    <p>Choisissez un document, puis la finesse de lecture. Une analyse large produit peu de concepts ; une analyse fine demande davantage de vérification.</p>
    <p>Le traitement continue côté serveur lorsque vous changez de page. Vous pouvez demander son arrêt : ECUME termine la partie en cours et conserve les premiers résultats.</p>
  </> },
  cards: { title: "Comprendre et décider", body: <>
    <p>Commencez par lire ce qu’ECUME a compris, puis vérifiez ce qu’il vous demande de décider. Validez seulement les concepts utiles à conserver.</p>
    <p>« Déjà reconnu » signifie que le document apporte une nouvelle source à une connaissance existante. « À vérifier » indique précisément ce qu’ECUME n’a pas pu confirmer.</p>
  </> },
  graph: { title: "Consulter la connaissance validée", body: <>
    <p>Le graphe montre les concepts retenus et leurs relations acceptées. Utilisez la recherche et les filtres pour isoler une partie de la connaissance.</p>
    <p>Une incohérence reste corrigeable depuis les actions de modification ; une proposition non validée n’apparaît pas dans le graphe principal.</p>
  </> },
  exports: { title: "Réutiliser les données hors d’ECUME", body: <>
    <p>JSON conserve le dossier complet. JSON-LD et le Turtle ECUME générique servent aux outils de données liées, tandis que CSV et Cypher facilitent l’import dans Memgraph.</p>
    <p>Le Turtle générique n’est pas un lot Echo conforme. Les sorties Echo expérimentales et ArchiMate sont des propositions à contrôler.</p>
  </> },
  references: { title: "Comparer avec les référentiels", body: <>
    <p>Les référentiels importés sont des copies locales en lecture seule. ECUME les utilise pour reconnaître les termes, concepts et règles déjà connus.</p>
    <p>Une absence de correspondance ne rend pas le concept invalide : elle peut devenir une proposition d’enrichissement à examiner.</p>
  </> },
  admin: { title: "Configurer ECUME", body: <>
    <p>Cette page configure le modèle de langage et permet de vérifier sa connexion. Le mode sans LLM reste disponible pour travailler manuellement.</p>
    <p>La remise à zéro supprime les données locales après confirmation explicite ; utilisez-la uniquement pour les essais.</p>
  </> },
  dashboard: { title: "Suivre l’activité", body: <p>Le tableau présente une vue globale des documents, cartes et décisions. Il sert au contrôle, pas au travail quotidien sur les concepts.</p> },
  orphans: { title: "Contrôler les concepts isolés", body: <p>Un concept sans relation peut être valide. Cette page permet de le rattacher, de l’accepter isolément ou de le remettre à vérifier.</p> },
  help: { title: "Aide générale ECUME", body: <p>Cette page décrit le parcours complet. Les premières sections sont destinées au métier ; les volets repliés détaillent les usages ontologie et ArchiMate.</p> },
};

export default function HelpCenter({ page }: { page: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const help = pageHelp[page] ?? pageHelp.import;
  return <>
    <button className="ghost-button icon-button help-trigger" title="Aide sur cette page" aria-label="Ouvrir l’aide" onClick={() => dialog.current?.showModal()}><CircleHelp size={20} /></button>
    <dialog className="help-dialog" ref={dialog} aria-labelledby="help-title" onClick={event => { if (event.target === dialog.current) dialog.current.close(); }}>
      <div className="help-dialog-header"><div><span>Aide ECUME</span><h2 id="help-title">{help.title}</h2></div>
        <button className="ghost-button icon-button" title="Fermer" aria-label="Fermer l’aide" onClick={() => dialog.current?.close()}><X size={19}/></button></div>
      <section className="help-page-content">{help.body}</section>
      <section className="help-workflow"><h3>Le principe</h3>
        <p>Vous décrivez et validez votre métier. ECUME se charge de la traduction technique et conserve toujours la source de ses propositions.</p>
        <ol><li>ECUME lit le document.</li><li>ECUME identifie son contexte métier et signale ses doutes.</li><li>ECUME reconnaît l’existant et présente les nouveautés.</li><li>Vous validez, corrigez ou ignorez.</li><li>Les exports produisent des lots contrôlables.</li></ol>
      </section>
      <details className="technical-help"><summary>Comment fonctionnent les mappings techniques ?</summary>
        <h3>Ontologies Echo</h3>
        <p><strong>VOC</strong> porte les termes, synonymes et définitions. <strong>OWL</strong> décrit les catégories et relations du domaine. <strong>SHACL</strong> exprime les contrôles formalisables : champs obligatoires, types, valeurs, seuils ou cardinalités.</p>
        <p>Une même règle métier peut alimenter les trois couches. ECUME réutilise l’existant et prépare séparément les nouveautés, sans modifier les fichiers sources.</p>
        <h3>ArchiMate 3.2</h3>
        <p>Les réponses métier permettent de proposer des capacités, objectifs, acteurs, rôles, processus, services, informations, applications ou contraintes. Ces correspondances restent candidates jusqu’à leur validation.</p>
        <h3>Exports</h3>
        <p>JSON est le format complet d’ECUME. JSON-LD et le Turtle générique représentent le graphe avec des URI stables. Un futur lot Echo produira trois fichiers distincts OWL, VOC et SHACL adaptés au domaine confirmé. L’export ArchiMate JSON conserve les justifications avant une future génération contrôlée du Model Exchange XML.</p>
      </details>
    </dialog>
  </>;
}
