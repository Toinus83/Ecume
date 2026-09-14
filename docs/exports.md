# Exports ECUME

Les exports ECUME sont concus pour etre lisibles hors de l'application. Un concept ou une relation exportee doit pouvoir etre compris sans rouvrir ECUME.

## Quel Export Utiliser

- `JSON` : connaissance validee par defaut ; archive complete disponible avec `scope=all`.
- `JSON-LD` : pivot Linked Data simple, pour preparer une integration RDF, GraphDB ou outil de mapping semantique.
- `CSV` : tables lisibles dans un tableur ou un pipeline de donnees.
- `Memgraph` : CSV + script Cypher pour charger le graphe dans Memgraph.
- `RDF/SKOS` : squelette minimal, non ontologique, utile pour tester une premiere projection SKOS.
- `ArchiMate JSON` : lot intermediaire prudent pour controler les mappings candidats avant un futur export ArchiMate Exchange XML.

## JSON Complet

Les endpoints JSON, JSON-LD, CSV et Memgraph utilisent `scope=validated` par defaut.
Les cartes et concepts rejetes ou a revoir, ainsi que les relations non acceptees, sont exclus des collections de connaissance validee.
Les documents et le changelog restent presents pour la tracabilite : les anciens etats dans l'historique ne sont pas des connaissances actuellement validees.

Pour obtenir une archive complete comprenant aussi propositions, rejets et decisions, utiliser
`http://127.0.0.1:8000/export/json?scope=all`. Le champ `export_metadata.scope` indique la portee.
Cette archive est un fichier de donnees ; ECUME ne propose pas encore de restauration automatique depuis ce JSON.

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

Le contexte JSON-LD 1.1 definit un vocabulaire ECUME par defaut pour conserver les champs imbriques du mapping.
Les cartes, l'historique et le manifeste sont aussi inclus ; leurs enregistrements complets sont preserves comme valeurs JSON typees (`@json`).

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
MERGE (source)-[r:ECUME_RELATION {id: row.id}]->(target)
SET r.relation_type = row.relation_type,
    r.label = row.label,
    r.description = row.description;
```

Le fichier `memgraph_import.cypher` fourni contient une version plus complete avec les metadonnees.

Les fichiers CSV doivent etre accessibles au serveur Memgraph (et montes dans son conteneur si necessaire).
Le script utilise les identifiants stables des noeuds et relations avec `MERGE` : reimporter le meme lot ne cree pas de doublons.
Il ne supprime pas les donnees deja chargees qui sont absentes d'un export suivant. Pour comparer des instantanes complets apres des rejets ou suppressions, utiliser une base de test vide ou gerer explicitement les retraits cote cible.

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

Seuls les concepts valides metier sont presentes ; les mappings rejetes ou a revoir sont exclus.
Un candidat n'est marque `selected_for_archimate_export` que si son mapping porte une validation architecture explicite (`validated_by_architect`) et une confiance d'au moins `0.70`.
La validation d'une carte metier ne fournit pas cette certification : elle conserve un mapping candidat.

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
# Conservation et decisions metier

Une source purgee conserve son identifiant documentaire, son nom, ses dates et son
empreinte. Les extraits courts restent attaches aux cartes et concepts. Une source
supprimee conserve une reference minimale dans `documents` avec `source_status=deleted`.
JSON, JSON-LD et `documents.csv` exposent l'etat de conservation. Une purge ne modifie
pas les fichiers d'export precedemment generes ou les copies externes.

`business_validation_status=auto_validated` distingue une validation automatique d'une
validation humaine. `business_confidence` contient le score metier estime (ou null) ;
`validation_decision` contient l'origine, la regle, les seuils et la date quand disponibles.
Les concepts partages citent leurs cartes de soutien. `orphan_status` distingue les
orphelins acceptes de ceux a revoir. Ces champs sont ajoutes aux CSV sans retirer les
colonnes precedentes et sont conserves par le script Memgraph (scores CSV sous forme texte).
Les mappings ArchiMate restent candidats, quelle que soit la validation metier.

Le graphe et les exports principaux incluent la connaissance validee manuellement ou
automatiquement. Les propositions, rejets et orphelins a revoir sont exclus ; l'archive
`scope=all` conserve tous les etats. Les decisions historiques du changelog ne constituent
pas une validation actuelle.
