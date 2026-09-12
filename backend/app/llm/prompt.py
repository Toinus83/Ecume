from __future__ import annotations

from typing import Any


def build_analysis_prompt(
    *, title: str, content_text: str, existing_nodes: list[dict[str, Any]]
) -> str:
    existing = [
        {"id": node["id"], "label": node["label"], "type": node["type"], "level": node["level"]}
        for node in existing_nodes[:80]
    ]
    clipped = content_text[:18000]
    return f"""
Tu aides ECUME, un outil local de capitalisation de connaissance metier sur la couche usage.
Tu proposes une structuration, sans pretendre produire une verite.

Langage utilisateur attendu : effet, objet, action, condition, tache.
N'utilise pas de jargon ontologique, RDF, OWL, MBSE ou UAF dans les libelles.
L'utilisateur metier ne doit pas voir ArchiMate : ces informations servent seulement de metadonnees backend.

Reponds uniquement avec un JSON valide, sans Markdown.

Types de liens autorises :
- contribue à
- se décompose en
- concerne
- nécessite
- déclenche
- proche de
- équivalent à

Niveaux autorises : strategic, operational, tactical, operator, unknown.
Confiance autorisee : low, medium, high.

Categories metier autorisees :
- resultat_recherche
- objectif_haut_niveau
- capacite_a_obtenir
- action_activite
- chose_metier
- donnee_manipulee
- condition_regle_contrainte
- tache_concrete
- acteur_organisation
- role_tenu
- service_rendu
- service_applicatif
- element_technique
- non_qualifie

Mapping ArchiMate candidat :
- framework doit valoir "ArchiMate"
- version doit valoir "3.2"
- candidate_layer peut valoir Motivation, Strategy, Business, Application, Technology, Implementation & Migration ou Unknown
- candidate_element doit rester un candidat, jamais une certitude
- confidence est un nombre entre 0 et 1
- status doit valoir proposed_by_llm

Schema exact :
{{
  "document_summary": "...",
  "cards": [
    {{
      "theme_label": "...",
      "main_effect": {{
        "label": "...",
        "description": "...",
        "level": "strategic|operational|tactical|operator|unknown",
        "confidence": "low|medium|high"
      }},
      "business_category": "resultat_recherche|objectif_haut_niveau|capacite_a_obtenir|action_activite|chose_metier|donnee_manipulee|condition_regle_contrainte|tache_concrete|acteur_organisation|role_tenu|service_rendu|service_applicatif|element_technique|non_qualifie",
      "business_justification": "Justification courte, lisible par un utilisateur metier.",
      "archimate_mapping": {{
        "framework": "ArchiMate",
        "version": "3.2",
        "candidate_layer": "...",
        "candidate_element": "...",
        "confidence": 0.72,
        "reason": "Justification courte du mapping candidat.",
        "status": "proposed_by_llm"
      }},
      "objects": ["..."],
      "actions": ["..."],
      "conditions": ["..."],
      "tasks": ["..."],
      "secondary_effects": ["..."],
      "suggested_links": [
        {{
          "source_label": "...",
          "target_existing_node_id": "...",
          "target_label": "...",
          "relation_type": "contribue à|se décompose en|concerne|nécessite|déclenche|proche de|équivalent à",
          "confidence": "low|medium|high",
          "reason": "..."
        }}
      ],
      "source_excerpt": "...",
      "confidence": "low|medium|high"
    }}
  ],
  "orphans": [],
  "warnings": []
}}

Decoupe le document en plusieurs cartes si plusieurs effets principaux apparaissent.
Chaque carte doit representer un seul effet principal.

Titre du document :
{title}

Noeuds deja presents dans ECUME :
{existing}

Texte du document :
{clipped}
""".strip()
