# Recette Echo et publication

Verification locale terminee le 14 septembre 2026. Cette livraison termine le
lot UX/reduction du bruit, conserve les corrections de coherence deja en cours
et ajoute l'atelier Echo. Le commit UX local anterieur est conserve.

## Resultats

- Backend : **203 tests passes**, 2 avertissements de depreciation FastAPI
  `on_event`, aucun echec, en 61,00 secondes lors de la derniere execution.
- TypeScript : `tsc --noEmit`, code de sortie 0.
- Frontend : Vite 4.5.14, **1 603 modules**, build reussi en 7,65 secondes.
  JS 698,11 ko (gzip 218,95 ko), CSS 22,43 ko. Avertissement non bloquant
  sur le bundle de plus de 500 ko, sans ajout de framework frontend.
- `git diff --check` : code de sortie 0. Sous Windows, Git peut signaler
  la conversion LF/CRLF ; ce n'est pas une erreur de whitespace.
- Verification des dependances Python runtime/dev : toutes presentes.
- Navigateur Edge via Playwright, ordinateur 1440 x 1000 et mobile 390 x 844 :
  import, echantillon de 8 termes, profil technique replie, correspondance
  decidee humainement puis conservee apres nouvelle recherche, telechargement
  JSON, suppression confirmee du referentiel local. Aucun plantage JavaScript
  ni debordement horizontal detecte. Captures controlees localement.
- Sur copie de base : 103 cartes, 813 concepts valides. Double initialisation
  des migrations sans changement des valeurs historiques ; seuils existants
  conserves. Recherche de lot sur les 813 concepts et 12 termes de recette :
  134 candidats, 704 concepts sans candidat, 1,22 seconde, graphe inchange.
- Empreinte du fichier de reference identique avant/apres les actions navigateur.

Commandes de verification depuis la racine :

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp=data/runtime/pytest-echo-publication
.\backend\.venv\Scripts\python.exe scripts/check-python-deps.py backend/requirements-dev.txt
git diff --check
```

Sur un poste standard, le build se lance avec `cd frontend` puis `npm run build`.
Dans l'environnement de recette Codex, le Node systeme rencontre un refus Windows
`EPERM lstat C:\Users\Toinus`. La verification a donc utilise le Node fourni par
Codex : compilation TypeScript puis API de build Vite avec le meme plugin React
et la meme racine, sans chargement du fichier de configuration par esbuild.
Ce contournement d'environnement n'est pas ajoute aux scripts du projet.

## Corrections et migrations

- Extraction sobre, importance locale concept-carte, garde-fou sur les regles
  numeriques et exceptions, sans nettoyage silencieux des anciennes donnees.
  Voir [la recette extraction](recette-extraction.md) et [les regles](extraction.md).
- Echo : quatre tables additives `reference_repositories`, `reference_terms`,
  `reference_relations`, `echo_mappings`. Profil JSON dans la fiche de reference.
- Aucun renommage ni suppression de colonne. La colonne `extraction_details`
  du lot reduction du bruit est ajoutee seulement si elle manque, apres PRAGMA.
- Operations de reference et decisions de mapping transactionnelles ; les
  decisions humaines et les concepts metier partages restent proteges.
- Import local RDFLib avec limite de taille/triplets, XML durci, aucune lecture
  distante ou dependance `owl:imports` chargee implicitement.
- Export Echo JSON et ZIP de revue CSV, rapport de controle, definitions
  supplementaires non destructives, statuts candidats/revue explicites.
- Une source utilisee uniquement par un lien est aussi incluse dans le lot,
  avec son extrait si les metadonnees du lien en contiennent un.
- Installation incrementale des nouvelles dependances Python meme si le venv
  existe ; les versions compatibles sont conservees.

## Fichiers du lot Echo

Backend et migrations :

- `backend/app/database/db.py`
- `backend/app/main.py`
- `backend/app/routers/__init__.py`
- `backend/app/routers/references.py`
- `backend/app/services/admin_service.py`
- `backend/app/services/reference_parser.py`
- `backend/app/services/reference_service.py`
- `backend/app/services/echo_mapping_service.py`
- `backend/app/services/echo_export_service.py`
- `backend/requirements.txt`

Frontend :

- `frontend/src/types.ts`
- `frontend/src/api/client.ts`
- `frontend/src/pages/ReferencesPage.tsx`
- `frontend/src/components/EchoMappings.tsx`
- `frontend/src/components/EffectCard.tsx`
- `frontend/src/styles/global.css`

Tests, installation et documentation :

- `backend/tests/test_references.py`
- `backend/tests/test_echo_mapping.py`
- `backend/tests/test_echo_exports.py`
- `backend/tests/test_dependency_check.py`
- `scripts/check-python-deps.py`
- `scripts/install-deps.ps1`
- `.gitignore`
- `README.md`
- `docs/echo.md`
- `docs/recette-echo.md`

La publication inclut aussi les fichiers des lots coherence, imports, validation,
GPU et UX deja modifies avant cette reprise. Leur liste exhaustive figure dans
le diff du commit de livraison ; ils n'ont pas ete remis a zero.

## Limites et securite de publication

La recette Echo utilise uniquement de petits referentiels synthetiques locaux.
Aucune ontologie Marine reelle n'a encore ete fournie : compatibilite des
conventions metier et reimport dans l'outil central restent a valider.
L'alignement est lexical, pas un raisonneur. Les exports Echo JSON-LD/TTL,
PPTX, ArchiMate XML et connecteurs restent differes.

Les copies de base, captures, documents, fichiers RDF de recette et exports
restent sous `data/`, exclu de Git. Aucun fichier utilisateur ni cle API n'est
ajoute au depot. `.env.example` est un exemple sans secret. Les petits exemples
RDF des tests sont des chaines synthetiques, pas des references utilisateur.
Les instances temporaires de recette utilisent des ports distincts de l'application.
