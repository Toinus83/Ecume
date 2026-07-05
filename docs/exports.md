# Exports ECUME

Les exports ECUME sont conçus pour être lisibles hors de l'application. Un concept ou une relation exportée doit pouvoir être compris sans rouvrir ECUME.

## Quel export utiliser

- `JSON` : export complet de référence, pour sauvegarder, échanger ou réimporter toutes les données ECUME.
- `JSON-LD` : pivot Linked Data simple, pour préparer une intégration RDF, GraphDB ou outil de mapping sémantique.
- `CSV` : tables lisibles dans un tableur ou un pipeline de données.
- `Memgraph` : CSV + script Cypher pour charger le graphe dans Memgraph.
- `RDF/SKOS` : squelette minimal, non ontologique, utile pour tester une première projection SKOS.

## JSON complet

Le fichier `ecume_export.json` contient :

- `export_metadata` : version d'export, date, types de relations, URI stables et notes de mapping ;
- `documents` : documents sources, titres, fichiers, type, texte extrait, aperçu et métadonnées ;
- `cards` : cartes d'effets d'origine, source, extrait, objets/actions/conditions/tâches ;
- `nodes` : concepts enrichis avec libellé canonique, alias, type, niveau, statut, confiance, sources, carte d'origine et métadonnées ;
- `edges` : relations enrichies avec libellés source/cible, sens, description, sources et métadonnées ;
- `changelog` : historique disponible ;
- `mappings` : descriptions métier simples des types de nœuds et relations.

## JSON-LD

Le fichier `ecume_export.jsonld` utilise des URI stables :

- `urn:ecume:node:{id}`
- `urn:ecume:edge:{id}`
- `urn:ecume:document:{id}`

Le `@context` reste volontairement simple. ECUME n'affirme pas encore une ontologie OWL/UAF complète ; il expose un graphe métier structuré et traçable.

## CSV

Le bundle CSV contient :

- `nodes.csv`
- `edges.csv`
- `documents.csv`
- `cards.csv`

Colonnes principales de `nodes.csv` :

- `id`, `label`, `canonical_label`, `aliases`, `type`, `level`, `description`, `status`, `confidence`
- `source_ids`, `source_titles`
- `created_at`, `updated_at`
- `uri`, `origin_card_id`, `source_excerpt`, `metadata`

Colonnes principales de `edges.csv` :

- `id`, `source_node_id`, `source_label`, `target_node_id`, `target_label`
- `relation_type`, `label`, `description`, `direction`
- `status`, `confidence`
- `source_ids`, `source_titles`
- `created_at`, `updated_at`
- `uri`, `origin_card_id`, `metadata`

Les colonnes `aliases`, `source_ids`, `source_titles` et `metadata` sont sérialisées en JSON texte dans le CSV.

## Lire le sens des relations

Les relations sont dirigées :

```text
source_node_id --relation_type--> target_node_id
```

Exemple :

```text
Effet A --se décompose en--> Tâche B
```

La colonne `direction` donne une phrase courte avec les libellés source et cible.

## Import Memgraph

Le bundle Memgraph contient :

- `memgraph_nodes.csv`
- `memgraph_edges.csv`
- `memgraph_import.cypher`

Principe :

- chaque concept devient un nœud `:EcumeNode` ;
- chaque relation devient une relation `:ECUME_RELATION` ;
- le type métier de la relation est stocké dans la propriété `relation_type`.

Exemple d'exécution depuis Memgraph Lab ou `mgconsole`, en adaptant le chemin CSV selon ton installation :

```cypher
LOAD CSV FROM "memgraph_nodes.csv" WITH HEADER AS row
MERGE (n:EcumeNode {id: row.id})
SET n.label = row.label,
    n.type = row.type,
    n.level = row.level,
    n.status = row.status;

LOAD CSV FROM "memgraph_edges.csv" WITH HEADER AS row
MATCH (source:EcumeNode {id: row.source_node_id}), (target:EcumeNode {id: row.target_node_id})
CREATE (source)-[r:ECUME_RELATION {id: row.id}]->(target)
SET r.relation_type = row.relation_type,
    r.label = row.label,
    r.description = row.description;
```

Le fichier `memgraph_import.cypher` fourni contient une version plus complète avec les métadonnées.

## Préparation MBSE / UAF

L'export ne mappe pas encore formellement vers UAF. Il préserve cependant les informations utiles à un futur mapping :

- effets ;
- objets ;
- actions ;
- conditions ;
- tâches ;
- niveaux ;
- relations métier simples ;
- sources et extraits.
