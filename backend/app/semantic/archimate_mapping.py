from __future__ import annotations

from typing import Any


BUSINESS_CATEGORIES: dict[str, dict[str, str]] = {
    "resultat_recherche": {
        "label": "resultat recherche",
        "tooltip": "Ce que l'on cherche a obtenir. Exemple : detecter une menace, produire une alerte, garantir une capacite.",
    },
    "objectif_haut_niveau": {
        "label": "objectif haut niveau",
        "tooltip": "Finalite generale a atteindre, souvent issue d'une directive ou d'un niveau superieur.",
    },
    "capacite_a_obtenir": {
        "label": "capacite a obtenir",
        "tooltip": "Ce que l'organisation doit etre capable de faire pour atteindre un objectif.",
    },
    "action_activite": {
        "label": "action / activite",
        "tooltip": "Ce qui est fait pour produire ou contribuer a un resultat. Exemple : capter, comparer, qualifier, transmettre.",
    },
    "chose_metier": {
        "label": "chose metier manipulee",
        "tooltip": "Element dont on parle ou sur lequel on agit. Exemple : signal, zone, emetteur, menace.",
    },
    "donnee_manipulee": {
        "label": "donnee manipulee",
        "tooltip": "Information utilisee, produite ou echangee. Exemple : position, frequence, identifiant, statut.",
    },
    "condition_regle_contrainte": {
        "label": "condition / regle / contrainte",
        "tooltip": "Situation, critere ou regle qui precise dans quel cas une action doit etre realisee.",
    },
    "tache_concrete": {
        "label": "tache concrete",
        "tooltip": "Action realisee concretement par un operateur, une equipe ou un systeme.",
    },
    "acteur_organisation": {
        "label": "acteur / organisation",
        "tooltip": "Personne, unite, organisme ou systeme qui agit ou porte une responsabilite.",
    },
    "role_tenu": {
        "label": "role tenu",
        "tooltip": "Fonction assumee par un acteur dans un contexte donne.",
    },
    "service_rendu": {
        "label": "service rendu",
        "tooltip": "Capacite fournie a un utilisateur ou a un metier pour produire un resultat.",
    },
    "service_applicatif": {
        "label": "service applicatif",
        "tooltip": "Service fourni par une application pour aider un metier ou un autre systeme.",
    },
    "element_technique": {
        "label": "element technique",
        "tooltip": "Element technique utile au fonctionnement : infrastructure, noeud, fonction ou service technique.",
    },
    "non_qualifie": {
        "label": "non qualifie",
        "tooltip": "ECUME n'a pas encore assez d'indices pour proposer une categorie fiable.",
    },
}


NODE_TYPE_DEFAULT_CATEGORY = {
    "effect": "resultat_recherche",
    "object": "chose_metier",
    "action": "action_activite",
    "condition": "condition_regle_contrainte",
    "task": "tache_concrete",
    "theme": "non_qualifie",
}


ARCHIMATE_BY_CATEGORY = {
    "resultat_recherche": ("Motivation", "Outcome", 0.72),
    "objectif_haut_niveau": ("Motivation", "Goal", 0.74),
    "capacite_a_obtenir": ("Strategy", "Capability", 0.76),
    "action_activite": ("Business", "Business Process", 0.68),
    "chose_metier": ("Business", "Business Object", 0.66),
    "donnee_manipulee": ("Application", "Data Object", 0.64),
    "condition_regle_contrainte": ("Motivation", "Constraint", 0.66),
    "tache_concrete": ("Business", "Business Process", 0.62),
    "acteur_organisation": ("Business", "Business Actor", 0.74),
    "role_tenu": ("Business", "Business Role", 0.72),
    "service_rendu": ("Business", "Business Service", 0.7),
    "service_applicatif": ("Application", "Application Service", 0.74),
    "element_technique": ("Technology", "Node", 0.62),
    "non_qualifie": ("Unknown", "Unknown", 0.3),
}


def normalize_business_category(value: str | None, fallback: str = "non_qualifie") -> str:
    if not value:
        return fallback
    normalized = str(value).strip().lower()
    if normalized in BUSINESS_CATEGORIES:
        return normalized
    by_label = {
        payload["label"].lower(): key for key, payload in BUSINESS_CATEGORIES.items()
    }
    return by_label.get(normalized, fallback)


def default_category_for_node_type(node_type: str) -> str:
    return NODE_TYPE_DEFAULT_CATEGORY.get(node_type, "non_qualifie")


def infer_archimate_mapping(
    *,
    business_category: str,
    concept_label: str = "",
    document_type: str = "",
    confidence: float | None = None,
    reason: str = "",
    status: str = "inferred_from_user_answer",
) -> dict[str, Any]:
    category = normalize_business_category(business_category)
    layer, element, default_confidence = ARCHIMATE_BY_CATEGORY.get(
        category, ARCHIMATE_BY_CATEGORY["non_qualifie"]
    )
    mapping_confidence = confidence if confidence is not None else default_confidence
    if not reason:
        category_label = BUSINESS_CATEGORIES[category]["label"]
        reason = (
            f"Le concept '{concept_label}' est classe comme '{category_label}'. "
            f"Le type de document '{document_type or 'inconnu'}' sert seulement d'indice de contexte."
        )
    return {
        "framework": "ArchiMate",
        "version": "3.2",
        "candidate_layer": layer,
        "candidate_element": element,
        "confidence": round(float(mapping_confidence), 2),
        "reason": reason,
        "status": status,
    }


def normalize_archimate_mapping(
    value: Any,
    *,
    business_category: str,
    concept_label: str = "",
    document_type: str = "",
    default_status: str = "inferred_from_user_answer",
) -> dict[str, Any]:
    fallback = infer_archimate_mapping(
        business_category=business_category,
        concept_label=concept_label,
        document_type=document_type,
        status=default_status,
    )
    if not isinstance(value, dict):
        return fallback
    merged = {**fallback, **value}
    merged["framework"] = "ArchiMate"
    merged["version"] = "3.2"
    try:
        merged["confidence"] = round(float(merged.get("confidence", fallback["confidence"])), 2)
    except (TypeError, ValueError):
        merged["confidence"] = fallback["confidence"]
    if not merged.get("status"):
        merged["status"] = default_status
    return merged
