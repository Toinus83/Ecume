from __future__ import annotations

import json

from app.database.db import atomic, get_db, now_iso
from app.models.schemas import CardUpdate, KnowledgeEdgeIn, MainEffect, OrphanUpdate
from app.services import card_service, coherence_service as coherence, graph_service as graph
from app.services.changelog_service import record_change


@atomic
def update_orphan(node_id: str, update: OrphanUpdate) -> dict:
    node = graph.get_node(node_id)
    if not node:
        raise ValueError("Concept introuvable.")
    if node["status"] in {"rejected", "linked"}:
        raise ValueError("Un concept rejete ou fusionne doit etre corrige depuis sa carte source.")
    if update.target_node_id and update.orphan_status:
        raise ValueError("Choisis un rattachement ou une decision d'orphelin, pas les deux.")
    if update.target_node_id == node_id:
        raise ValueError("Un concept ne peut pas etre rattache a lui-meme.")
    changes = {key: value.strip() if isinstance(value, str) else value
               for key, value in update.model_dump(exclude_none=True).items()
               if key in {"label", "business_category", "level"} and value != node.get(key)}
    if "label" in changes and not changes["label"]:
        raise ValueError("Le libelle est obligatoire.")
    users = coherence.concept_users(node_id)
    if len(users) > 1 and (changes or update.orphan_status == "orphan_to_review"):
        raise ValueError("Concept partage par plusieurs cartes : corrige-le depuis sa carte source. Le rattachement reste possible.")
    with get_db() as conn:
        if changes:
            if users:
                card = card_service.require_card(users[0])
                ids = card["graph_node_ids"]
                if ids.get("effect") == node_id:
                    effect = {**card["main_effect"], "label": changes.get("label", node["label"]), "level": changes.get("level", node["level"])}
                    card_service.update_card(card["id"], CardUpdate(main_effect=MainEffect(**effect),
                        level=effect["level"], business_category=changes.get("business_category", node["business_category"])))
                else:
                    patches = {}
                    for role in card_service.ROLES:
                        if node_id in ids.get(role, []):
                            patches[role] = [changes.get("label", label) if current == node_id else label
                                             for label, current in zip(card[role], ids[role])]
                    if ids.get("theme") == node_id:
                        patches["theme_label"] = changes.get("label", node["label"])
                    card_service.update_card(card["id"], CardUpdate(**patches, status="to_confirm"))
            if "label" in changes:
                graph._attach_variant(node_id, node["label"], "former_label", next(iter(node["source_ids"]), None))
            conn.execute(f"UPDATE knowledge_nodes SET {', '.join(key + ' = ?' for key in changes)}, updated_at = ? WHERE id = ?",
                         [*changes.values(), now_iso(), node_id])
            # An edited concept needs explicit validation again, including a standalone concept.
            metadata = graph.get_node(node_id)["metadata"]
            metadata.pop("standalone_status", None)
            conn.execute("""UPDATE knowledge_nodes SET status = 'to_confirm', validation_status = 'to_confirm',
                business_validation_status = 'corrected_by_user', business_confidence = NULL,
                orphan_status = '', metadata = ? WHERE id = ?""", (json.dumps(metadata), node_id))
            updated = graph.get_node(node_id)
            mapping = graph.infer_archimate_mapping(business_category=updated["business_category"],
                concept_label=updated["label"], status="inferred_from_user_answer")
            conn.execute("UPDATE knowledge_nodes SET archimate_mapping = ?, archimate_mapping_status = 'inferred_from_user_answer' WHERE id = ?",
                         (json.dumps(mapping), node_id))
        edge = None
        if update.target_node_id:
            target = graph.get_node(update.target_node_id)
            if not target:
                raise ValueError("Concept cible introuvable.")
            if target["status"] in {"rejected", "linked"}:
                raise ValueError("Le concept cible est rejete ou fusionne.")
            edge = graph.create_edge(KnowledgeEdgeIn(source_node_id=node_id, target_node_id=update.target_node_id,
                relation_type=update.relation_type, status="accepted", source_ids=node["source_ids"],
                metadata={"origin": "user", "manual_attachment": True, "reason": "Rattachement manuel depuis les orphelins."}))
            conn.execute("UPDATE knowledge_nodes SET orphan_status = '' WHERE id = ?", (node_id,))
            metadata = {**edge["metadata"], "standalone_status": "accepted", "manual_attachment": True}
            conn.execute("""UPDATE knowledge_edges SET status = 'accepted', business_validation_status = 'validated_by_user',
                metadata = ?, validation_decision = ? WHERE id = ?""",
                         (json.dumps(metadata), json.dumps({"origin": "user", "decided_at": now_iso(), "action": "manual_attachment"}), edge["id"]))
        if update.orphan_status:
            if len(users) == 1:
                card = card_service.require_card(users[0])
                if update.orphan_status == "orphan_to_review":
                    card_service.update_card(card["id"], CardUpdate(status="to_confirm"))
                elif card["graph_node_ids"].get("effect") == node_id:
                    card_service.accept_card(card["id"], orphan=True)
            metadata = graph.get_node(node_id)["metadata"]
            status = "accepted" if update.orphan_status == "accepted_orphan" else "to_confirm"
            metadata["standalone_status"] = status
            conn.execute("""UPDATE knowledge_nodes SET orphan_status = ?, status = ?, validation_status = ?,
                business_validation_status = ?, metadata = ?, validation_decision = ?, updated_at = ? WHERE id = ?""",
                (update.orphan_status, status, status, "validated_by_user" if status == "accepted" else "to_review",
                 json.dumps(metadata), json.dumps({"origin": "user", "decided_at": now_iso(), "action": update.orphan_status}), now_iso(), node_id))
        record_change(entity_type="node", entity_id=node_id, action="orphan_updated", origin="user",
                      details={"changes": changes, "orphan_status": update.orphan_status, "edge_id": edge["id"] if edge else None})
    return {"node": graph.get_node(node_id), "edge": edge}
