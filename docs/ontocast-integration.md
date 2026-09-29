# Contrat preparatoire OntoCast

L'integration OntoCast est preparee mais n'est pas encore branchee au parcours d'analyse. Le moteur actuel d'ECUME reste le fallback obligatoire.

## Flux cible

1. ECUME recoit ou importe un document.
2. ECUME demande ou propose un domaine.
3. ECUME transmet le texte, la granularite et les graphes Echo disponibles a OntoCast.
4. OntoCast renvoie concepts, relations, regles, mentions, rapprochements, scores et provenance.
5. ECUME transforme cette reponse technique en cartes metier simples.
6. L'expert metier valide, corrige ou ignore.

## Entree JSON cible

```json
{
  "document_id": "...",
  "title": "...",
  "domain": "ECHO_RH",
  "granularity": "large | medium | fine",
  "text": "...",
  "reference_graphs": {
    "owl": "graph:echo:reference:owl",
    "voc": "graph:echo:reference:voc",
    "shacl": "graph:echo:reference:shacl"
  }
}
```

## Sortie JSON cible

```json
{
  "document_id": "...",
  "proposed_domain": {
    "domain": "ECHO_RH",
    "confidence": 0.86,
    "reasons": ["termes RH detectes", "concepts proches dans Echo RH"]
  },
  "candidates": [
    {
      "local_mention": "le maire",
      "candidate_label": "Maire",
      "candidate_type": "actor",
      "source_excerpt": "...",
      "confidence": 0.91,
      "close_matches": [
        {
          "uri": "...",
          "label": "Maire",
          "score": 0.94,
          "source": "Echo VOC",
          "reason": "altLabel proche"
        }
      ]
    }
  ],
  "relations": [],
  "rules": [],
  "provenance": []
}
```

## Regles d'integration

- L'appel API est desactive par defaut.
- Le mode simulation permet de verifier l'Admin sans service externe.
- Une erreur OntoCast est traduite en message simple et declenche le fallback local s'il est active.
- La reponse brute n'est jamais montree dans les cartes metier.
- Le contrat devra etre versionne avant l'activation de l'envoi reel de documents.
