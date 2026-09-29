"""Materialize confirmed business fields without inferring causal relationships."""
import json

from app.database.db import get_db
from app.models.schemas import KnowledgeNodeIn, KnowledgeEdgeIn
from app.semantic.archimate_mapping import infer_archimate_mapping
from app.services import graph_service as graph, coherence_service as coherence

CATEGORIES = {
    'motivation':'objectif_haut_niveau', 'objects':'chose_metier',
    'actors':'acteur_organisation', 'actions':'action_activite',
    'means':'non_qualifie', 'information':'donnee_manipulee',
    'rules':'condition_regle_contrainte', 'result':'resultat_recherche',
}


def materialize_fields(card, effect_id):
    from app.services.review_service import classify, index, QUESTIONS
    entries = index()
    ids, labels = [], []
    for question, values in card['extraction_details']['simple_fields'].items():
        for field in values:
            text = field['text']
            if not field.get('source_excerpt') and field.get('origin') != 'user':
                continue
            status, target, _ = classify(text, entries)
            explicit = field.get('target') if field.get('mapping_origin') == 'user' else None
            if explicit:
                target = next((e for e in entries if e['id'] == explicit['id']), None)
                if not target:
                    continue
                status = 'known'
            if field.get('force_new'):
                status, target = 'new', None
            # A nearby concept needs its own identity decision, not a duplicate.
            if status == 'review' or (target and target['kind'] == 'echo'):
                continue
            prior = graph.get_node(field.get('node_id','')) if field.get('node_id') else None
            if not target and prior and prior['label'] == text:
                node = prior
            elif target:
                node = graph.get_node(target['id'])
                graph._append_source_to_node(node['id'], [card['document_id']])
            else:
                category = CATEGORIES.get(question, 'non_qualifie')
                node = graph.create_node(KnowledgeNodeIn(
                    label=text, type='object', business_category=category,
                    archimate_mapping=infer_archimate_mapping(business_category=category, concept_label=text,
                        confidence=.4, reason='Candidat prepare depuis la question metier. Nature exacte a confirmer, sans equivalence formelle.'),
                    source_ids=[card['document_id']],
                    metadata={'card_id':card['id'], 'origin':field.get('origin','import'),
                              'source_excerpt':field.get('source_excerpt',''), 'question':question,
                              'force_new':field.get('force_new',False)},
                ))
            if node['id'] == effect_id:
                continue
            if node['id'] not in ids:
                ids.append(node['id'])
                labels.append(node['label'])
            field['node_id'] = node['id']
            edge = graph.create_edge(KnowledgeEdgeIn(
                source_node_id=effect_id, target_node_id=node['id'], relation_type='concerne',
                label=QUESTIONS.get(question,'concerne'), source_ids=[card['document_id']],
                metadata={'card_id':card['id'], 'origin':'import', 'question':question,
                          'source_excerpt':field.get('source_excerpt',''), 'confirmed_by_user':True},
            ))
            coherence.bind_relation(card['id'], edge['id'])
    card['objects'] = labels
    return ids


def synchronize(before, card):
    from app.services.card_service import _node_for_content, _all_card_node_ids
    with get_db() as conn:
        fields = card['extraction_details']['simple_fields']
        removed = {node_id for label,node_id in zip(before['objects'],before['graph_node_ids'].get('objects',[])) if label not in card['objects']}
        for key in fields:
            fields[key] = [v for v in fields[key] if v.get('node_id') not in removed]
        for role,question in [('objects','objects'),('actions','actions'),('conditions','rules'),('tasks','actions')]:
            for label in card[role]:
                if label not in before[role]:
                    fields.setdefault(question,[]).append({'text':label,'origin':'user','source_excerpt':''})
        old_edges = [r[0] for r in conn.execute("SELECT edge_id FROM card_relations WHERE card_id=? AND kind='structural'", (card['id'],))]
        conn.execute("DELETE FROM card_relations WHERE card_id=? AND kind='structural'", (card['id'],))
        main = card['main_effect']
        effect = _node_for_content(card, 'effect', main['label'], before['graph_node_ids'].get('effect'),
                                   description=main['description'], level=card['level'],
                                   business_category=card['business_category'], business_justification=card['business_justification'])
        ids = {'effect':effect, 'theme':'', 'objects':materialize_fields(card,effect),
               'actions':[], 'conditions':[], 'tasks':[]}
        conn.execute('UPDATE extracted_cards SET objects=?,graph_node_ids=?,extraction_details=? WHERE id=?',
                     (json.dumps(card['objects']),json.dumps(ids),json.dumps(card['extraction_details']),card['id']))
        coherence.bind_concepts({**card, 'graph_node_ids':ids})
        coherence.refresh_states(node_ids=_all_card_node_ids(before),edge_ids=old_edges)
