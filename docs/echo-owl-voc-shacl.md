# MVP Echo OWL / VOC / SHACL

ECUME reste un atelier. Les fichiers Echo sources sont copies localement, jamais
modifies. Le JSON et les CSV sont des propositions a relire, pas une autorisation
de reimport dans le referentiel central. Aucun commit ni push fait pendant ce lot.

## Demarrer et tester

Arreter les serveurs avant installation des nouvelles dependances. Depuis la racine :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1 -WithDev
powershell -ExecutionPolicy Bypass -File scripts\start-ecume.ps1
```

Ouvrir `http://127.0.0.1:5173`. Sauvegarder auparavant le dossier local `data/`.
Le script verifie les dependances existantes et ajoute pySHACL si necessaire.

1. Dans Referentiels, importer successivement les fichiers synthetiques de test :
   [OWL](../backend/tests/fixtures/Echo_Test.owl.ttl),
   [VOC](../backend/tests/fixtures/Echo_Test.voc.ttl),
   [SHACL](../backend/tests/fixtures/Echo_Test.shacl.ttl).
2. Verifier qu'ils appartiennent au meme referentiel `Echo_Test`. La cible du
   formulaire est conservee pour completer le paquet. Pour un autre domaine,
   choisir Nouveau. Le regroupement par nom reconnait `Nom.owl.ttl`, `Nom.voc.ttl`
   et `Nom.shacl.ttl`, sans domaine code en dur.
3. Examiner le profil : 2 classes, 3 proprietes, 3 termes, 7 formes interpretees
   (2 NodeShape et 5 PropertyShape). Verifier les trois fichiers associes.
4. Importer votre propre document metier. Pour cette reference synthetique, les
   termes Construction/Batiment et une regle de distance permettent une recette
   simple. Aucun document metier de demonstration n'est ajoute a la base.
5. Examiner les cartes, la regle detectee, sa valeur, son unite et son extrait.
   Corriger si besoin puis valider la carte. Les regles suivent la decision de
   leur carte, pas une validation parallele.
6. Sur une carte validee, verifier le resume des elements reconnus dans Echo et
   les nouveautes proposees. Les correspondances et controles restent replies.
7. Corriger une unite ou une valeur : la carte revient a revoir. Confirmer que
   ses regles disparaissent du lot principal jusqu'a nouvelle validation.
8. Dans Exports, choisir le referentiel cible et Preparer le bilan. Lire les
   controles et avertissements, puis telecharger JSON et ZIP de controle.
9. Verifier dans le JSON la source, l'extrait, les statuts, les valeurs/unites et
   la separation entre reconnu, nouveaute, enrichissement et non-conformite.
10. Desactiver puis supprimer la copie de reference sur votre base de recette :
    les cartes et connaissances doivent rester presentes. Ne pas utiliser la RAZ
    administrative sur une base de travail a conserver.

Ces trois fichiers sont exclusivement des fixtures synthetiques, pas des
ontologies Marine. Aucun referentiel Marine reel n'a encore ete valide en recette.

## Import et profil

Le formulaire permet la detection automatique ou la declaration OWL, VOC,
SHACL, mixte. Reimporter les memes octets sur la meme cible reutilise la copie ;
choisir une couche explicite permet de corriger sa declaration. La declaration
ne transforme pas artificiellement les donnees RDF : une couche sans elements
reconnus est signalee insuffisante.

Formats : TTL, RDF/XML, OWL en Turtle/RDF/XML, XML RDF et extension locale SHACL.
OWL/XML fonctionnel et JSON-LD en entree ne sont pas pris en charge.
Limites : 5 Mio / 100 000 triplets par fichier, 12 fichiers par paquet et
100 000 termes/relations consolides. Import distant, DTD et entites XML interdits.

Le profil distingue fichier lu, alignement exploitable et aptitude a un export
RDF adapte. La derniere reste fausse dans ce lot. Les profils suffisants,
partiels et insuffisants ne constituent pas une certification semantique.
Les domaines/portees/proprietes OWL sont conserves. Les synonymes VOC, variantes,
definitions et hierarchies restent separes de la connaissance ECUME.

Migrations additives : `reference_files`, `echo_validation_reports` et colonne
`echo_mappings.target_signature`, ajoutee apres PRAGMA si absente. Le profil
unifie reste un JSON dans `reference_repositories`. Les fichiers associes portent
leur empreinte, leur couche declaree, leur profil et leurs octets d'origine.
Les anciens profils ne sont pas recalcules au demarrage ; reimporter ou completer
explicitement leur reference pour construire le profil multi-couches.

## Analyse et regles

Chaque chunk recoit un contexte Echo borne : termes et variantes pertinents,
classes candidates et proprietes attendues par les formes simples. Ce contexte
est traite comme une donnee, pas comme une instruction. Le LLM reste responsable
de proposer la structuration ; rien ne garantit une extraction exhaustive.
Les modes Sobre/Equilibre/Exhaustif et les seuils de validation sont conserves.

Les regles sont stockees dans `extracted_cards.extraction_details.business_rules`,
avec identifiant, libelle, description, type, valeur, unite, condition, exception,
source, extrait, justification, confiance et saillance. Elles restent dans le noyau
ECUME et suivent la validation de leur carte. Les anciennes listes `rule_details`
sont conservees ; leur conversion lors d'une nouvelle extraction ne reclasse pas
les anciennes cartes. Un extrait ou une valeur introuvable signale une regle a
verifier et empeche l'auto-validation des nouvelles reponses structurees.

La correction d'une regle est transactionnelle, tracee et remet la carte a revoir.
La purge de source conserve les regles et extraits. La fusion de cartes conserve
les regles avec leur document d'origine. Aucune interpretation juridique ni
inference de condition absente n'est revendiquee.

## Reconnaissance et nouveautes

La reconnaissance transparente exige un nom ou synonyme exact et unique dans la
couche cible du referentiel. Elle est calculee a l'ouverture d'une carte validee
ou a la preparation de son lot, et les candidats sont persistants. Un terme reconnu
reste un mapping candidat tant qu'une decision humaine n'a pas confirme son sens.
La reconnaissance n'auto-valide ni le metier, ni ArchiMate, ni une equivalence OWL.

Les correspondances ambigues/faibles, mises a revoir ou rejetees ne sont pas
reconnues silencieusement. Une nouvelle recherche conserve les decisions humaines.
Changer le concept ou la definition cible rend le mapping humain ancien/a revoir,
sans effacer son statut historique. Une propriete OWL n'est pas reconnue comme une
classe de concept. Les relations ont leurs propres positionnements candidats.

L'absence de candidat propose une nouveaute, sans prouver l'absence dans toute
l'ontologie. Le lot garde les voisins candidats, propositions de termes VOC,
positionnements de regles OWL et formes SHACL applicables. Les synonymes et
definitions additionnels d'une cible existante restent des enrichissements
proposes apres confirmation humaine du mapping exact. Aucun remplacement automatique.

## Controle SHACL simple

Le moteur est [pySHACL](https://github.com/RDFLib/pySHACL), sans inference,
SHACL Advanced Features, JavaScript ou imports distants. Les formes sont lues,
puis seules les contraintes autorisees sont reconstruites pour le moteur.
Le contenu RDF importe n'est jamais execute comme du code.

Sous-ensemble : targetClass, chemins de propriete simples, minCount, maxCount,
datatype, class, nodeKind, in, pattern/flags, severite et message. Les chemins
complexes, cibles non determinees, formes desactivees et contraintes non prises
en charge restent visibles comme non interpretes. Aucun SPARQL n'est execute.

La projection de travail utilise les libelles/definitions, valeur, unite, source,
conditions, exceptions et relations acceptees dont le nom correspond a une
propriete de reference. Les champs sont rapproches par un petit vocabulaire
explicite francais/anglais dans `echo_workshop.FIELD_NAMES`. Un champ inconnu
reste non verifiable : sa valeur n'est ni inventee ni consideree conforme.
Les instances de travail ne constituent pas un export RDF approuve.

Resultats : conforme aux contraintes verifiees, a completer, non conforme,
non verifiable. Ils ne modifient jamais automatiquement la validation metier et
ne suppriment aucune proposition. Les details techniques du moteur restent dans
le rapport ; les messages courants ne montrent pas d'URI.

Le controle s'execute dans un sous-processus limite a 20 secondes. Au-dela de
10 000 couples element/forme, le lot est marque non verifiable. Les cinq derniers
rapports par reference sont conserves. Un arret/une erreur reste non verifiable
et peut etre retente, jamais interprete comme un succes.

## Exports

Le JSON v2 conserve les champs v1 et ajoute `target_repository`, `echo_profile`,
`owl_profile`, `voc_profile`, `shacl_profile`, `recognized_existing_echo_elements`,
`ecume_concepts`, `ecume_rules`, `proposed_new_concepts`, `proposed_voc_terms`,
`proposed_owl_alignments`, `proposed_voc_alignments`, `proposed_shacl_alignments`,
`shacl_checks` et `review_items`. Les sources et extraits sont inclus, pas les
octets des fichiers ni le texte integral des documents.

Le ZIP conserve les fichiers existants et ajoute `echo_recognized_existing.csv`,
`echo_new_voc_terms.csv`, `echo_rules.csv`, `echo_shacl_report.csv`. Il contient
tout le JSON et le rapport de controle. Les cellules ressemblant a des formules
restent protegees. Le JSON est la representation complete.

Les cartes/concepts rejetes ou a revoir, elements faibles non retenus et liens
casses sont exclus de la connaissance principale. Les mappings rejetes ne sont
pas exportes comme alignements proposes. Les controles non conformes restent
visibles pour correction. `ready_for_automatic_import` reste toujours faux.

## Limites a recetter

- Reconnaissance lexicale, pas desambiguïsation semantique generale.
- Regles tributaires des extractions du LLM ; verifier valeurs, unites et sources.
- Pas d'editeur expert de projection de proprietes arbitraires. Une reference
  aux conventions personnalisees peut rester partiellement non verifiable.
- Pas de raisonnement OWL, transitivite ou alignement automatique de taxonomies.
- Pas de suppression individuelle d'un fichier dans un paquet ni remplacement
  automatique d'une version : utiliser un nouveau paquet pour une autre version.
- Les limites de volume privilegient une recette locale. Les recherches et
  projections sont synchrones, pas un pipeline distribue.
- JSON-LD/TTL Echo, PPTX et ArchiMate XML restent differes.
- La recette navigateur utilise une copie locale et des propositions synthetiques.
  La qualite avec votre modele Ollama et vos documents doit etre verifiee manuellement.

## Verification du 15 septembre 2026

- Backend : **227 tests passes**, 2 avertissements FastAPI `on_event`,
  aucun echec, 70,92 secondes sur la derniere execution complete.
- TypeScript : `tsc --noEmit`, code 0.
- Vite : build reussi, 1 604 modules, 7,84 secondes. Avertissement connu
  pour le bundle JS de 706,16 ko (gzip 221,10 ko), non bloquant.
- `git diff --check` : code 0. Git peut signaler LF/CRLF sous Windows.
- Navigateur Edge/Playwright : ordinateur 1440 x 1000 et mobile 390 x 844,
  import des trois couches, profil, regle, reconnaissance automatique, controles,
  export JSON et suppression de la reference de recette. Aucun plantage JS ni
  debordement horizontal detecte. Recette effectuee sur copie locale.
- Le passage analyse -> contexte Echo -> regles -> export est couvert par un
  fournisseur LLM simule dans les tests. La qualite avec Ollama et vos documents
  reels reste a tester ; elle n'est pas deduite du succes des tests automatiques.
- Les serveurs temporaires de recette sont arretes ; aucun commit/push realise.

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp=data/runtime/pytest-echo-release-check
.\backend\.venv\Scripts\python.exe scripts/check-python-deps.py backend/requirements-dev.txt
git diff --check
```

Le build a utilise le Node fourni par Codex et l'API Vite (meme racine/plugin React)
pour contourner l'erreur d'environnement Windows du Node systeme observee lors
des lots precedents. Sur un poste standard : `cd frontend`, puis `npm run build`.

## Fichiers principaux

Backend : `database/db.py`, `routers/references.py`, `services/reference_parser.py`,
`reference_service.py`, `echo_profile.py`, `business_rule_service.py`,
`echo_workshop.py`, `echo_shacl_worker.py`, `echo_mapping_service.py`,
`echo_export_service.py`, `analysis_service.py`, `salience_service.py`,
`admin_service.py`, `llm/prompt.py`, `llm/api.py`, `llm/ollama.py`, `requirements.txt`.

Frontend : `types.ts`, `api/client.ts`, `components/EchoCard.tsx`,
`components/EffectCard.tsx`, `pages/ReferencesPage.tsx`, `pages/ExportPage.tsx`,
`styles/global.css`.

Tests : `test_echo_layers.py`, extension `test_echo_exports.py`, trois fixtures
Echo_Test. Documentation : README, guide Echo et ce guide. `.gitignore` autorise
uniquement ces trois fichiers RDF synthetiques ; les fichiers utilisateur restent ignores.
