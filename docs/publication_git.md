# Publication Git de ECUME

Ce guide sert a publier le code ECUME sur un depot Git gratuit, puis a le recuperer sur un autre PC.

## Ce qui doit etre publie

A publier :

- le code source backend et frontend ;
- `README.md` ;
- `.env.example` ;
- `backend/requirements.txt` et `backend/requirements-dev.txt` ;
- `frontend/package.json` et `frontend/package-lock.json` ;
- les scripts du dossier `scripts/` ;
- la documentation du dossier `docs/`.

A ne jamais publier :

- `.env` ;
- `data/ecume.db` ;
- `data/uploads/` ;
- `data/exports/` ;
- les PDF, Word, Excel, PowerPoint ou autres documents utilisateur ;
- les cles API.

Le fichier `.gitignore` est prevu pour exclure ces donnees.

## Option recommandee

Le plus simple est GitHub :

1. Creer un compte sur https://github.com/
2. Creer un nouveau depot, par exemple `ecume`.
3. Choisir `Public` si tu veux partager le projet librement.
4. Ne pas ajouter de README depuis GitHub, car le projet en a deja un.

GitLab et Codeberg proposent aussi des depots Git gratuits.

## Premiere publication depuis ton PC

Depuis un terminal ouvert dans le dossier `ecume` :

```powershell
git init
git add .
git status
git commit -m "Initial commit ECUME"
git branch -M main
git remote add origin https://github.com/Toinus83/Ecume.git
git push -u origin main
```

Une variante plus simple existe avec le script fourni :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\publish-github.ps1
```

Le script verifie d'abord que `.env`, `data/`, `.venv` et `node_modules` sont bien ignores.

Avant `git commit`, verifier avec `git status` que les fichiers suivants ne sont pas listes :

- `.env`
- `data/ecume.db`
- `data/uploads/...`
- `data/exports/...`
- `frontend/node_modules/...`
- `backend/.venv/...`

## Recuperation sur le PC de ton ami

Sur son PC, il doit installer :

- Git for Windows ;
- Python 3.11+ ;
- Node.js LTS ;
- Ollama seulement s'il veut utiliser le LLM local.

Puis :

```powershell
git clone https://github.com/Toinus83/Ecume.git
cd ecume
powershell -ExecutionPolicy Bypass -File scripts\check-prereqs.ps1
powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1
powershell -ExecutionPolicy Bypass -File scripts\start-ecume.ps1
```

Le script `install-deps.ps1` garde les dependances deja presentes. Pour forcer une reinstall ou une mise a jour :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1 -Force
```

Les dependances de test sont optionnelles :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1 -Force -WithDev
```

L'application sera disponible ici :

```text
http://127.0.0.1:5173
```

## Mettre a jour le PC de ton ami

Quand tu publies une nouvelle version :

```powershell
git add .
git commit -m "Description courte de la modification"
git push
```

Ton ami recupere ensuite les modifications :

```powershell
git pull
powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1
powershell -ExecutionPolicy Bypass -File scripts\start-ecume.ps1
```

Relancer `install-deps.ps1` apres un `git pull` est utile si des dependances ont change.

## Arreter ECUME

Fermer les deux fenetres ouvertes par `start-ecume.ps1`, ou lancer :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop-ecume.ps1
```
