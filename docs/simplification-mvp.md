# Lot de simplification ECUME

## Parcours retenu

Import -> bilan documentaire -> nouveaux concepts / deja reconnus / a verifier.
Une proposition nouvelle n'est pas un noeud du graphe. La validation humaine
materialise la carte et ses champs confirmes dans une transaction.
Les actions principales sont Valider, Corriger, Ignorer.

Import propose Large / Moyenne / Fine et Manuel / Pre-rempli. Ces choix sont
enregistres pour l'analyse, sans reecrire les seuils historiques de validation.
Le nouveau parcours ne pratique pas d'auto-validation de nouveaux concepts.
Les outils Tableau et Orphelins sont ranges sous Outils avances. Les scores,
anciens modes de validation et mappings ne figurent plus sur le parcours principal.
Les anciens endpoints et outils restent disponibles pour compatibilite.

## Pourquoi zero carte ?

L'audit a retrouve des analyses historiques avec du texte extrait, mais sans
carte ni avertissement. L'ancien traitement acceptait une liste vide ou absente
et ne distinguait pas absence de proposition, concept deja connu et reponse
inexploitable. La reponse brute historique du LLM n'etant pas conservee, on ne
peut pas attribuer avec certitude chaque ancien resultat vide a une cause precise.
Ce n'est donc pas une preuve que tous les concepts existaient deja.

Un second mecanisme fabriquait une carte "Passages du document a verifier"
pour porter les nombres ou exceptions non repris. Ce comportement est retire.
Ces extraits restent dans les points de lecture du bilan, jamais dans une
nouvelle carte. Les anciennes alertes sont masquees dans Cartes, sans suppression
ni changement de leur statut en base. Une ancienne fausse carte deja validee
peut encore exister dans le graphe historique : son retrait reste une action humaine.

Chaque nouvelle analyse du parcours simple conserve maintenant : texte lu,
parties traitees, erreurs par partie, avertissements, nouveaux concepts,
concepts ECUME reconnus, termes Echo reconnus, ambiguities et extraits courts.
Un echec partiel reste un echec explicite et empeche la purge automatique.
Une reponse vide conserve un bilan consultable, sans affirmation "tout est connu".

## Mentions et identite

Une mention conserve son libelle local, le document et son extrait.
Un rattachement conserve separement l'identifiant et le libelle canonique.
La reconnaissance automatique est volontairement conservative : correspondance
normalisee unique sur un libelle ou un alias valide, ou un terme Echo actif.
ECUME est prioritaire sur Echo ; le vocabulaire VOC est prioritaire sur la classe
OWL homonyme dans un meme ensemble de resultats. Plusieurs cibles de meme
priorite restent ambigues. La proximite textuelle ne vaut pas synonymie certaine.

Le crayon permet de garder, de rechercher une autre cible (8 resultats maximum),
ou de proposer explicitement un nouveau concept. Il fonctionne aussi sur les
champs des nouvelles cartes. Une cible retiree n'est plus presentee comme fiable.
Les decisions sont journalisees avec avant/apres.

## Champs et graphe

Les huit questions metier restent en texte simple. En pre-remplissage, une
valeur doit avoir une citation retrouvee dans la partie source ; sinon elle
reste vide avec un point a verifier. En mode Manuel, les champs restent vides.
Les corrections humaines ont une origine utilisateur ; un champ inchange
conserve sa citation au lieu de perdre sa provenance.

La validation reutilise les identites connues. Les champs ambigus restent des
mentions, sans creation automatique de doublons. Un terme Echo reconnu n'est
pas duplique en noeud local. Les liens crees par le nouveau parcours sont des
associations generiques "concerne", avec question et preuve en metadonnees :
ECUME ne transforme pas une simple association en causalite ou decomposition.
Les liens/canoniques deja partages restent proteges lors des corrections.
Une correction de carte retire sa validation locale jusqu'a une nouvelle decision.

La purge du fichier et du texte integral ne supprime pas les mentions, cartes,
concepts ou extraits. La suppression de connaissance et la RAZ effacent aussi
les nouvelles tables, uniquement dans leurs actions destructives explicites.

## Mappings et exports

Les trois entrees visibles sont Export graphe, Export Echo et Export ArchiMate.
Les formats historiques et l'archive restent dans un volet replie.
JSON et JSON-LD incluent les mentions documentaires et bilans. Le ZIP Echo
ajoute echo_document_mentions.csv, y compris quand un document ne cree aucun
nouveau noeud parce que son vocabulaire etait deja reconnu.

Sans referentiel charge, un ZIP de proposition fournit OWL, VOC, SHACL et le
JSON complet du noyau valide. Ce n'est PAS une ontologie approuvee : les classes
OWL et les formes SHACL sont des propositions. Les formes imposent seulement
libelle et source sur les futures instances. Aucune regle metier numerique ou
juridique n'est automatiquement traduite en contrainte executable. Les regles
et leurs valeurs restent dans le JSON pour revue humaine.

Les mappings ArchiMate restent candidats. Verification effectuee sur les fiches
ArchiMate 3.2 N221 de The Open Group :
https://www.opengroup.org.cn/sites/default/files/N221C_%E6%97%A0%E6%B0%B4%E5%8D%B0%E7%89%88.pdf

Les familles Goal/Outcome, BusinessActor/BusinessRole, BusinessProcess/Function,
BusinessObject, DataObject, Constraint/Requirement sont distinctes. Un moyen
non qualifie n'est pas automatiquement transforme en Node ou ApplicationComponent.
Une information metier ne prouve pas a elle seule une donnee automatisee :
le mapping candidat doit etre confirme. Aucun XML ni equivalence formelle ajoute.
L'export ArchiMate reste fonde sur le noyau valide, pas sur les reponses brutes.

## Migration et fichiers

Migration additive idempotente : deux nouvelles tables review_runs et
review_mentions, plus l'index idx_review_document. Pas de colonne existante
supprimee ou renommee. Pas de reclassification massive de l'ancienne base.

Nouveaux fichiers fonctionnels :
- backend/app/routers/review.py
- backend/app/services/review_service.py
- backend/app/services/review_graph.py
- backend/app/services/ontology_draft.py
- backend/tests/test_review.py
- frontend/src/components/SimpleConcept.tsx
- docs/simplification-mvp.md

Fichiers raccordes ou corriges :
- backend/app/database/db.py ; backend/app/main.py
- backend/app/llm/prompt.py, api.py, ollama.py
- backend/app/services/analysis_service.py, salience_service.py, job_service.py
- backend/app/services/card_service.py, document_service.py, admin_service.py
- backend/app/services/export_service.py, echo_export_service.py, echo_workshop.py
- backend/tests/test_salience.py, test_echo_exports.py
- frontend/src/App.tsx ; api/client.ts ; types.ts ; styles/global.css
- frontend/src/pages/CardsPage.tsx, ImportPage.tsx, ExportPage.tsx, GraphPage.tsx
- frontend/src/components/DocumentLibrary.tsx, EffectCard.tsx

Les fichiers Docker/deploiement, config.py, README et .gitignore deja modifies
avant ce lot sont conserves. La conteneurisation n'a pas ete reprise.
Les scripts et captures de recette dans data/runtime sont ignores par Git.

## Recette manuelle avant validation du MVP

1. Relancer front et backend avec les scripts habituels du README.
2. Dans Admin, verifier URL, modele et acces au LLM reel.
3. Importer un petit document connu en Large / Pre-rempli, sans Echo.
4. Ouvrir son bilan, verifier les citations et les trois rubriques.
5. Valider une proposition : la retrouver dans le graphe valide.
6. Corriger une question, puis revalider. Verifier les liens et le concept partage.
7. Importer un autre document qui utilise un libelle deja valide ou son alias :
   il doit apparaitre dans Deja reconnus, avec sa nouvelle source, sans doublon.
8. Corriger un rattachement au crayon, puis tester une creation explicite.
9. Refaire en Manuel : les questions doivent rester vides.
10. Charger Echo OWL/VOC/SHACL et importer un document employant un terme VOC.
11. Verifier la reconnaissance, puis les exports JSON, Echo ZIP et ArchiMate JSON.
12. Simuler un LLM indisponible : bilan d'echec et source conservee.
13. Tester une purge : les mentions et extraits doivent rester consultables.

## Limites a garder visibles

- Les tests de traitement utilisent des reponses LLM controlees. La qualite
  semantique et le temps reel sur vos gros PDF restent a recetter avec votre modele.
- Pas d'OCR ; un PDF image sans texte exploitable demande une extraction adaptee.
- La proximite est lexicale, sans moteur de synonymie semantique general.
- Les huit questions sont completes pour les nouvelles analyses ; les anciennes
  cartes gardent leur structure et leurs outils historiques dans le graphe.
- Les rattachements connus ne deviennent pas automatiquement des equivalences OWL.
- Les champs/relations techniques et les regles structurees demandent une revue
  avant integration dans un modele central. Le ZIP sans Echo est un brouillon.
- L'API externe existante attend toujours un protocole chat/completions compatible ;
  le deploiement on-premise n'implique pas a lui seul cette compatibilite.
- La verification navigateur de correction/validation emploie une fixture IHM,
  sans appeler le LLM ni injecter de document de demonstration dans votre base.

## Verification

Suite backend complete : 267 tests passes, puis 26 tests cibles de nouveau passes
apres les derniers ajustements de comptage et tracabilite. Deux avertissements FastAPI existants
sur on_event. TypeScript : sans erreur. Build Vite : reussi ; avertissement de
bundle JavaScript superieur a 500 kB (environ 707 kB, 221 kB gzip).
Recette navigateur Edge/Playwright a 1440x1000 et 390x844 : navigation,
correction et validation verifiees ; pas d'erreur JavaScript ou HTTP,
pas de debordement horizontal. git diff --check : code de sortie 0.

Aucun commit et aucun push effectues.
