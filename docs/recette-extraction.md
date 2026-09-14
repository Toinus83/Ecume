# Bilan du lot extraction sobre

## Perimetre

Lot poursuivi sans repartir de zero. Aucun commit ni push. Aucun travail sur les
referentiels RDF/TTL/OWL, PPTX ou nouveaux formats d'export.
Les modifications des lots precedents, deja presentes dans le depot, sont conservees.

Les regles de fonctionnement et la migration sont detaillees dans [extraction.md](extraction.md).

## Fichiers de ce lot

Backend :

- `backend/app/database/db.py`
- `backend/app/llm/prompt.py`
- `backend/app/llm/ollama.py`
- `backend/app/llm/api.py`
- `backend/app/main.py`
- `backend/app/models/schemas.py`
- `backend/app/services/salience_service.py` (nouveau)
- `backend/app/services/analysis_service.py`
- `backend/app/services/card_service.py`
- `backend/app/services/coherence_service.py`
- `backend/app/services/validation_service.py`
- `backend/app/services/graph_service.py`
- `backend/app/services/job_service.py`
- `backend/app/services/serialization.py`

Frontend :

- `frontend/src/App.tsx`
- `frontend/src/types.ts`
- `frontend/src/api/client.ts`
- `frontend/src/components/CardConcepts.tsx` (nouveau)
- `frontend/src/components/EffectCard.tsx`
- `frontend/src/components/ConceptSearch.tsx`
- `frontend/src/components/SuggestionRepair.tsx`
- `frontend/src/components/DocumentLibrary.tsx`
- `frontend/src/pages/ImportPage.tsx`
- `frontend/src/pages/CardsPage.tsx`
- `frontend/src/pages/OrphansPage.tsx`
- `frontend/src/styles/global.css`

Tests et documentation :

- `backend/tests/test_salience.py` (nouveau, 37 cas)
- `backend/tests/test_documents.py` (signature du double d'analyse)
- `backend/tests/test_validation_cycle.py` (signature du double d'analyse)
- `README.md`
- `docs/extraction.md` (nouveau)
- `docs/recette-extraction.md` (ce bilan)

Plusieurs fichiers listes etaient deja non suivis ou modifies avant ce lot.
Cette liste decrit le perimetre du lot, pas uniquement les differences par rapport au dernier commit.

## Migration

Une seule colonne ajoutee pour ce lot : `extracted_cards.extraction_details`,
de type TEXT, non nulle, avec valeur par defaut `{}`.
Verification par `PRAGMA table_info` avant ajout ; aucun renommage ni suppression.
Pas de reclassement des anciennes cartes, ni modification de leurs seuils.

## Verification backend

Commande finale depuis la racine :

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q --basetemp=data/runtime/pytest-salience-release
```

Resultat : **170 passed, 2 warnings in 102.74s**.
Les deux avertissements concernent `FastAPI.on_event`, deja utilise dans le projet.

Les cas couvrent notamment la selection 4/8/14, les scores absents ou invalides,
la protection des concepts partages, les decisions explicites, les fusions,
les annulations transactionnelles, les anciennes bases, les extraits reglementaires,
la purge, l'archive JSON et la creation prudente d'une cible de rapprochement.

## Verification frontend

- TypeScript : `tsc --noEmit`, code de sortie 0.
- Vite 4.5.14 : build de production reussi, 1602 modules, 5.67 secondes.
- Fichier JavaScript principal : 687,47 kB, 216,20 kB compresse gzip.
- Avertissement non bloquant : fichier JavaScript superieur a 500 kB.

Le runtime Node integre a ete utilise. Le chargement standard de la configuration
Vite par esbuild rencontre une restriction d'acces Windows dans l'environnement
d'execution de Codex. Le build a donc utilise l'API Vite avec les memes options de
production (racine frontend, plugin React), sans changer la configuration du projet.

Playwright / Edge, tailles 1440 x 1000 et 390 x 844 :

- principaux visibles et secondaires replies ;
- actions Valider / Corriger / A revoir ;
- maximum de trois rapprochements prioritaires ;
- lien incomplet sans bouton Accepter, avec recherche et creation a verifier ;
- maximum de huit cibles par page ;
- trois modes d'extraction et valeur Sobre au chargement ;
- documents importes charges, navigation revenant en haut de page ;
- aucun debordement horizontal et aucune exception JavaScript detectee.

## Recette sur copie et LLM

Copie realisee avec SQLite backup, original ouvert en lecture seule.
Deux initialisations successives ont conserve toutes les valeurs preexistantes
(103 cartes), ainsi que le mode Automatique et les seuils 1,00 / 0,28.
Trois essais controles sur des concepts deja presents dans le reglement ont retenu
respectivement 4, 8 et 14 concepts associes. Ces qualifications de recette ne sont
pas des decisions appliquees a la base originale.

Deux essais reels avec Ollama local `qwen2.5-coder:7b` ont porte sur un extrait
de 5000 caracteres du reglement fourni, sans appel a une API externe.
Ils ont confirme une extraction courte, mais variable : certains scores ou roles
restent imparfaits, et des valeurs chiffrees peuvent manquer dans la synthese.
Le controle complementaire a conserve les passages omis concernant notamment
hauteurs, surfaces et besoins en eau. Ces passages restent a verifier.

Les bases de recette, scripts temporaires, journaux et captures sont sous
`data/runtime/`, exclu de Git. Aucun document de demonstration n'a ete ajoute.

## Limites

- L'importance declaree par le LLM reste une proposition. Si les scores ou la
  justification manquent, un concept peut rester secondaire, meme s'il est utile.
- Le garde-fou lexical n'est pas un controle exhaustif de reglement ; il peut
  demander des verifications supplementaires et manquer des regles implicites.
- La recette LLM porte sur un extrait, pas sur une nouvelle analyse complete du PLU.
- Les anciennes analyses restent volontairement telles quelles.
- Le lot ne resout pas les restrictions de droits du runtime Node systeme de Codex.

Controle final : `git diff --check`, code de sortie 0, aucune erreur d'espacement.
Les 21 nouveaux fichiers du depot ont aussi ete verifies avec
`git diff --no-index --check` : aucune erreur d'espacement.
