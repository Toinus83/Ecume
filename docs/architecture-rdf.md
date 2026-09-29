# Architecture RDF cible d'ECUME

ECUME reste le poste de travail simple des experts metier. Il ne remplace ni un triple store, ni un editeur d'ontologie, ni un moteur d'extraction RDF, ni un outil de revue technique.

> ECUME propose, l'expert metier valide, l'ontologue integre, Echo reste maitrise.

## Vue logique

```text
Echo OWL / VOC / SHACL
          |
          v
        Fuseki
  RDF store + SPARQL endpoint
          |
  +-------+----------+----------------+
  |                  |                |
  v                  v                v
OntoCast           ECUME          Ontosphere
extraction RDF     validation     revue graphe /
                   metier         ontologie
```

- Echo alimente Fuseki avec les referentiels valides.
- Fuseki expose les graphes au moyen de SPARQL.
- OntoCast peut exploiter Echo/Fuseki pour extraire des candidats depuis les documents.
- ECUME presente ces candidats en langage metier et conserve la decision humaine.
- ECUME ecrit uniquement dans ses propres graphes candidats ou valides, jamais dans Echo.
- Ontosphere, ou un outil equivalent, permet a l'ontologue d'inspecter les propositions.
- L'ontologue decide ensuite de leur integration eventuelle dans Echo.

## Convention configurable de graphes nommes

Graphes de reference, toujours en lecture seule pour ECUME :

- `graph:echo:reference:owl`
- `graph:echo:reference:voc`
- `graph:echo:reference:shacl`

Graphes de travail ECUME :

- `graph:ecume:candidates` : propositions brutes ;
- `graph:ecume:validated` : decisions validees par le metier ;
- `graph:ecume:rejected` : propositions rejetees ;
- `graph:ecume:provenance` : documents, extraits, decisions et traces ;
- `graph:ecume:review` : lot pret pour la revue ontologue.

Ces noms sont des valeurs par defaut modifiables dans l'Admin. La separation entre `graph:echo:reference:*` et `graph:ecume:*` est, elle, obligatoire.

## Modes de fonctionnement

### Mode local

SQLite, moteur ECUME, cartes, validation et exports locaux. Aucun service externe n'est requis.

### Mode connecte en lecture seule

ECUME lit Echo depuis Fuseki pour rechercher des concepts, synonymes et domaines. Aucune ecriture RDF n'est autorisee.

### Mode connecte complet

ECUME lit Echo et pourra ecrire ses propositions dans les graphes ECUME dedies. Meme dans ce mode, les graphes Echo restent intouchables.

Le connecteur actuel implemente la lecture SPARQL preparatoire. L'ecriture SPARQL Update n'est pas encore activee.

## Responsabilites et securite

- Les services externes sont desactives par defaut.
- Les secrets sont stockes dans le fichier local `.env`, exclu de Git, et ne sont pas renvoyes par l'API Admin.
- L'interface metier ne montre pas les endpoints, graphes ou details d'authentification.
- Une indisponibilite Fuseki ou OntoCast ne bloque pas ECUME : le mode local demeure utilisable.
- Aucun fichier ou graphe Echo n'est modifie directement.
