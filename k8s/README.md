# ECUME sur Kubernetes

Ces manifestes constituent une base neutre a adapter a l'infrastructure cible. Ils ne
deploient ni LLM, ni Fuseki, ni OntoCast, ni Ontosphere.

Ils ont ete controles statiquement, mais n'ont pas ete appliques a un cluster dans ce
lot car `kubectl` et aucun cluster Kubernetes ne sont disponibles sur le poste de recette.

## 1. Preparer les images

Construire puis publier les images dans le registre interne, ou les charger directement
sur les noeuds d'un cluster de recette :

```bash
docker build -t registry.intra/ecume-backend:dev ./backend
docker build -t registry.intra/ecume-frontend:dev ./frontend
docker push registry.intra/ecume-backend:dev
docker push registry.intra/ecume-frontend:dev
kubectl set image -n ecume deployment/ecume-backend backend=registry.intra/ecume-backend:dev
kubectl set image -n ecume deployment/ecume-frontend frontend=registry.intra/ecume-frontend:dev
```

Pour un cluster hors ligne, utiliser `docker save`/`docker load` ou l'outil d'import
d'images fourni par la distribution Kubernetes.

## 2. Adapter la configuration

Modifier avant deploiement :

- `configmap.yaml` : host CORS, LLM, URLs des services et noms de graphes ;
- `pvc.yaml` : taille et `storageClassName` si l'infrastructure l'exige ;
- les deux Deployments : noms d'images et `imagePullPolicy` ;
- `ingress.example.yaml` : host, TLS et annotations propres au controleur.

Le frontend est expose seul par l'Ingress. Il sert l'application et transmet `/api` au
service `ecume-backend`. Le navigateur n'a donc pas besoin de connaitre le DNS interne
Kubernetes.

## 3. Creer les secrets, si necessaire

Ne jamais appliquer ni modifier directement l'exemple versionne :

```bash
cp k8s/secret.example.yaml k8s/secret.local.yaml
# Editer secret.local.yaml, retirer les cles inutiles et remplacer tous les REPLACE_ME.
kubectl apply -f k8s/secret.local.yaml
```

`secret.local.yaml` est ignore par Git. Si aucun service protege n'est utilise, ne pas
creer ce Secret : sa reference est optionnelle dans le backend.

## 4. Appliquer les manifestes

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

L'Ingress ne fixe aucune `ingressClassName`. Il faut la definir selon le cluster, par
exemple `nginx` ou `traefik`, ainsi que la configuration TLS.

## 5. Verifier

```bash
kubectl get pods,svc,pvc,ingress -n ecume
kubectl rollout status -n ecume deployment/ecume-backend
kubectl rollout status -n ecume deployment/ecume-frontend
kubectl logs -n ecume deploy/ecume-backend
kubectl logs -n ecume deploy/ecume-frontend
kubectl port-forward -n ecume svc/ecume-frontend 8080:80
```

Ouvrir `http://127.0.0.1:8080`. Le test direct du backend peut se faire avec :

```bash
kubectl port-forward -n ecume svc/ecume-backend 8000:8000
curl http://127.0.0.1:8000/health
```

## Persistance et limites

Le PVC `ecume-data` est monte sur `/data`. Il contient la base, les reglages persistants,
les sources conservees et les exports. `/tmp` utilise un `emptyDir` ephemere.

**SQLite impose une replique backend unique en V1.** Ne pas augmenter `replicas` sans
migration vers un stockage concurrent adapte. Le PVC est `ReadWriteOnce` et la strategie
backend est `Recreate` pour eviter deux processus ecrivant simultanement.

En V1, si SQLite est utilise, le backend doit rester a une seule replique. Pour une montee
en charge future, prevoir un stockage adapte comme PostgreSQL.

La purge documentaire reste geree par ECUME : supprimer un fichier source ne supprime
pas les concepts, cartes, relations ou extraits courts deja capitalises.

## Integrations

Toutes les integrations sont desactivees par defaut. Configurer les URL non sensibles
dans la ConfigMap et les identifiants dans un Secret. Garder Fuseki en lecture seule ou
en ecriture limitee aux graphes candidats. ECUME produit des propositions d'enrichissement
et ne modifie jamais directement un referentiel Echo source.
