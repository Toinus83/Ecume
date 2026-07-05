# Modèle de données ECUME

## SourceDocument

Document importé par l'utilisateur. Le texte extrait est stocké pour garder la provenance.

## ExtractedCard

Carte métier proposée ou créée manuellement. Une carte représente un effet principal et ses objets, actions, conditions et tâches.

## KnowledgeNode

Concept du graphe : effet, objet, action, condition, tâche ou thème.

Le champ `metadata` permet de conserver l'origine, l'extrait source, l'identifiant de carte et des informations techniques non exposées à l'utilisateur.

## KnowledgeEdge

Lien entre deux noeuds. Les relations visibles sont volontairement courtes : `contribue à`, `se décompose en`, `concerne`, `nécessite`, `déclenche`, `proche de`, `équivalent à`.

## KnowledgeNodeAlias

Synonymes, variantes documentaires et anciennes appellations d'un concept.

## ChangeLog

Historique des modifications : entité concernée, action, origine, source documentaire, date et détails.

## Exports

Le MVP exporte JSON, JSON-LD, CSV, Memgraph CSV + Cypher, et un squelette SKOS en Turtle.
