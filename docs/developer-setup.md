# Developper ECUME sans Docker

Ce guide permet de lancer ECUME localement avec Python, Node.js et VS Code. Docker reste
optionnel.

## Prerequis

- Git ;
- Python 3.11 ou plus recent ;
- Node.js LTS et npm ;
- VS Code recommande ;
- Docker optionnel.

## Cloner le depot

```powershell
git clone https://github.com/Toinus83/Ecume.git
cd Ecume
code .
```

VS Code propose automatiquement les extensions utiles au projet. Les fichiers du dossier
`.vscode` ne contiennent aucun chemin personnel et aucun secret.

## Lancer le backend sans Docker

Dans un premier terminal PowerShell :

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Pour installer aussi Pytest et utiliser les taches de test VS Code :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Le backend et sa documentation interactive sont disponibles sur
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Lancer le frontend sans Docker

Dans un second terminal PowerShell, depuis la racine du depot :

```powershell
cd frontend
npm install
npm run dev
```

Ouvrir [http://127.0.0.1:5173](http://127.0.0.1:5173).

Dans VS Code, les memes commandes sont disponibles avec **Terminal > Run Task**. Le
backend peut aussi etre lance avec **Run and Debug > ECUME: Debug backend FastAPI**.

## Ports utilises

- frontend : `5173` ;
- backend : `8000`.

Pour identifier puis arreter un processus qui occupe un port sous Windows :

```powershell
netstat -ano | findstr :8000
netstat -ano | findstr :5173
taskkill /PID <PID> /F
```

Remplacer `<PID>` par le numero affiche par `netstat`. Fermer proprement un serveur avec
`Ctrl+C` reste preferable lorsque son terminal est accessible.

## Configuration

Le fichier `.env.example` sert uniquement de modele documente. Un fichier `.env` reel ne
doit jamais etre commite. Les cles, jetons, documents importes, bases locales et exports
restent hors du depot.

Le LLM, Fuseki, Echo, OntoCast et Ontosphere peuvent etre configures dans la page
**Admin**. ECUME fonctionne aussi sans ces services, avec SQLite et l'analyse locale
simple. Voir le [guide de configuration](configuration.md) pour le detail.

## Difference entre les modes

### Mode developpeur VS Code

Python lance FastAPI sur le port `8000` et npm lance Vite sur le port `5173`. Ce mode est
le plus simple pour debugger le backend et modifier le frontend.

### Mode Docker Compose

`docker compose up --build` construit deux conteneurs. Le frontend nginx appelle le
backend via `/api` et les donnees persistent dans le volume `ecume-data`. Ce mode est le
plus proche d'un deploiement reproductible.

### Mode Kubernetes

Les manifestes du dossier `k8s/` utilisent une ConfigMap, un Secret et un PVC. Ce mode
est destine a l'infrastructure on-premise ; le backend SQLite reste limite a une seule
replique.
