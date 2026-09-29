export default function HelpPage(){
  return <section className="help-page page-stack">
    <section><h2>À quoi sert ECUME ?</h2>
      <p>ECUME aide à transformer des documents métier en connaissance structurée. Il lit un document, propose des concepts métier, explique ce qu’il a compris, puis demande à l’utilisateur de valider, corriger ou ignorer. Les concepts validés alimentent un graphe de connaissance et peuvent ensuite servir à préparer des exports techniques.</p>
    </section>
    <section><h2>Comment ECUME travaille ?</h2>
      <p><strong>ECUME ne remplace pas l’expert métier. Il propose. L’utilisateur décide.</strong></p>
      <p>ECUME conserve les sources, les extraits, les décisions et les liens entre concepts. Si ECUME ne trouve pas une information fiable dans le document, il laisse le champ vide.</p>
    </section>
    <section><h2>Parcours recommandé</h2><ol><li>Importer un document et choisir la granularité.</li><li>Confirmer le domaine métier proposé.</li><li>Lire ce qu’ECUME a compris.</li><li>Valider, corriger ou ignorer les concepts.</li><li>Contrôler les rapprochements et le graphe.</li><li>Produire l’export adapté au destinataire.</li></ol></section>
    <details open><summary>Explication des onglets</summary><dl className="help-definitions">
      <div><dt>Import</dt><dd>Charger, suivre, arrêter et relancer l’analyse des documents.</dd></div>
      <div><dt>Cartes</dt><dd>Comprendre les propositions, confirmer le domaine et prendre les décisions métier.</dd></div>
      <div><dt>Graphe</dt><dd>Relire les concepts validés et leurs relations acceptées.</dd></div>
      <div><dt>Exports</dt><dd>Partager le JSON maître, le graphe RDF ou un lot technique de revue.</dd></div>
      <div><dt>Référentiels</dt><dd>Charger des copies locales OWL, VOC ou SHACL utilisées pour la comparaison.</dd></div>
      <div><dt>Admin</dt><dd>Configurer le LLM, les connexions RDF facultatives et les opérations de maintenance locale.</dd></div>
    </dl></details>
    <details><summary>Granularité d’analyse</summary><div className="help-levels">
      <section><h3>Large</h3><p>Moins de concepts à valider. ECUME ne garde que les notions principales.</p><small>Cartographie rapide : peu de champs secondaires, de relations et de règles.</small></section>
      <section><h3>Moyenne</h3><p>Équilibre entre lisibilité et détail. ECUME garde les concepts principaux et quelques éléments associés.</p><small>Acteurs, objets métier, actions, informations, règles explicites importantes et relations simples.</small></section>
      <section><h3>Fine</h3><p>Plus détaillé. ECUME extrait davantage d’acteurs, informations, règles, conditions et éléments secondaires. Il y aura plus de choses à relire.</p><small>Valeurs, unités, seuils et candidats SHACL lorsqu’ils sont réellement formalisables.</small></section>
    </div></details>
    <details><summary>Mode manuel ou prérempli</summary><p>En mode manuel, ECUME détecte les concepts principaux et vous laisse compléter les réponses métier. En mode prérempli, il propose aussi les acteurs, actions, moyens, informations et règles trouvés dans le texte. Tout reste corrigeable.</p></details>
    <details><summary>Concepts proches et rattachement</summary><p>Un pourcentage indique la proximité estimée, pas une certitude. Vous pouvez rattacher la mention au concept existant, la proposer comme synonyme, créer un nouveau concept ou ignorer le rapprochement.</p><p>90 à 100 % : fort · 70 à 89 % : probable · 50 à 69 % : faible. Les valeurs inférieures ne sont pas affichées en premier niveau.</p></details>
    <details><summary>Domaines métier</summary><p>Après l’analyse, ECUME propose un domaine en expliquant les termes et référentiels reconnus. Confirmez ou corrigez cette proposition. Sans domaine confirmé, les cartes restent accessibles mais aucun futur lot Echo conforme ne doit être préparé.</p></details>
    <details><summary>Exports</summary><p><strong>JSON maître ECUME</strong> conserve le périmètre complet et traçable. Le <strong>Turtle RDF générique</strong> représente le graphe. Le <strong>lot OWL/VOC/SHACL</strong> est un brouillon pour revue experte. Le futur lot Echo conforme reste à venir.</p></details>
    <details><summary>Ce qu’ECUME fait en arrière-plan</summary><p>ECUME extrait le texte, le découpe, analyse chaque partie, consolide les concepts, recherche l’existant, prépare les cartes et conserve les décisions. Le traitement continue côté backend lorsque vous changez d’onglet.</p></details>
    <details><summary>Echo, Fuseki, OntoCast et outil de revue</summary><dl className="help-definitions">
      <div><dt>Echo</dt><dd>Le référentiel validé OWL, VOC et SHACL. ECUME le consulte mais ne le modifie jamais directement.</dd></div>
      <div><dt>Fuseki</dt><dd>Le service RDF/SPARQL qui peut exposer les graphes Echo et recevoir, plus tard, les propositions ECUME dans des graphes séparés.</dd></div>
      <div><dt>OntoCast</dt><dd>Un moteur d’extraction RDF possible. S’il est absent, ECUME continue avec son moteur local.</dd></div>
      <div><dt>Ontosphere ou équivalent</dt><dd>Un outil technique pour inspecter le graphe et préparer la revue ontologue. Il n’est pas piloté par ECUME.</dd></div>
    </dl><p><strong>ECUME propose, l’expert métier valide, l’ontologue intègre, Echo reste maîtrisé.</strong></p></details>
    <details><summary>Pour les experts ontologie</summary><p>VOC porte les termes, définitions, synonymes et hiérarchies SKOS. OWL ne reçoit que des classes ou propriétés candidates suffisamment qualifiées. SHACL ne reçoit que des contraintes disposant d’une cible, d’une propriété et d’une structure vérifiable. Les autres règles restent signalées comme non formalisées.</p><p>Les trois gabarits Echo fournis constituent le contrat de structure du futur exporteur. Aucun fichier référentiel source n’est modifié.</p></details>
    <details><summary>Pour les experts ArchiMate</summary><p>ECUME s’appuie sur les réponses métier pour proposer des éléments candidats ArchiMate 3.2. Le JSON ArchiMate conserve la couche, l’élément, la confiance et la justification. Une validation métier ne vaut pas validation d’architecture.</p></details>
    <details><summary>Limites et bonnes pratiques</summary><ul><li>Contrôler les extraits avant validation.</li><li>Ne pas interpréter un score comme une preuve.</li><li>Ne pas réimporter automatiquement les brouillons ontologiques.</li><li>Préférer peu de concepts utiles à une extraction difficile à relire.</li><li>Une image sans couche texte peut nécessiter un OCR externe.</li></ul></details>
  </section>;
}
