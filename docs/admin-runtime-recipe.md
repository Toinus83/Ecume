# Recette Admin et persistance runtime

Cette recette prouve que les reglages saisis dans Admin sont conserves dans le volume
`ecume-data` et relus par le backend apres recreation des conteneurs.

## 1. Demarrer ECUME

```bash
docker compose up --build -d
docker compose ps
```

Ouvrir `http://127.0.0.1:8080`, puis la page **Admin**.

## 2. Modifier la configuration

Dans **Configuration LLM**, renseigner un fournisseur, son URL, son modele et, si
necessaire, sa cle. Cliquer sur **Enregistrer**.

Dans **Interopérabilité RDF / Ontologies**, ouvrir successivement :

- **Fuseki et graphes nommes** : URL, dataset et endpoints ;
- **Echo** : source, domaine et references OWL/VOC/SHACL ;
- **OntoCast** : mode, URL, profil et jeton eventuel ;
- **Outil de revue RDF** : URL Ontosphere, endpoint SPARQL et graphe de revue.

Cliquer sur **Enregistrer l'ecosysteme RDF**. Les boutons de test enregistrent aussi le
formulaire courant avant d'appeler le backend : ils ne testent donc pas une ancienne valeur.

## 3. Verifier le masquage des secrets

```bash
curl -s http://127.0.0.1:8080/api/admin/llm
curl -s http://127.0.0.1:8080/api/admin/rdf
```

Les champs `external_llm_api_key`, `rdf_auth_secret` et `ontocast_api_token` doivent etre
vides. Seuls `has_external_llm_api_key`, `has_rdf_auth_secret` et
`has_ontocast_api_token` indiquent si une valeur existe. Ne pas afficher le contenu de
`/data/settings.env` dans un journal ou une capture.

## 4. Recreer les conteneurs

```bash
docker compose down
docker compose up -d
```

Ne pas ajouter `-v` : cette option supprimerait volontairement le volume de donnees.
Rouvrir Admin et verifier que les URL, modeles, domaines et options sont toujours presents.
Les champs secrets restent vides dans le navigateur, avec la mention qu'un secret est
enregistre.

Le fichier persistant se trouve dans `/data/settings.env` dans le backend :

```bash
docker compose exec ecume-backend sh -c 'test -s /data/settings.env && echo Configuration presente'
```

## 5. Tester les connexions

Dans Admin :

1. cliquer sur **Tester** dans le bloc LLM ;
2. cliquer sur **Tester la connexion** dans le bloc Fuseki ;
3. utiliser **Tester une requete SPARQL** pour confirmer les droits de lecture.

Le test LLM appelle `GET {URL_LLM}/models` avec la cle conservee par le backend. Le test
Fuseki execute une requete SPARQL `SELECT` sur l'endpoint configure. Aucun secret n'est
renvoye au frontend.

## 6. Preuve automatisee

Le test suivant lance deux processus Python successifs avec le meme repertoire `/data` :

```bash
python -m pytest backend/tests/test_container.py::test_container_config_paths_and_admin_settings_survive_process_restart -q
```

Il verifie les valeurs initiales de type ConfigMap, la sauvegarde Admin simulee, le
redemarrage, puis l'utilisation des valeurs persistantes par le fournisseur LLM et Fuseki.

Les tests de connexion et de non-divulgation des secrets sont :

```bash
python -m pytest backend/tests/test_rdf_ecosystem.py -q
```

## Priorite de configuration

1. La ConfigMap et le Secret Kubernetes, ou l'environnement Compose, fournissent les
   valeurs initiales et les valeurs de repli.
2. Une sauvegarde Admin ecrit les cles gerees dans `/data/settings.env`.
3. Aux demarrages suivants, ce fichier persistant surcharge les valeurs initiales pour les
   cles deja enregistrees.
4. Une variable absente du fichier continue de venir de l'environnement.

Supprimer le PVC ou lancer `docker compose down -v` supprime volontairement cette
configuration avec les autres donnees ECUME.
