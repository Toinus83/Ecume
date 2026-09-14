import csv
import io
import json
import zipfile

import pytest
from test_mvp import isolated_data_dir
from test_references import TTL
from app.database import db
from app.main import app
from fastapi.testclient import TestClient
from app.models.schemas import KnowledgeNodeIn, KnowledgeEdgeIn
from app.services import graph_service as graph, reference_service as references, echo_mapping_service as echo
from app.services import echo_export_service as exports


def setup():
    reference = references.import_reference('Reference.ttl',TTL)
    mapped = graph.create_node(KnowledgeNodeIn(label='Acces',type='object',status='accepted',description='Une definition metier complementaire.'))
    other = graph.create_node(KnowledgeNodeIn(label='Soutien logistique',type='object',status='accepted',description='Organiser les moyens.'))
    edge = graph.create_edge(KnowledgeEdgeIn(source_node_id=mapped['id'],target_node_id=other['id'],relation_type='concerne',status='accepted'))
    echo.propose(reference['id'],mapped['id'])
    return reference,mapped,other,edge


def test_json_is_self_contained_and_candidate_is_not_an_enrichment():
    reference,mapped,other,edge = setup()
    payload = exports.build_package(reference['id'])
    assert not payload['metadata']['authoritative']
    assert not payload['metadata']['source_reference_modified']
    assert payload['target_reference']['content_hash']==reference['content_hash']
    assert 'source_content' not in payload['target_reference']
    assert not payload['proposed_enrichments']
    assert all(item['status']=='candidate' for item in payload['mappings'])
    assert {item['id'] for item in payload['concepts']}=={mapped['id'],other['id']}
    assert next(item for item in payload['concepts'] if item['id']==other['id'])['classification']=='new_concept'
    assert payload['proposed_relations'][0]['source_label']=='Acces'
    assert payload['control_report']['ready_for_automatic_import'] is False
    assert 'exactMatch' in payload['export_conventions']['mapping_semantics']


def test_only_human_validated_exact_mapping_proposes_non_destructive_enrichment():
    reference,mapped,_,_ = setup()
    mapping = echo.mappings(mapped['id'])[0]
    echo.decide(mapping['id'],'exactMatch','validated')
    payload = exports.build_package(reference['id'])
    assert payload['proposed_enrichments'][0]['target_uri']==mapping['target_uri']
    assert payload['proposed_enrichments'][0]['proposed_definition']==mapped['description']
    assert payload['proposed_enrichments'][0]['existing_definition']
    assert 'never_automatic_replacement' in payload['proposed_enrichments'][0]['strategy']
    assert payload['concepts'][0]['archimate_candidate'] is not None


def test_changed_or_rejected_mapping_is_excluded_from_primary_enrichment():
    reference,mapped,_,_ = setup()
    mapping = echo.mappings(mapped['id'])[0]
    echo.decide(mapping['id'],'exactMatch','validated')
    with db.get_db() as conn:
        conn.execute('UPDATE knowledge_nodes SET description=? WHERE id=?',('Sens modifie',mapped['id']))
    payload = exports.build_package(reference['id'])
    assert not payload['proposed_enrichments']
    assert payload['items_to_review'][0]['effective_status']=='to_review'
    echo.decide(mapping['id'],'exactMatch','rejected')
    payload = exports.build_package(reference['id'])
    assert not payload['mappings'] and not payload['items_to_review']
    assert payload['control_report']['rejected_mappings_excluded']==1


def test_rejected_review_and_broken_edges_never_export_as_validated():
    reference,mapped,_,_ = setup()
    rejected = graph.create_node(KnowledgeNodeIn(label='Rejete',type='object',status='rejected'))
    review = graph.create_node(KnowledgeNodeIn(label='A revoir',type='object',status='to_confirm'))
    graph.create_edge(KnowledgeEdgeIn(source_node_id=mapped['id'],target_node_id=review['id'],relation_type='concerne',status='proposed'))
    payload = exports.build_package(reference['id'])
    ids = {item['id'] for item in payload['concepts']}
    assert rejected['id'] not in ids and review['id'] not in ids
    assert all(item['source_node_id'] in ids and item['target_node_id'] in ids for item in payload['proposed_relations'])
    assert all(item['status'] in {'accepted','accepted_orphan'} for item in payload['proposed_relations'])
    assert payload['control_report']['rejected_nodes_excluded']==1


def test_csv_bundle_contains_review_files_json_and_report_and_escapes_formulas():
    reference,_,_,_ = setup()
    graph.create_node(KnowledgeNodeIn(label='=HYPERLINK("https://example.org")',type='object',status='accepted'))
    with zipfile.ZipFile(exports.export_csv(reference['id'])) as bundle:
        assert set(bundle.namelist())=={'echo_new_concepts.csv','echo_enrichments.csv','echo_mappings.csv','echo_relations.csv',
            'echo_warnings.csv','echo_enrichment.json','echo_control_report.json','README.txt'}
        rows = list(csv.DictReader(io.StringIO(bundle.read('echo_new_concepts.csv').decode('utf-8-sig'))))
        assert any(row['label'].startswith("'=HYPERLINK") for row in rows)
        payload = json.loads(bundle.read('echo_enrichment.json'))
        assert any(item['label'].startswith('=HYPERLINK') for item in payload['concepts'])
        assert json.loads(bundle.read('echo_control_report.json'))['concepts']==3


def test_empty_legacy_base_and_partial_profile_export_cleanly():
    db.init_db()
    reference = references.import_reference('Partial.ttl',b'<https://example.org/a> <https://example.org/name> "Unknown".')
    payload = exports.build_package(reference['id'])
    assert payload['concepts']==[]
    assert payload['detected_profile']['status']=='partial' and payload['warnings']
    with TestClient(app) as client:
        response=client.get(f"/references/{reference['id']}/export/json")
        assert response.status_code==200
        assert response.json()['control_report']['concepts']==0
        assert client.get(f"/references/{reference['id']}/export/ttl").status_code==400


def test_explicit_secondary_retention_and_purge_preserve_useful_evidence():
    from test_salience import store
    from app.services import card_service as cards, salience_service as salience, document_service as documents
    reference = references.import_reference('Reference.ttl',TTL)
    card = store()
    cards.accept_card(card['id'])
    payload = exports.build_package(reference['id'])
    assert all(item['label'] not in {'Batiment','Chose'} for item in payload['concepts'])
    secondary = next(item for item in card['extraction_details']['concepts'] if item['label']=='Batiment')
    salience.decide_concept(card['id'],secondary['id'],'retain')
    assert not exports.build_package(reference['id'])['concepts']
    cards.accept_card(card['id'])
    documents.purge_source(card['document_id'])
    payload = exports.build_package(reference['id'])
    retained = next(item for item in payload['concepts'] if item['label']=='Batiment')
    assert retained['salience_by_card'][0]['importance']=='secondary'
    assert retained['salience_by_card'][0]['retained']
    assert payload['sources'][0]['source_status']=='purged'
    assert payload['evidence_cards'][0]['rule_details']
    assert 'content_text' not in payload['sources'][0]


def test_source_used_only_by_a_relation_is_self_contained():
    from test_documents import upload
    reference,_,_,edge = setup()
    document = upload()
    with db.get_db() as conn:
        conn.execute('UPDATE knowledge_edges SET source_ids=?,metadata=? WHERE id=?',
                     (json.dumps([document['id']]), json.dumps({**edge['metadata'],
                      'source_excerpt':'Extrait justifiant uniquement le lien.'}), edge['id']))
    payload = exports.build_package(reference['id'])
    assert any(source['id']==document['id'] for source in payload['sources'])
    assert payload['proposed_relations'][0]['source_excerpt']=='Extrait justifiant uniquement le lien.'
