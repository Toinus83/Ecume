# Deployer ECUME avec Docker et Kubernetes

Ce guide couvre les deux images separees frontend/backend. Le conteneur unique hors
ligne reste disponible dans [deploiement-hors-ligne.md](deploiement-hors-ligne.md).
Les services LLM, Fuseki, OntoCast et Ontosphere sont facultatifs et desactives par
defaut. ECUME reste utilisable sans eux, avec les limites indiquees dans l'interface.

## Prerequis

- Git pour recuperer le depot ;
- Docker Engine ou Docker Desktop ;
- Docker Compose v2 (`docker compose`) ;
- Python 3.10 ou plus recent pour la recette automatisee ;
- `kubectl` uniquement pour adapter et deployer les manifestes Kubernetes.

La configuration fonctionnelle est detaillee dans [configuration.md](configuration.md).

## Lancement Docker Compose

```bash
docker compose up --build
```

- application : `http://127.0.0.1:8080`
- documentation backend : `http://127.0.0.1:8000/docs`
- sante backend : `http://127.0.0.1:8000/health`

Le navigateur appelle uniquement `/api`. Nginx applique la route
`/api -> ecume-backend:8000` sur le reseau Compose : aucune URL
`127.0.0.1:8000` n'est embarquee dans le frontend conteneurise et aucun reglage CORS
n'est necessaire pour le parcours normal.

Les donnees sont conservees dans le volume Docker `ecume-data`. Ne pas utiliser
`docker compose down -v` si elles doivent etre preservees.

Par defaut, `LLM_ENABLED=false` : ECUME utilise immediatement son extraction locale
simple, sans tenter de contacter Ollama ou une API. Un LLM peut ensuite etre active et
configure dans **Admin**, sans modifier ni reconstruire le code.

Pour utiliser un LLM ou un service externe, creer un fichier `.env` local a cote de
`docker-compose.yml`. Ce fichier est ignore par Git. Exemple pour un LLM compatible
avec l'API configuree dans ECUME :

```text
LLM_ENABLED=true
LLM_PROVIDER=api
LLM_API_URL=http://llm.intra.example/v1
LLM_MODEL=modele-interne
LLM_API_KEY=remplacer-localement
```

La configuration peut aussi etre saisie dans **Admin**. Elle est alors conservee dans
`/data/settings.env`, sur le volume persistant. Proteger ce volume comme un secret.

Les noms de variables utilisables avec Compose sont regroupes dans `.env.example`.
L'interface Admin sauvegarde ses reglages canoniques dans `/data/settings.env`.

## Recette automatisee de bout en bout

Sur une machine equipee de Docker avec Compose v2 :

```bash
python scripts/smoke-compose.py
```

Cette recette construit les deux images dans un projet Docker isole, verifie le frontend
et ses pages, appelle le backend uniquement par le proxy `/api`, lit Admin, importe un
document temporaire, lance l'analyse locale, valide une proposition, telecharge les
exports puis recree les conteneurs pour verifier la base, le concept et la configuration
persistants. Le volume et les conteneurs de recette sont supprimes a la fin. Utiliser
`--keep` uniquement pour diagnostiquer un echec.

## Construire les images

```bash
docker build -t ecume-backend:dev ./backend
docker build -t ecume-frontend:dev ./frontend
```

Le frontend utilise `/api` par defaut. Nginx transmet ce chemin au backend. Au
demarrage, `ECUME_API_URL` genere `config.js`, ce qui permet de changer l'URL publique
sans reconstruire l'image. `ECUME_BACKEND_UPSTREAM` indique la destination interne du
proxy et vaut `http://ecume-backend:8000` par defaut.

Pour une infrastructure sans acces Internet, construire les images sur une machine
connectee, puis les transferer :

```bash
docker save ecume-backend:dev ecume-frontend:dev -o ecume-images.tar
docker load -i ecume-images.tar
```

Les images de base et dependances ne sont necessaires qu'au build, pas au demarrage des
images deja chargees.

## Deployer dans Kubernetes

Les manifestes sont detailles dans [le README Kubernetes](../k8s/README.md). Adapter
d'abord les images, le host Ingress, les URL internes et la classe de stockage.

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/backend-service.yaml
kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/frontend-service.yaml
kubectl apply -f k8s/ingress.example.yaml
```

Ne pas appliquer `secret.example.yaml`. Le copier vers `secret.local.yaml`, renseigner
uniquement les secrets necessaires, puis appliquer cette copie locale. Le fichier local
est ignore par Git.

## Persistance et SQLite

Le PVC monte `/data` et conserve :

- la base SQLite ;
- les reglages Admin persistants ;
- les sources tant qu'elles ne sont pas purgees ;
- les exports produits.

`/tmp` reste ephemere. La politique de purge ECUME continue de determiner si les
documents sources doivent rester dans `/data`. Purger une source ne supprime pas la
connaissance validee.

Avec SQLite, utiliser **une seule replique backend**. Le manifeste impose `replicas: 1`
et une strategie `Recreate`. Une mise a l'echelle horizontale demandera une base adaptee
et une evolution explicite de l'application.

## Services optionnels

- **LLM distant** : configurer fournisseur, URL, modele et cle dans Admin ou via les
  variables `EXTERNAL_LLM_*`.
- **Fuseki** : laisser `ECUME_FUSEKI_ENABLED=false` tant que le serveur, le dataset,
  l'authentification et les graphes nommes n'ont pas ete valides.
- **Echo** : les graphes OWL, VOC et SHACL sont des references. ECUME ne modifie jamais
  directement les fichiers Echo sources.
- **OntoCast** : laisser `ECUME_ONTOCAST_ENABLED=false` sans service disponible.
- **Ontosphere** : laisser `ECUME_ONTOSPHERE_ENABLED=false` sans URL de revue valide.

Les noms de graphes se reglent dans `k8s/configmap.yaml`. Les identifiants et jetons
restent exclusivement dans un Secret Kubernetes ou dans un gestionnaire de secrets.

OntoCast est encore un contrat preparatoire : tant que son API n'est pas stabilisee,
aucun document n'est envoye automatiquement et le traitement local ECUME reste actif.
Ontosphere est un outil externe de revue ; ECUME prepare des liens, graphes et exports,
mais ne pilote pas directement cet outil.

## Verification

```bash
kubectl get pods -n ecume
kubectl get svc -n ecume
kubectl get ingress -n ecume
kubectl logs -n ecume deploy/ecume-backend
kubectl logs -n ecume deploy/ecume-frontend
kubectl port-forward -n ecume svc/ecume-frontend 8080:80
```

Ouvrir ensuite `http://127.0.0.1:8080`. Le backend doit repondre sur `/api/health`
depuis cette origine. Les probes utilisent `/health` pour le backend et `/healthz` pour
le frontend.

## Securite

- ne jamais versionner `.env`, `secret.local.yaml`, base SQLite, uploads ou exports ;
- remplacer les placeholders avant de creer un Secret ;
- limiter l'acces au PVC, car les reglages Admin peuvent contenir une cle API ;
- exposer l'application en HTTPS sur une infrastructure partagee ;
- conserver Fuseki et les integrations en lecture seule tant que les droits ne sont pas
  explicitement valides.

Les Dockerfiles n'embarquent ni `data/`, ni environnement Python local, ni
`node_modules`, ni secret. Le backend s'execute sans privilege et avec un systeme de
fichiers racine en lecture seule dans Compose et Kubernetes.
