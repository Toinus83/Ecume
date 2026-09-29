# ECUME : un conteneur, deploiement hors ligne

## Perimetre

Un seul conteneur **ECUME** contient le frontend compile, FastAPI, SQLite et les
dependances Python, y compris pySHACL. Une seule adresse HTTP, port 8080 : interface
a `/`, API a `/api`. Aucune installation npm/pip ni telechargement au demarrage.
Le frontend principal n'utilise pas de CDN. La documentation technique Swagger
de FastAPI, distincte de l'interface ECUME, peut referencer des CDN.

**Ollama et ses modeles ne sont pas inclus.** L'analyse utilise un service LLM deja
disponible sur le reseau interne (Ollama ou API compatible). Sans LLM, la consultation,
les corrections, les exports et les fonctions manuelles restent disponibles ;
l'analyse LLM echoue avec un message. Il faut preparer separement le serveur LLM,
ses poids et eventuels pilotes GPU avant de couper son acces Internet.
ECUME lui-meme n'a pas besoin d'acces GPU.

Cible par defaut : **Linux x86-64 (`linux/amd64`)**, Docker Engine et Compose v2.
Configuration de livraison : **API LLM externe au conteneur ECUME**, accessible
sur le reseau interne. Renseigner URL, modele et cle dans le `.env` de la cible.
Windows peut preparer/tester avec Docker Desktop en mode conteneurs Linux.
ARM64 est selectionnable, mais exige la meme verification sur l'architecture cible.
Un Docker en mode conteneurs Windows ne peut pas executer cette image Linux.

Ce guide et le packaging sont prepares dans le depot. Le test reel de l'image
doit etre execute sur une machine equipee de Docker ; aucune image construite
ou certifiee n'est livree simplement en clonant le code.

## 1. Construire sur une machine connectee

Prerequis : depot ECUME, Python 3.10+ et Docker avec moteur Linux operationnel.
Node et Python de l'application sont installes dans les etapes de construction,
pas a installer sur la machine cible. Les images de base et les dependances sont
telechargees **ici**, pendant la preparation connectee.

Depuis la racine du depot, dans PowerShell :

```powershell
python scripts/package-offline.py --image ecume:offline --platform linux/amd64
```

Ou avec l'environnement deja installe dans le projet :

```powershell
.\backend\.venv\Scripts\python.exe scripts/package-offline.py --image ecume:offline
```

Linux : meme commande avec `python3` a la place de `python`.
Pour une livraison versionnee, utiliser par exemple `--image ecume:recette-20260916`
et `--output dist-offline/recette-20260916`. Le dossier cible doit etre nouveau.

Le script :
1. Construit l'image multi-etapes avec une liste stricte de fichiers autorises.
2. Lance un conteneur temporaire **sans reseau**, non root et en lecture seule,
   avec son propre volume de test.
3. Verifie interface/assets, API, pySHACL, creation/export d'un concept de test.
4. Recree le conteneur pour verifier la persistance des donnees et reglages Admin.
5. Supprime uniquement son conteneur et son volume de test.
6. Sauvegarde l'image et prepare `dist-offline/ecume-offline/` avec :
   `ecume-image.tar`, `compose.yaml`, `.env.example`, `README.md`,
   `SHA256SUMS` et `manifest.json`.

Il n'existe pas d'option pour ignorer un smoke test en echec. Si Docker n'est pas
disponible, aucune image n'est pretendue construite. Les tests sans reseau ne
valident pas la connexion au LLM interne, a tester ensuite sur l'infrastructure.

Le manifeste indique l'image, son identifiant, la plateforme, le commit source,
l'existence eventuelle de modifications non commitees et les empreintes de fichiers.
Une empreinte detecte une alteration accidentelle ; ce n'est pas une signature.
Les images de base ont des tags de version, pas des digests figes : une nouvelle
construction peut obtenir des correctifs differents. L'archive livree fixe les
octets deployes ; conserver son manifeste avec elle.

**Aucune base locale, source importee, export utilisateur, cle API ou modele LLM
n'entre dans l'image ou dans le dossier de livraison.** Ne pas ajouter votre
`.env` reel au dossier avant le transfert, sauf canal securise explicitement gere.

## 2. Transferer vers le reseau isole

Transferer le dossier de livraison complet par le canal autorise de votre
organisation. Docker Engine et Compose doivent deja etre installes sur la cible ;
leurs paquets d'installation et dependances sont a prevoir separement si necessaire.
Ne pas reconstruire l'image sur la cible deconnectee et ne pas lancer `docker pull`.

Depuis le dossier transfere, Linux :

```sh
sha256sum -c SHA256SUMS
docker load --input ecume-image.tar
cp .env.example .env
chmod 600 .env
```

Sous PowerShell, verifier les empreintes avec `Get-FileHash -Algorithm SHA256`
et les comparer a `SHA256SUMS`, puis :

```powershell
docker load --input ecume-image.tar
Copy-Item .env.example .env
```

## 3. Configurer le LLM interne

Editer `.env` a cote de `compose.yaml` avant le premier lancement. Par defaut,
`LLM_ENABLED=false` conserve l'analyse locale simple et ne contacte aucun service LLM :

```text
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://serveur-llm.interne:11434
OLLAMA_MODEL=nom-exact-du-modele-deja-installe
```

Pour une API interne compatible :

```text
LLM_PROVIDER=api
EXTERNAL_LLM_BASE_URL=http://serveur-llm.interne:8000/v1
EXTERNAL_LLM_MODEL=nom-du-modele
EXTERNAL_LLM_API_KEY=cle-interne
```

Ne jamais publier la cle. Si une autorite de certification interne est necessaire,
faire configurer son certificat de confiance dans le conteneur selon les regles
de l'infrastructure ; ne pas desactiver la verification TLS.

Le connecteur actuel utilise `/chat/completions`, avec `response_format=json_object`,
et exige une URL, un modele et une cle non vides. Une API d'un autre protocole ou
sans authentification demande une adaptation explicite ; ne pas inventer une cle.
En mode API, le bouton Tester controle actuellement la presence de ces trois
champs, pas une requete reelle au modele. Une analyse d'un petit document est
necessaire pour verifier effectivement la connexion et la compatibilite.

`localhost` dans un conteneur designe **le conteneur**, pas le serveur Docker.
`host.docker.internal` est configure pour joindre l'hote. Un Ollama lie uniquement
a `127.0.0.1` de l'hote peut rester inaccessible depuis le reseau Docker, notamment
sous Linux. Preferer l'adresse interne du service accessible, avec un pare-feu
limitant l'acces. Ne pas exposer Ollama publiquement.

Les modifications LLM faites dans **Admin** sont sauvegardees dans
`/data/settings.env` et persistent. Comme en local, ce fichier sauvegarde prend
ensuite priorite sur les valeurs LLM initiales de l'environnement. Pour changer
ces reglages, privilegier Admin ; modifier seulement le `.env` de Compose apres
une sauvegarde Admin ne remplace pas automatiquement cette configuration.

## 4. Demarrer hors ligne

Dans le dossier contenant la livraison et le `.env` configure :

```sh
docker compose up -d --pull never --no-build
docker compose ps
docker compose logs --tail 80 ecume
```

Ouvrir `http://127.0.0.1:8080` sur l'hote Docker. Le port peut etre change avec
`ECUME_PORT` si 8080 est deja utilise. Le compose n'a aucune etape `build` et sa
politique de telechargement est `never` : une image absente est une erreur claire.

Le statut healthy teste l'API ECUME, **pas le LLM**. Dans Admin, verifier la
configuration, enregistrer puis Tester. Importer ensuite un petit document fourni
par l'utilisateur, valider une carte et verifier un export avant un gros document.

## 5. Acces depuis un autre poste et securite

Par defaut seul l'hote peut acceder au port publie (`127.0.0.1`). ECUME MVP ne
possede pas d'authentification ni de roles ; tout utilisateur qui atteint l'API
peut acceder aux donnees et aux fonctions Admin/RAZ. **Un reseau sans Internet
n'est pas, a lui seul, un controle d'acces.**

Pour une recette distante, privilegier un tunnel SSH vers le port local, ou un
reverse proxy deja gere par votre infrastructure avec authentification et TLS.
Pour une ouverture directe temporaire sur un reseau de test de confiance,
`ECUME_BIND_IP` peut etre l'adresse LAN de l'hote, sous filtrage pare-feu strict.
Ne pas ouvrir sur toutes les interfaces sans protection.

Les flux necessaires sont navigateur -> ECUME et ECUME -> LLM interne. Aucun
flux Internet n'est requis a l'execution. Docker/Compose n'est pas un pare-feu
d'egress : appliquer les restrictions reseau au niveau de l'infrastructure.
Le script de recette prouve seulement que le demarrage et les fonctions testees
fonctionnent sans reseau ; une analyse necessite l'acces au service LLM interne.

## 6. Persistance, sauvegarde et mise a jour

Le volume nomme `ecume_ecume-data` contient SQLite, uploads, exports et reglages
LLM. Le processus utilise UID/GID 10001. Le volume neuf est initialise avec les
droits de l'image ; si vous le remplacez par un bind mount, preparer ses droits
avant demarrage. Une erreur de permission ne doit pas etre resolue par `chmod 777`.

Un seul conteneur et un seul worker : ne pas partager SQLite entre plusieurs
repliques. Les analyses en cours peuvent etre interrompues par un arret et sont
signalees au redemarrage ; terminer les analyses avant une maintenance.

Arret sans suppression de donnees :

```sh
docker compose stop
```

Sauvegarde coherente, application arretee (le dossier `backup` est a creer) :

```sh
docker compose cp ecume:/data/. ./backup/
docker compose start
```

La sauvegarde contient aussi des secrets dans `settings.env` : proteger son acces.
Une archive JSON n'est pas un remplacement de cette sauvegarde complete.
Ne pas utiliser `docker compose down -v` : `-v` supprime les volumes et leurs donnees.
Ne pas utiliser la RAZ pour mettre l'image a jour.

Mise a jour : sauvegarder a l'arret, charger la nouvelle archive avec `docker load`,
modifier `ECUME_IMAGE` si le tag change, puis :

```sh
docker compose up -d --pull never --no-build --force-recreate
```

Conserver la meme identite Compose et le meme volume. Les migrations applicatives
s'executent au demarrage. Un retour arriere exige une image et une sauvegarde de
donnees compatibles ; ne pas supposer qu'une ancienne image comprend une base migree.

## 7. Recette attendue sur l'infrastructure

- [ ] Bonne architecture, archive integre, moteur Docker et Compose disponibles.
- [ ] Aucun telechargement au lancement ; conteneur healthy.
- [ ] Interface, graphe et exports disponibles depuis le poste de test autorise.
- [ ] Test LLM interne reussi ; modele deja installe et GPU verifie cote service LLM.
- [ ] Import d'un document personnel et analyse complete.
- [ ] Import des trois couches Echo et controles SHACL simples.
- [ ] Donnees et configuration conservees apres recreation du conteneur.
- [ ] Sauvegarde arretee realisee et procedure de restauration examinee avec l'admin.
- [ ] Acces Admin/RAZ non expose a des utilisateurs non autorises.

## Verification locale du packaging, 16 septembre 2026

- Suite backend : 241 tests reussis, dont 14 nouveaux tests du point d'entree,
  de la persistance et du script de livraison. Deux avertissements FastAPI
  `on_event` deja connus, aucun echec.
- TypeScript : succes. Frontend compile avec `VITE_API_URL=/api` : succes
  (Vite via le Node fourni par Codex, avertissement de taille de bundle connu).
- Navigateur Edge : pages principales testees sur une base temporaire isolee,
  desktop/mobile, 19 appels API sur la meme origine, aucune requete externe
  observee, aucune erreur JavaScript ni erreur HTTP sur l'API et les assets testes.
  Le navigateur demande aussi un favicon absent (404 sans impact fonctionnel).
- YAML Compose lu et verifie structurellement ; `git diff --check` reussi.
- **Docker absent de la machine de verification : pas de build Docker execute,
  pas de smoke test en conteneur execute, pas d'archive image produite.**
  Les tests Python ne remplacent pas ces verifications. Le script impose ces
  controles lors de la fabrication du paquet sur une machine equipee.

References officielles : [docker image save](https://docs.docker.com/reference/cli/docker/image/save/),
[docker image load](https://docs.docker.com/reference/cli/docker/image/load/),
[services Compose](https://docs.docker.com/reference/compose-file/services/).
