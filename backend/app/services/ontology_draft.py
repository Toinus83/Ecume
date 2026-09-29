"""Build a portable ontology review package from validated ECUME knowledge."""
from __future__ import annotations

import csv
from html import escape
import io
import json
import uuid
import zipfile

from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS, OWL, SKOS, DCTERMS

from app.database.db import now_iso


OWL_CLASS_CATEGORIES = {
    "acteur_organisation", "role_tenu", "capacite_a_obtenir", "service_rendu",
    "service_applicatif", "application_outil", "lieu_environnement_physique",
    "element_technique", "donnee_manipulee",
}
PROPOSAL_FIELDS = [
    "id", "type_proposition", "libelle", "definition", "domaine", "statut",
    "confiance", "source_document", "extrait_source", "cible_reference",
    "score_rapprochement", "decision_recommandee", "commentaire_revue",
]


def _confidence(value) -> float:
    if isinstance(value, (int, float)):
        return round(max(0.0, min(1.0, float(value))), 3)
    return {"high": 0.85, "medium": 0.6, "low": 0.35}.get(str(value), 0.5)


def _domain(documents: list[dict]) -> str:
    confirmed = [doc.get("confirmed_domain", "").strip() for doc in documents]
    confirmed = list(dict.fromkeys(value for value in confirmed if value))
    return confirmed[0] if len(confirmed) == 1 else "multi-domaines" if confirmed else "non confirme"


def _proposal(identifier: str, kind: str, label: str, *, definition: str = "", domain: str,
              confidence=0.5, source_document: str = "", excerpt: str = "",
              target: str = "", score="", decision: str = "Revoir", comment: str = "") -> dict:
    return {
        "id": identifier, "type_proposition": kind, "libelle": label,
        "definition": definition, "domaine": domain, "statut": "review_required",
        "confiance": _confidence(confidence), "source_document": source_document,
        "extrait_source": excerpt, "cible_reference": target,
        "score_rapprochement": score, "decision_recommandee": decision,
        "commentaire_revue": comment,
    }


def _csv(proposals: list[dict]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=PROPOSAL_FIELDS)
    writer.writeheader()
    writer.writerows(proposals)
    return output.getvalue()


def _report(manifest: dict, proposals: list[dict]) -> str:
    groups = {}
    for item in proposals:
        groups[item["type_proposition"]] = groups.get(item["type_proposition"], 0) + 1
    rows = "".join(
        f"<tr><td>{escape(kind)}</td><td>{count}</td></tr>" for kind, count in sorted(groups.items())
    ) or "<tr><td>Aucune proposition</td><td>0</td></tr>"
    warnings = "".join(f"<li>{escape(message)}</li>" for message in manifest["avertissements"])
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Rapport de contrôle ECUME</title>
<style>body{{font:16px system-ui,sans-serif;max-width:980px;margin:32px auto;padding:0 20px;color:#172033}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd6df;padding:8px;text-align:left}}.warning{{border-left:4px solid #a16207;background:#fff7e6;padding:12px}}</style></head>
<body><h1>Lot de revue ontologique ECUME</h1>
<p class="warning"><strong>Proposition à revoir, pas une ontologie approuvée.</strong><br>
ECUME ne modifie pas directement le référentiel Echo. Ce lot est une proposition d’enrichissement soumise à revue humaine.</p>
<h2>Périmètre</h2><p>Domaine confirmé : <strong>{escape(manifest['domaine_confirme'])}</strong>. Statut : <strong>review_required</strong>.</p>
<h2>Contrôle humain</h2><ul>
<li>Déjà reconnu : {manifest['nombre_elements_reconnus']}</li>
<li>Nouveau : {manifest['nombre_propositions_voc']}</li>
<li>Proche d'un concept existant : {manifest['nombre_concepts_proches_a_revoir']}</li>
<li>À revoir : {manifest['nombre_propositions_a_revoir']}</li>
<li>Non formalisable en SHACL : {manifest['nombre_regles_non_formalisees']}</li>
<li>Candidat OWL : {manifest['nombre_propositions_owl']}</li>
<li>Candidat VOC : {manifest['nombre_propositions_voc']}</li>
<li>Candidat SHACL : {manifest['nombre_propositions_shacl']}</li></ul>
<h2>Résumé des propositions</h2><table><thead><tr><th>Type</th><th>Nombre</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Lecture du lot</h2><ul><li>Les concepts VOC sont des termes candidats.</li><li>Les classes OWL sont limitées aux concepts métier suffisamment qualifiés.</li><li>Les règles sans cible, propriété et contrainte structurées restent non formalisées en SHACL.</li><li>Les concepts proches et alignements doivent être vérifiés avant réimport.</li></ul>
<h2>Limites et avertissements</h2><ul>{warnings}</ul>
<p><strong>Revue humaine avant tout réimport. Aucun fichier référentiel source modifié.</strong></p></body></html>"""


def export_bundle():
    from app.services import export_service
    from app.services.review_service import workspace

    payload = export_service._complete_export_payload()
    documents = payload["documents"]
    domain = _domain(documents)
    document_titles = {doc["id"]: doc.get("title") or doc.get("filename", "") for doc in documents}
    graphs = {layer: Graph() for layer in ("owl", "voc", "shacl")}
    ecume = Namespace("urn:ecume:vocab:")
    for graph in graphs.values():
        for prefix, namespace in [("owl", OWL), ("skos", SKOS), ("dcterms", DCTERMS), ("ecume", ecume)]:
            graph.bind(prefix, namespace)

    generated_at = now_iso()
    ontology = URIRef("urn:ecume:draft:ontology")
    scheme = URIRef("urn:ecume:draft:vocabulary")
    shacl_ontology = URIRef("urn:ecume:draft:shacl")
    graphs["owl"].add((ontology, RDF.type, OWL.Ontology))
    graphs["owl"].add((ontology, DCTERMS.title, Literal("Brouillon OWL ECUME", lang="fr")))
    graphs["owl"].add((ontology, DCTERMS.created, Literal(generated_at)))
    graphs["voc"].add((scheme, RDF.type, SKOS.ConceptScheme))
    graphs["voc"].add((scheme, DCTERMS.title, Literal("Brouillon VOC ECUME", lang="fr")))
    graphs["voc"].add((scheme, DCTERMS.created, Literal(generated_at)))
    graphs["shacl"].add((shacl_ontology, RDF.type, OWL.Ontology))
    graphs["shacl"].add((shacl_ontology, DCTERMS.title, Literal("Brouillon SHACL ECUME", lang="fr")))
    graphs["shacl"].add((shacl_ontology, RDFS.comment, Literal(
        "Aucune règle n'est convertie sans cible, propriété et contrainte structurées.", lang="fr")))

    proposals = []
    for node in payload["nodes"]:
        term = URIRef(f"urn:ecume:voc:{node['id']}")
        voc = graphs["voc"]
        voc.add((term, RDF.type, SKOS.Concept))
        voc.add((term, SKOS.inScheme, scheme))
        voc.add((term, SKOS.prefLabel, Literal(node["label"], lang="fr")))
        if node.get("description"):
            voc.add((term, SKOS.definition, Literal(node["description"], lang="fr")))
        for alias in node.get("aliases", []):
            label = alias.get("label", "") if isinstance(alias, dict) else str(alias)
            if label and label.casefold() != node["label"].casefold():
                voc.add((term, SKOS.altLabel, Literal(label, lang="fr")))
                proposals.append(_proposal(f"{node['id']}:alias:{len(proposals)}", "synonyme_candidat", label,
                    domain=domain, target=node["label"], decision="Ajouter comme altLabel",
                    comment="Vérifier l'équivalence de sens."))
        for source_id in node.get("source_ids", []):
            voc.add((term, DCTERMS.source, URIRef(f"urn:ecume:document:{source_id}")))
        sources = "; ".join(document_titles.get(value, value) for value in node.get("source_ids", []))
        proposals.append(_proposal(node["id"], "concept_voc_nouveau", node["label"],
            definition=node.get("description", ""), domain=domain, confidence=node.get("confidence"),
            source_document=sources, excerpt=node.get("source_excerpt", ""), decision="Examiner dans le VOC"))

        mapping = node.get("archimate_mapping") or {}
        category = node.get("business_category", "non_qualifie")
        if category in OWL_CLASS_CATEGORIES and mapping.get("candidate_element") not in (None, "", "Unknown"):
            canonical = URIRef(node["uri"])
            graphs["owl"].add((canonical, RDF.type, OWL.Class))
            graphs["owl"].add((canonical, RDFS.label, Literal(node["label"], lang="fr")))
            graphs["owl"].add((canonical, ecume.status, Literal("candidate_class_to_review")))
            if node.get("description"):
                graphs["owl"].add((canonical, RDFS.comment, Literal(node["description"], lang="fr")))
            proposals.append(_proposal(f"{node['id']}:owl", "classe_owl_candidate", node["label"],
                definition=node.get("description", ""), domain=domain,
                confidence=mapping.get("confidence", node.get("confidence")), source_document=sources,
                excerpt=node.get("source_excerpt", ""), decision="Vérifier classe ou individu",
                comment=f"Catégorie ECUME : {category}; candidat ArchiMate : {mapping.get('candidate_element', '')}."))

    non_formalized_rules = 0
    for card in payload["cards"]:
        details = card.get("extraction_details") or {}
        for position, rule in enumerate(details.get("business_rules", [])):
            label = rule.get("label") or rule.get("description") or "Règle métier"
            source = document_titles.get(card.get("document_id", ""), card.get("document_id", ""))
            proposals.append(_proposal(f"{card['id']}:rule:{position}", "regle_metier", label,
                definition=rule.get("description", ""), domain=domain, confidence=card.get("confidence"),
                source_document=source, excerpt=rule.get("source_excerpt", ""),
                decision="Règle métier non formalisée en SHACL",
                comment="Cible, propriété ou contrainte structurée insuffisante."))
            non_formalized_rules += 1

    for edge in payload["edges"]:
        proposals.append(_proposal(edge["id"], "relation_candidate", edge.get("label") or edge["relation_type"],
            definition=edge.get("description", ""), domain=domain, confidence=edge.get("confidence"),
            source_document="; ".join(edge.get("source_titles", [])), decision="Vérifier le sens de la relation",
            comment=f"{edge.get('source_label', '')} -> {edge['relation_type']} -> {edge.get('target_label', '')}"))

    review = workspace()
    for mention in review["items"]:
        if mention.get("status") != "review":
            continue
        candidate = (mention.get("candidates") or [None])[0]
        proposals.append(_proposal(f"{mention['id']}:review", "a_revoir", mention["label"],
            definition=mention.get("description", ""), domain=domain,
            source_document=mention.get("document_title", ""), excerpt=mention.get("source_excerpt", ""),
            target=(candidate or {}).get("label", ""), score=(candidate or {}).get("score", ""),
            decision="Choisir le rattachement ou confirmer un nouveau concept",
            comment=(candidate or {}).get("reason", "Proposition métier à vérifier.")))

    counts = {}
    for item in proposals:
        counts[item["type_proposition"]] = counts.get(item["type_proposition"], 0) + 1
    files = ["ecume_draft.owl.ttl", "ecume_draft.voc.ttl", "ecume_draft.shacl.ttl",
             "ecume_knowledge.json", "README.txt", "manifest.json", "proposals.csv", "control_report.html"]
    warnings = [
        "Proposition à revoir — pas une ontologie approuvée.",
        "Revue humaine avant tout réimport.",
        "Aucun fichier référentiel source modifié.",
    ]
    if domain == "non confirme":
        warnings.append("Domaine métier non confirmé : ne pas préparer de réimport Echo.")
    manifest = {
        "date_generation": generated_at,
        "version_ecume": payload["export_metadata"].get("version", ""),
        "domaine_confirme": domain,
        "documents_analyses": [{"id": doc["id"], "titre": doc.get("title", "")} for doc in documents],
        "fichiers_produits": files,
        "nombre_concepts": len(payload["nodes"]), "nombre_relations": len(payload["edges"]),
        "nombre_propositions_voc": counts.get("concept_voc_nouveau", 0) + counts.get("synonyme_candidat", 0),
        "nombre_propositions_owl": counts.get("classe_owl_candidate", 0) + counts.get("propriete_owl_candidate", 0),
        "nombre_propositions_shacl": counts.get("shape_shacl_candidate", 0),
        "nombre_regles_non_formalisees": non_formalized_rules,
        "nombre_elements_reconnus": sum(1 for item in review["items"] if item.get("status") == "known"),
        "nombre_concepts_proches_a_revoir": sum(1 for item in review["items"] if item.get("status") == "review" and item.get("candidates")),
        "nombre_propositions_a_revoir": counts.get("a_revoir", 0),
        "avertissements": warnings, "statut": "review_required",
    }

    export_service.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = export_service.EXPORT_DIR / f"ecume_ontology_review_{uuid.uuid4().hex}.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for layer, graph in graphs.items():
            bundle.writestr(f"ecume_draft.{layer}.ttl", graph.serialize(format="turtle"))
        bundle.writestr("ecume_knowledge.json", json.dumps(payload, ensure_ascii=False, indent=2))
        bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        bundle.writestr("proposals.csv", _csv(proposals))
        bundle.writestr("control_report.html", _report(manifest, proposals))
        bundle.writestr("README.txt",
            "Proposition à revoir — pas une ontologie approuvée.\n"
            "Revue humaine avant tout réimport.\n"
            "Aucun fichier référentiel source modifié.\n\n"
            "ecume_draft.owl.ttl : classes OWL candidates suffisamment qualifiées.\n"
            "ecume_draft.voc.ttl : concepts, définitions et synonymes SKOS candidats.\n"
            "ecume_draft.shacl.ttl : uniquement les shapes formalisables ; peut ne contenir que ses métadonnées.\n"
            "proposals.csv et control_report.html : supports de décision pour la revue humaine.\n"
            "ecume_knowledge.json : export pivot complet et traçable.\n")
    return path
