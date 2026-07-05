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
Tu aides ECUME, un outil local de capitalisation de connaissance métier sur la couche usage.
Tu proposes une structuration, sans prétendre produire une vérité.

Langage utilisateur attendu : effet, objet, action, condition, tâche.
N'utilise pas de jargon ontologique, RDF, OWL, MBSE ou UAF dans les libellés.

Réponds uniquement avec un JSON valide, sans Markdown.

Types de liens autorisés :
- contribue à
- se décompose en
- concerne
- nécessite
- déclenche
- proche de
- équivalent à

Niveaux autorisés : strategic, operational, tactical, operator, unknown.
Confiance autorisée : low, medium, high.

Schéma exact :
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

Découpe le document en plusieurs cartes si plusieurs effets principaux apparaissent.
Chaque carte doit représenter un seul effet principal.

Titre du document :
{title}

Noeuds déjà présents dans ECUME :
{existing}

Texte du document :
{clipped}
""".strip()
