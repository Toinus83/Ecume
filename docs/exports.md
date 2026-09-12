# Exports ECUME

Les exports ECUME sont concus pour etre lisibles hors de l'application. Un concept ou une relation exportee doit pouvoir etre compris sans rouvrir ECUME.

## Quel Export Utiliser

- `JSON` : export complet de reference, pour sauvegarder, echanger ou reimporter toutes les donnees ECUME.
- `JSON-LD` : pivot Linked Data simple, pour preparer une integration RDF, GraphDB ou outil de mapping semantique.
- `CSV` : tables lisibles dans un tableur ou un pipeline de donnees.
- `Memgraph` : CSV + script Cypher pour charger le graphe dans Memgraph.
- `RDF/SKOS` : squelette minimal, non ontologique, utile pour tester une premiere projection SKOS.
- `ArchiMate JSON` : lot intermediaire prudent pour controler les mappings candidats avant un futur export ArchiMate Exchange XML.

## JSON Complet

Le fichier `ecume_export.json` contient :

- `export_metadata` : version d'export, date, types de relations, URI stables et notes de mapping ;
- `documents` : documents sources, titres, fichiers, type, texte extrait, apercu et metadonnees ;
- `cards` : cartes d'effets d'origine, source, extrait, objets/actions/conditions/taches ;
- `nodes` : concepts enrichis avec libelle canonique, alias, type, niveau, statut, confiance, sources, carte d'origine et metadonnees ;
- `edges` : relations enrichies avec libelles source/cible, sens, description, sources et metadonnees ;
- `changelog` : historique disponible ;
- `mappings` : descriptions metier simples des types de noeuds, categories metier et relations.

Les concepts et cartes peuvent aussi contenir :

- `business_category` : categorie metier simple visible par l'utilisateur ;
- `business_validation_status` : validation metier separee du mapping ;
- `business_justification` : justification courte lisible ;
- `archimate_mapping` : mapping candidat ArchiMate 3.2 structure ;
- `archimate_mapping_status` : statut du mapping architectural ;
- `ontology_mapping_status` : statut de mapping ontologique, sans bloquer la valeur metier.

## JSON-LD

Le fichier `ecume_export.jsonld` utilise des URI stables :

- `urn:ecume:node:{id}`
- `urn:ecume:edge:{id}`
- `urn:ecume:document:{id}`
- `urn:ecume:ontology:{id}` pour les futurs referentiels importes

Le `@context` reste volontairement simple. ECUME n'affirme pas encore une ontologie OWL/UAF complete ; il expose un graphe metier structure et tracable.

## CSV

Le bundle CSV contient :

- `nodes.csv`
- `edges.csv`
- `documents.csv`
- `cards.csv`

Colonnes principales de `nodes.csv` :

- `id`, `label`, `canonical_label`, `aliases`, `type`, `level`, `description`, `status`, `confidence`
- `business_category`, `business_validation_status`, `business_justification`
- `archimate_mapping`, `archimate_mapping_status`, `ontology_mapping_status`
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

Les colonnes `aliases`, `source_ids`, `source_titles`, `archimate_mapping` et `metadata` sont serialisees en JSON texte dans le CSV.

## Lire Le Sens Des Relations

Les relations sont dirigees :

```text
source_node_id --relation_type--> target_node_id
```

Exemple :

```text
Effet A --se decompose en--> Tache B
```

La colonne `direction` donne une phrase courte avec les libelles source et cible.

## Import Memgraph

Le bundle Memgraph contient :

- `memgraph_nodes.csv`
- `memgraph_edges.csv`
- `memgraph_import.cypher`

Principe :

- chaque concept devient un noeud `:EcumeNode` ;
- chaque relation devient une relation `:ECUME_RELATION` ;
- le type metier de la relation est stocke dans la propriete `relation_type`.

Exemple d'execution depuis Memgraph Lab ou `mgconsole`, en adaptant le chemin CSV selon ton installation :

```cypher
LOAD CSV FROM "memgraph_nodes.csv" WITH HEADER AS row
MERGE (n:EcumeNode {id: row.id})
SET n.label = row.label,
    n.type = row.type,
    n.level = row.level,
    n.status = row.status,
    n.business_category = row.business_category,
    n.archimate_mapping = row.archimate_mapping;

LOAD CSV FROM "memgraph_edges.csv" WITH HEADER AS row
MATCH (source:EcumeNode {id: row.source_node_id}), (target:EcumeNode {id: row.target_node_id})
CREATE (source)-[r:ECUME_RELATION {id: row.id}]->(target)
SET r.relation_type = row.relation_type,
    r.label = row.label,
    r.description = row.description;
```

Le fichier `memgraph_import.cypher` fourni contient une version plus complete avec les metadonnees.

## Export ArchiMate JSON

Le fichier `ecume_archimate_candidates.json` est un export intermediaire, volontairement prudent.

Il contient uniquement des candidats d'import ArchiMate, pas un modele central modifie. Chaque candidat garde :

- l'identifiant ECUME ;
- le libelle et la description ;
- la categorie metier ;
- le statut de validation metier ;
- les sources ;
- le mapping candidat ArchiMate 3.2 ;
- une decision d'export indicative.

La selection automatique reste conservatrice : un element est marque comme selectionnable seulement si le concept est valide metier et si la confiance du mapping candidat est au moins egale a `0.70`.

Le format ArchiMate Model Exchange XML n'est pas genere dans cette iteration. Ce JSON sert de lot de controle avant generation XML future.

## Preparation MBSE / UAF

L'export ne mappe pas encore formellement vers UAF. Il preserve cependant les informations utiles a un futur mapping :

- effets ;
- objets ;
- actions ;
- conditions ;
- taches ;
- niveaux ;
- relations metier simples ;
- categories metier ;
- mapping candidat ArchiMate ;
- sources et extraits.
