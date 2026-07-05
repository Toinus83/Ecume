# ECUME

ECUME est un MVP local de capitalisation de connaissance métier sur la couche usage. Il importe des documents, propose des cartes d'effets, enrichit un graphe SQLite au fil des imports et exporte les données vers des formats simples.

## Prérequis

- Python 3.11+
- Node.js 16+
- Ollama lancé localement si tu veux l'analyse LLM automatique

## Installation

Installation automatique sous Windows :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check-prereqs.ps1
powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1
```

Le script d'installation ne reinstalle pas les paquets si l'environnement Python et `node_modules` existent deja. Pour forcer une mise a jour complete :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1 -Force
```

Pour installer aussi les dependances de test :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1 -Force -WithDev
```

Backend :

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Frontend :

```bash
cd frontend
npm install
```

Configuration :

```bash
copy .env.example .env
```

Tu peux changer `OLLAMA_MODEL` pour utiliser un autre modèle local.

## Lancement

Lancement automatique sous Windows :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-ecume.ps1
```

Backend :

```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload
```

Frontend :

```bash
cd frontend
npm run dev
```

Ouvre ensuite `http://127.0.0.1:5173`.

Pour arreter les serveurs lances par script :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop-ecume.ps1
```

## Publication Git

Le guide de publication et de recuperation sur un autre PC est dans `docs/publication_git.md`.

Pour publier vers le depot GitHub configure :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\publish-github.ps1
```

## Flux MVP

1. Importe un document `.txt`, `.md`, `.pdf` ou `.docx`.
2. Lance l'analyse. ECUME crée un job backend et affiche sa progression.
3. Tu peux changer d'onglet pendant que le backend travaille.
4. Consulte les cartes d'effets une fois le job terminé.
5. Valide, corrige, fusionne ou rattache les cartes.
6. Visualise le graphe et les orphelins.
7. Exporte en JSON, JSON-LD, CSV ou Memgraph. Les formats sont détaillés dans `docs/exports.md`.
8. Utilise l'onglet Admin pour changer de fournisseur LLM, supprimer des concepts ou réinitialiser la base.

Si Ollama ne répond pas, ECUME affiche une erreur claire. Tu peux réessayer l'analyse ou créer une carte manuellement.

## Dépannage Ollama

Si l'import affiche une erreur sur `http://localhost:11434/api/generate`, vérifie dans un terminal :

```bash
ollama serve
ollama list
ollama pull llama3.1
```

Puis relance l'analyse dans ECUME. Si Ollama utilise un autre port ou une autre machine, modifie `.env` :

```text
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
```

ECUME essaie `/api/generate`, puis `/api/chat` si le premier endpoint n'est pas disponible.

## Administration

L'onglet Admin permet de :

- choisir entre Ollama local et une API externe compatible OpenAI ;
- modifier l'URL, le modèle et la clé API ;
- tester la configuration LLM ;
- rechercher les concepts déjà en base ;
- supprimer un concept et ses liens associés ;
- réinitialiser la base locale pour les tests, avec confirmation `RESET ECUME`.

## Données locales

Les données utilisateur restent locales dans `data/` et ne doivent pas être versionnées :

- `data/uploads/`
- `data/ecume.db`
- `data/exports/`

Le `.gitignore` les exclut explicitement.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Les tests couvrent l'import d'un document, la création de noeuds et liens, la détection d'orphelins, l'export JSON et l'export Memgraph.

## Limites connues

- Le dédoublonnage est volontairement simple : libellé identique, proximité textuelle, variantes et synonymes enregistrés.
- `ApiLLMProvider` est prévu mais non implémenté.
- Le squelette RDF/SKOS est minimal.
- La fusion de concepts est disponible côté API ; l'IHM expose surtout la fusion de cartes et le rattachement d'effets.
