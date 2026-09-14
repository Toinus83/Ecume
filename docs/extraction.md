# Extraction sobre et importance locale

ECUME privilegie quelques concepts utiles par carte. Le mode d'extraction est choisi
dans Import, puis fige dans le travail d'analyse. Il ne modifie pas les seuils de
validation ni les anciennes cartes.

| Mode | Concepts associes principaux au maximum | Usage |
| --- | --- | --- |
| Sobre (defaut) | 4, en plus de l'effet principal | Validation rapide |
| Equilibre | 8, en plus de l'effet principal | Davantage de contexte |
| Exhaustif | 14, en plus de l'effet principal | Examen plus large |

Ces plafonds ne sont pas des quotas. Par role, le plafond reste de 5 objets,
3 actions, 3 conditions et 3 taches. Un principal propose par le LLM doit avoir
une justification et un score d'importance d'au moins 0,65. Ce critere d'extraction
est distinct des seuils de confiance utilises pour l'auto-validation.
Les scores absents ne sont jamais inventes.

## Connaissance et contexte

- Les principaux retenus sont proposes dans le graphe de travail, puis visibles
  dans le graphe principal uniquement apres validation.
- Les secondaires, faibles et ignores restent dans les details de la carte,
  sans creation de noeud. Le mode Exhaustif ne les valide pas automatiquement.
- Retenir explicitement un secondaire cree ou reutilise son concept et remet la
  carte a revoir. Un concept partage conserve ses usages dans les autres cartes.
- Une correction manuelle reste possible ; les concepts au-dela des plafonds
  d'affichage restent accessibles dans les details.
- Les regles, seuils, distances, conditions, exceptions et extraits sources
  restent independants du nombre de concepts retenus.

La consolidation des parties d'un document cumule leurs descriptions, regles,
extraits et incertitudes. Elle ne garde pas seulement la premiere occurrence.
La confiance consolidee est prudente : le minimum des scores, ou aucun score
si une partie ne dispose pas de score.

Un controle complementaire conserve des extraits courts autour des valeurs avec
unites et des marqueurs d'exception dans le texte extrait. Les passages non repris
integralement sont presentes dans **Passages sources a verifier** et empechent
l'auto-validation de la carte concernee. Ils restent du contexte a verifier,
pas des regles interpretees ni de nouveaux concepts. Chaque extrait garde le
document, le numero de partie et ses positions relatives dans cette partie.
Ils sont conserves en cas de purge de la source. Ce controle lexical n'est pas
un moteur reglementaire : il ne garantit pas la detection de toute regle, notamment
les valeurs ecrites en lettres, les tableaux mal extraits ou les conditions implicites.

## Rapprochements

La carte propose au plus 3 rapprochements complets concernant ses principaux et
ayant une confiance numerique d'au moins 0,80. Les autres restent repliees.
Les liens incomplets sont separes et ne proposent pas Accepter.
La recherche affiche 8 resultats au maximum par page, avec priorite aux principaux,
puis aux concepts valides, au meme document et a la meme categorie.

La creation d'une cible depuis la reparation est explicite, tracee et transactionnelle.
Elle laisse concept et lien a verifier. Un concept similaire existant bloque cette
creation et invite a choisir une cible existante ; aucun doublon n'est cree en silence.

## Compatibilite et stockage

Migration additive : `extracted_cards.extraction_details`, JSON vide par defaut,
ajoute seulement si absent apres lecture de `PRAGMA table_info`.
Il contient le mode, les propositions locales concept-carte, leurs scores et raisons,
leur decision de retention, leur identifiant de noeud lorsqu'elles sont actives,
ainsi que les regles, incertitudes et extraits utiles.
L'importance n'est pas un attribut global du noeud.

Les anciennes cartes restent sans ce profil et ne sont ni reduites ni reclassees.
Les fusions explicites conservent les details et les decisions humaines d'ignorance.
JSON et JSON-LD conservent ces informations dans les cartes ; le CSV du graphe
continue de decrire les noeuds et liens du perimetre valide. Aucun nouveau format
d'export n'est ajoute dans ce lot.

## Verification

Les tests de `backend/tests/test_salience.py` couvrent les trois modes, les scores
absents, les concepts partages, la retention explicite, les fusions, les transactions,
les passages sources, les purges, l'archive JSON et les anciennes bases.
Une recette sur copie est necessaire avant toute reevaluation de documents existants.
