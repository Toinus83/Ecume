# Configurer ECUME

ECUME fonctionne seul par defaut. Les integrations enrichissent le traitement, mais ne
sont pas requises pour importer un document, effectuer une extraction locale, valider
des concepts et produire les exports.

Copier `.env.example` vers `.env` uniquement pour une configuration Docker locale.
`.env` est ignore par Git. En Kubernetes, placer les valeurs non sensibles dans la
ConfigMap et les cles ou jetons dans un Secret ou un gestionnaire de secrets.

## Mode local par defaut

- `LLM_ENABLED=false` : extraction locale simple, sans appel reseau ;
- `FUSEKI_ENABLED=false` ;
- `ONTOCAST_ENABLED=false` ;
- Ontosphere non configure ;
- SQLite dans `/data/ecume.db` ;
- sources conservees, reglages Admin et exports sous `/data`.

`DATA_DIR` change le repertoire en lancement natif. `DATABASE_URL` accepte actuellement
un chemin ou une URL SQLite de forme `sqlite:////data/ecume.db`. PostgreSQL n'est pas
encore pris en charge par cette V1.

Le frontend conteneurise utilise `ECUME_API_URL=/api`. Nginx transmet `/api` au service
backend ; il n'est normalement pas necessaire de modifier cette valeur.

## LLM local ou distant

Le LLM se configure dans **Admin > Configuration LLM** ou par variables :

```text
LLM_ENABLED=true
LLM_PROVIDER=api
LLM_API_URL=http://llm.intra.example/v1
LLM_API_KEY=changeme
LLM_MODEL=modele-interne
```

Pour Ollama, utiliser `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL` et `OLLAMA_MODEL`.
La valeur `changeme` est un placeholder, jamais une cle fonctionnelle. Ne placer aucun
secret reel dans `.env.example`. En Kubernetes, renseigner `EXTERNAL_LLM_API_KEY` dans
`secret.local.yaml` ou dans le gestionnaire de secrets de l'infrastructure.

Quand le LLM est desactive, le bouton de test Admin confirme le mode local et aucune
connexion LLM n'est tentee.

## Fuseki et Echo

Fuseki est desactive par defaut. La V1 est configuree en lecture seule et n'active aucune
ecriture validee. Les variables principales sont :

```text
FUSEKI_ENABLED=false
FUSEKI_BASE_URL=http://fuseki:3030
FUSEKI_DATASET=ecume
FUSEKI_QUERY_ENDPOINT=/query
FUSEKI_UPDATE_ENDPOINT=/update
FUSEKI_WRITE_MODE=disabled
```

Les graphes de reference sont :

- `FUSEKI_GRAPH_ECHO_OWL` ;
- `FUSEKI_GRAPH_ECHO_VOC` ;
- `FUSEKI_GRAPH_ECHO_SHACL`.

Les graphes de travail ECUME sont :

- `FUSEKI_GRAPH_ECUME_CANDIDATES` ;
- `FUSEKI_GRAPH_ECUME_VALIDATED` ;
- `FUSEKI_GRAPH_ECUME_REJECTED` ;
- `FUSEKI_GRAPH_ECUME_PROVENANCE` ;
- `FUSEKI_GRAPH_ECUME_REVIEW`.

**ECUME ne modifie jamais directement les graphes Echo de reference.** Il produit des
propositions et lots d'enrichissement soumis a revue humaine. Les identifiants RDF se
placent dans `ECUME_RDF_AUTH_USERNAME` et `ECUME_RDF_AUTH_SECRET`, uniquement dans une
configuration locale non versionnee ou un Secret Kubernetes.

## OntoCast

OntoCast est desactive par defaut avec `ONTOCAST_ENABLED=false`. Le contrat d'integration
et `ONTOCAST_API_URL` sont prepares, mais aucun document n'est envoye reellement tant que
l'API n'est pas stabilisee. `ONTOCAST_TOKEN` est reserve a ce futur contrat et n'est pas
utilise en mode `disabled`. Le fallback local ECUME reste disponible.

## Ontosphere

`ONTOSPHERE_URL` designe un outil externe de revue. ECUME prepare les graphes, liens et
exports a examiner ; il ne pilote pas directement Ontosphere et n'en depend pas pour son
fonctionnement local.

## Priorite des reglages

Les valeurs initiales viennent de l'environnement. Les reglages enregistres dans Admin
sont conserves dans `/data/settings.env` et reutilises apres redemarrage. Ce fichier peut
contenir une cle LLM ou des identifiants RDF : l'acces au volume `/data` doit donc etre
protege.

La recette reproductible [Admin et persistance runtime](admin-runtime-recipe.md) montre
comment modifier les cinq integrations, redemarrer les conteneurs, verifier la persistance
et tester les connexions LLM et Fuseki sans afficher les secrets.
