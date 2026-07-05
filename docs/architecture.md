# Architecture ECUME

ECUME est séparé en deux applications locales.

- `backend/` expose une API FastAPI, stocke les données dans SQLite et appelle le fournisseur LLM.
- `frontend/` expose l'IHM React/Vite avec cartes d'effets, graphe, orphelins et exports.
- `data/` contient les fichiers locaux non versionnés : uploads, base SQLite et exports.

Le backend garde une abstraction LLM :

- `LLMProvider` définit le contrat.
- `OllamaProvider` appelle l'API HTTP Ollama.
- `ApiLLMProvider` est un point d'extension pour une API externe.

L'analyse fonctionne par imports successifs. Avant de créer un concept, ECUME compare le libellé avec les noeuds et alias existants. Les concepts identiques ou proches sont rattachés comme variantes ou proposés comme rapprochements, afin de limiter les doublons.

Les gros documents sont découpés en chunks avant l'appel au LLM. Les cartes issues des chunks sont ensuite consolidées.

Chaque création, fusion, changement de statut ou alias est enregistré dans `change_log`.
