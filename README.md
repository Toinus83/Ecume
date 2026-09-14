# ECUME

ECUME est un MVP local de capitalisation de connaissance métier sur la couche usage. Il importe des documents, propose des cartes d'effets, enrichit un graphe SQLite au fil des imports et exporte les données vers des formats simples.

## Pilotage des imports et validation

La page **Import** separe le chargement, l'analyse en cours et les documents importes.
La liste affiche les cartes produites et leurs statuts, sans confondre cartes et concepts.
Les actions documentaires sont repliees dans le menu **Actions**.
**Ouvrir les cartes** conserve le filtre documentaire et montre tous leurs statuts.

- **Conserver les sources** est le reglage initial. Les originaux restent dans
  `data/uploads`, le texte extrait dans SQLite.
- **Purger apres analyse reussie** retire le fichier original et le texte integral
  uniquement apres enregistrement des resultats. Ce reglage s'applique aux prochains
  imports ; chaque document peut aussi avoir sa propre regle pour sa prochaine analyse.
- **Purger la source** est une action manuelle confirmee, sans suppression des cartes,
  concepts, liens, synonymes, extraits courts ni historique. Une purge interrompue est
  recuperee au redemarrage ; un fichier verrouille reste signale comme purge a terminer.
- **Fournir a nouveau le fichier** verifie son empreinte SHA-256. Pour une ancienne
  source deja perdue et sans empreinte, il faut un nouvel import. Une relance conserve
  les cartes existantes et peut creer de nouvelles propositions : elle ne les remplace pas.
- **Supprimer** demande de saisir `SUPPRIMER`. La connaissance est conservee par defaut.
  La suppression des cartes et concepts exclusivement associes demande en plus
  `SUPPRIMER LES CONNAISSANCES`. Les concepts partages restent proteges. Une reference
  documentaire minimale (titre, nom, date, empreinte) reste dans les exports et l'historique.

La purge n'efface pas les copies deja exportees ou sauvegardees en dehors de ce flux.
SQLite reutilise l'espace libere : le fichier `.db` ne retrecit pas necessairement.
Il ne s'agit pas d'un effacement securise du disque. Aucun document de demonstration
n'est ajoute ; les tests utilisent uniquement des fichiers temporaires isoles.

La page **Cartes** met en premier ce qu'ECUME a compris, la decision attendue et
les actions **Valider / Corriger / A revoir**. Les elements associes, les sources,
les actions secondaires et les details avances restent accessibles sans encombrer la carte.
L'aide **Que dois-je faire ici ?** est repliee ; les infobulles sont aussi accessibles au clavier.
La page propose six filtres : A traiter, Validees, Auto-validees, A revoir,
Rejetees et Toutes. Les actions expliquent le changement de liste. Une carte validee
reste modifiable avec **Modifier** ; une correction remet sa validation a revoir.

Le **mode de validation** est conserve dans SQLite, independamment des parametres LLM :

| Mode | Regle sur les nouvelles analyses |
| --- | --- |
| Strict | Toutes les propositions demandent une validation humaine. |
| Assiste (defaut) | Score >= 90 % : auto-validation ; 60-90 % : a revoir ; moins de 60 % : a traiter. |
| Automatique | Score >= 60 % : auto-validation ; sinon a revoir. |

Les valeurs du tableau sont les valeurs recommandees, pas un remplacement des reglages existants.
Le bandeau montre le mode actuel et le niveau d'exigence, avec **Changer le mode**.
Les seuils sont visibles et reglables uniquement dans **Reglages avances**.
Le score est une **estimation du LLM**, pas une
probabilite calibree ni une certitude. Score absent, qualification incomplete, analyse
degradee ou interpretations concurrentes empechent l'auto-validation. Les anciennes
confiances faible/moyenne/forte ne sont pas converties artificiellement en pourcentages.
Changer de mode ne reclasse pas les cartes existantes. Dans Import, le mode et les seuils
choisis sont attaches a chaque analyse des sa mise en file, y compris pour une relance.
Le mode reste visible dans la liste documentaire ; les seuils historiques sont conserves
dans les donnees de l'analyse, sans les afficher dans le parcours principal.
Un ancien import sans instantane est indique comme tel. Les reglages choisis dans Import sont locaux a cette page ; ceux
enregistres dans Cartes servent de valeurs par defaut pour les prochaines analyses.
Les reglages avances montrent le seuil effectivement utilise : seuil haut pour Assiste,
seuil bas pour Automatique. **Retablir 90 % / 60 %** est une action explicite ;
**Conserver mes seuils** ne modifie rien. Une migration ne change jamais un reglage existant.

Dans Cartes, l'aide **Pourquoi reste-t-il des cartes a valider ?** explique les cas restants.
Elle contient l'action explicite **Appliquer aux cartes non decidees**, suivie d'un bilan.
La selection respecte document, carte source, statut et recherche.
L'action est transactionnelle ; elle conserve les validations, rejets, corrections et
mises a revoir humaines, ainsi que les cartes deja auto-validees. Un historique incertain
est protege. Les anciennes cartes sans score numerique restent inchangees et sont
comptees dans le bilan. Aucune requete LLM n'est declenchee par cette action : la
reevaluation LLM des anciennes cartes n'est pas encore disponible dans cet increment.
Les motifs d'absence d'auto-validation sont consultables dans les details des cartes.

Les rapprochements ont leurs propres scores et decisions ; les mappings techniques
restent candidats. La carte affiche un resume et **Examiner les rapprochements**.
Les propositions sont classees en fiables (estimation numerique elevee, pas une certitude),
a verifier, incompletes, ignorees/rejetees et acceptees. Un score absent n'est pas invente.
Un rapprochement incomplet reste visible, mais le bouton **Accepter** est absent.
**Choisir une cible** ou **Corriger le lien** permet de choisir les concepts et la relation, sans accepter
le lien. Le backend reverifie l'existence des concepts au clic ; si une cible a disparu
entre-temps, le rapprochement revient a revoir avec un message explicite.

La recherche de cible commence apres deux caracteres et montre au maximum huit resultats
par page, avec libelle, categorie, statut, description et provenance quand ils sont connus.
Les correspondances exactes et les synonymes enregistres arrivent avant les rapprochements
textuels. Les filtres permettent de limiter aux concepts valides, au meme document ou aux
libelles proches. **Voir plus** remplace la page courante. Cette recherche est utilisee dans
les rapprochements, le rattachement d'une carte et les orphelins ; elle ne modifie aucune connaissance.
La fusion de cartes filtre aussi sa liste a huit propositions maximum apres une recherche.

**Graphe** recherche les concepts valides par libelle, description ou synonyme et montre
leurs voisins directs et cartes sources (50 premiers resultats). Ce n'est pas un moteur
de questions libres. **Orphelins** permet de corriger, rattacher, accepter sans rattachement
ou mettre a revoir. Les corrections d'un concept partage passent par sa carte source.
Un lien non hierarchique ne remplace pas un parent hierarchique : un effet peut rester
dans cette file apres un lien `concerne`. Graphe et exports principaux partagent le meme
filtre de validation ; les orphelins a revoir en sont exclus.

Le suivi des analyses est partage entre les pages et retrouve apres rechargement.
Fermer le navigateur n'arrete pas le backend. Arreter le backend interrompt ses analyses :
elles sont signalees comme interrompues au redemarrage, pas reprises automatiquement.
Le MVP utilise un seul processus backend (pas plusieurs workers Uvicorn).

## Prérequis Techniques

- Python 3.11+
- Node.js 16+
- Ollama lancé localement si tu veux l'analyse LLM automatique

## Recuperer le projet depuis GitHub

Sur un nouveau PC, installer d'abord :

- Git for Windows : https://git-scm.com/download/win
- Python 3.11+
- Node.js LTS
- Ollama si l'analyse LLM locale est souhaitee

Puis ouvrir PowerShell et lancer :

Scripts utilises : [check-prereqs.ps1](scripts/check-prereqs.ps1), [install-deps.ps1](scripts/install-deps.ps1), [start-ecume.ps1](scripts/start-ecume.ps1).

```powershell
git clone https://github.com/Toinus83/Ecume.git
cd Ecume
powershell -ExecutionPolicy Bypass -File scripts\check-prereqs.ps1
powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1
powershell -ExecutionPolicy Bypass -File scripts\start-ecume.ps1
```

L'application sera disponible ici :

```text
http://127.0.0.1:5173
```

Les donnees locales ne sont pas fournies avec le depot GitHub : chaque utilisateur aura sa propre base SQLite, ses propres imports et ses propres exports dans `data/`.

## Installation

Installation automatique sous Windows :

Scripts utilises : [check-prereqs.ps1](scripts/check-prereqs.ps1), [install-deps.ps1](scripts/install-deps.ps1).

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check-prereqs.ps1
powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1
```

Le script verifie les versions des dependances Python, meme si l'environnement existe deja.
Il installe uniquement si une dependance manque ou ne satisfait pas la version demandee ;
les paquets deja compatibles ne sont pas reinstalles. Le frontend conserve `node_modules`
s'il existe. Pour forcer la verification complete et l'installation frontend :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1 -Force
```

Pour installer aussi les dependances de test :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1 -WithDev
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

Script utilise : [start-ecume.ps1](scripts/start-ecume.ps1).

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

Script utilise : [stop-ecume.ps1](scripts/stop-ecume.ps1).

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop-ecume.ps1
```

## Publication Git

Le guide de publication et de recuperation sur un autre PC est dans `docs/publication_git.md`.

Pour publier vers le depot GitHub configure :

Script utilise : [publish-github.ps1](scripts/publish-github.ps1).

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

En cas d'erreur CUDA `PTX ... unsupported toolchain`, le passage automatique sur processeur est desactive par defaut.
Sur Windows, le [script de lancement GPU Vulkan](scripts/start-ollama-gpu.ps1) permet d'utiliser le GPU via le moteur Vulkan fourni avec Ollama :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-ollama-gpu.ps1 -Restart
```

Lance ce script avant le backend et le frontend. `-Restart` arrete l'instance Ollama du port 11434 (et ses generations en cours), puis la relance en mode Vulkan.
Le script ne touche pas aux autres serveurs et refuse d'arreter un processus qui n'est pas Ollama.
Il verifie ensuite une generation et la presence du modele en memoire GPU. Aucun modele n'est telecharge automatiquement.
Le serveur reste en arriere-plan ; ses journaux sont dans `data/runtime/`, exclus de Git.
Apres redemarrage du PC, relance le script : les variables sont limitees au processus Ollama, sans modification permanente de Windows.
L'ouverture de l'application Ollama habituelle peut lancer une instance avec d'autres reglages : dans ce cas, relance le script avec `-Restart`.
Pour plusieurs GPU, utiliser `-GpuIndex 1` si le GPU souhaite est Vulkan1. Le modele peut etre precise avec `-Model qwen2.5-coder:7b`.

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

## Atelier Echo

L'onglet **Referentiels** permet d'importer une copie locale TTL, RDF/XML ou OWL
(serialise en RDF/XML ou Turtle), d'examiner son profil et de proposer des
correspondances avec les concepts metier valides. La reference source n'est jamais modifiee.
Une correspondance, meme a 100 %, reste candidate jusqu'a une decision humaine.

Le **lot d'enrichissement Echo** fournit un JSON autonome et un ZIP de CSV de controle,
avec sources, statuts, propositions et rapport de limites. Il doit etre relu avant tout
reimport externe : ECUME n'est pas le referentiel central.

Voir le [guide Echo](docs/echo.md) et la [recette Echo](docs/recette-echo.md).
Apres une mise a jour du code, arreter ECUME, relancer
`scripts\install-deps.ps1 -WithDev`, puis `scripts\start-ecume.ps1`.
Les migrations sont additives ; conserver une sauvegarde locale de `data/` avant mise a jour.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Les tests couvrent aussi les corrections carte/graphe/exports, les concepts partages, les decisions de rapprochement, les fusions, les migrations et les annulations transactionnelles.

Depuis la racine du projet sous PowerShell :

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest_coherence -q
```

Le dossier temporaire `.pytest_coherence/` est exclu de Git.

## Coherence Metier

Le [mode d'extraction sobre et l'importance locale des concepts](docs/extraction.md)
limitent le bruit sur les nouvelles analyses, sans reclasser les anciennes cartes
ni modifier les seuils de validation existants.

Les corrections, validations, rejets, detachements et suppressions de cartes sont executes dans des transactions backend.
Retirer un concept d'une carte conserve ses autres usages. Une correction qui change un concept partage cree une variante locale.
La suppression ou fusion globale d'un concept encore utilise par des cartes est bloquee ; la fusion de cartes reste disponible.
Les decisions de rapprochement sont persistantes. Une proposition n'est jamais exportee comme relation valide sans acceptation ; sa carte doit aussi etre validee.

La migration au demarrage ajoute `card_concepts`, `card_relations`, `link_suggestions` et `coherence_migrations`, sans supprimer ni renommer les anciennes colonnes.
Elle reconstruit les associations verifiables. Les anciennes cartes incoherentes et les rapprochements sans decision explicite sont remis a revoir, avec une trace dans le changelog.
Les marqueurs `bindings_v1` et `bindings_v2` rendent la reprise repetable, y compris apres une premiere installation du lot en cours.

Le graphe principal et les exports utilisent la connaissance validee. L'archive complete reste disponible avec `scope=all` : voir [les formats d'export](docs/exports.md).

## Limites connues

- Le dédoublonnage est volontairement simple : libellé identique, proximité textuelle, variantes et synonymes enregistrés.
- L'API LLM externe doit etre compatible avec Chat Completions et les reponses JSON.
- Les correspondances Echo sont lexicales et candidates, sans raisonneur ni validation semantique automatique.
- L'export Echo JSON-LD/TTL, PPTX et ArchiMate XML restent differes.
- La fusion de concepts est disponible côté API ; l'IHM expose surtout la fusion de cartes et le rattachement d'effets.
