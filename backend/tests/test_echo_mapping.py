import pytest
from test_mvp import isolated_data_dir
from test_references import TTL
from app.database import db
from app.models.schemas import KnowledgeNodeIn
from app.services import graph_service as graph, reference_service as references, echo_mapping_service as echo


def node(label='Acces', status='accepted'):
    return graph.create_node(KnowledgeNodeIn(label=label,type='object',status=status,description='Possibilite de rejoindre les constructions.'))


def test_exact_mapping_is_only_a_candidate_and_does_not_change_business_or_archimate():
    reference = references.import_reference('Example.ttl',TTL)
    concept = node()
    before = graph.get_node(concept['id'])
    counts = echo.propose(reference['id'],concept['id'])
    assert counts['created'] >= 1
    mapping = echo.mappings(concept['id'])[0]
    assert mapping['match_type']=='exactMatch' and mapping['score']==1
    assert mapping['status']=='candidate'
    assert graph.get_node(concept['id']) == before


def test_alias_and_close_mapping():
    reference = references.import_reference('Example.ttl',TTL)
    synonym = node('Desserte')
    close = node('Mobilites')
    echo.propose(reference['id'])
    assert echo.mappings(synonym['id'])[0]['match_type']=='exactMatch'
    assert echo.mappings(close['id'])[0]['match_type']=='closeMatch'


def test_multiple_mappings_and_rejected_decisions_are_preserved():
    first = references.import_reference('One.ttl',TTL)
    second = references.import_reference('Two.ttl',TTL.replace(b'example.org/echo',b'example.org/second'))
    concept = node()
    echo.propose(node_id=concept['id'])
    found = echo.mappings(concept['id'])
    assert {item['repository_id'] for item in found} == {first['id'],second['id']}
    rejected = echo.decide(found[0]['id'],'closeMatch','rejected')
    counts = echo.propose(node_id=concept['id'])
    assert counts['human_decisions_preserved']==1
    assert next(item for item in echo.mappings(concept['id']) if item['id']==rejected['id']) == rejected


def test_inactive_reference_and_nonvalidated_nodes_are_not_aligned():
    reference = references.import_reference('Example.ttl',TTL)
    concept = node(status='to_confirm')
    with pytest.raises(ValueError):
        echo.propose(reference['id'],concept['id'])
    assert echo.propose(reference['id'])['concepts']==0
    references.set_active(reference['id'],False)
    with pytest.raises(ValueError):
        echo.propose(reference['id'])


def test_unmapped_validated_concept_remains_valid():
    reference = references.import_reference('Example.ttl',TTL)
    concept = graph.create_node(KnowledgeNodeIn(label='Transfert financier',type='object',status='accepted'))
    assert echo.propose(reference['id'],concept['id'])['without_candidate']==1
    assert not echo.mappings(concept['id'])
    assert graph.get_node(concept['id'])['status']=='accepted'


def test_changed_concept_requires_mapping_review_without_overwriting_human_decision():
    reference = references.import_reference('Example.ttl',TTL)
    concept = node()
    echo.propose(reference['id'],concept['id'])
    mapping = echo.decide(echo.mappings(concept['id'])[0]['id'],'exactMatch','validated')
    with db.get_db() as conn:
        conn.execute('UPDATE knowledge_nodes SET description=? WHERE id=?',('Nouveau sens a verifier',concept['id']))
    echo.propose(reference['id'],concept['id'])
    updated = next(item for item in echo.mappings(concept['id']) if item['id']==mapping['id'])
    assert updated['status']=='validated' and updated['stale']
    echo.decide(updated['id'],'closeMatch','validated')
    assert not echo.mappings(concept['id'])[0]['stale']


def test_invalid_mapping_decision_rolls_back():
    reference = references.import_reference('Example.ttl',TTL)
    concept = node()
    echo.propose(reference['id'],concept['id'])
    before = echo.mappings(concept['id'])
    with pytest.raises(ValueError):
        echo.decide(before[0]['id'],'not-a-relation','validated')
    assert echo.mappings(concept['id'])==before


def test_bulk_search_over_200_concepts_uses_comparison_budget(monkeypatch):
    reference = references.import_reference('Example.ttl', TTL)
    concept = node('Transfert financier')
    monkeypatch.setattr(graph, 'list_nodes', lambda: [concept] * 201)
    assert echo.propose(reference['id'])['concepts'] == 201
    monkeypatch.setattr(graph, 'list_nodes', lambda: [concept] * 83334)
    with pytest.raises(ValueError, match='trop grand'):
        echo.propose(reference['id'])
