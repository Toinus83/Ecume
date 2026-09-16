import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_mvp import isolated_data_dir
from test_documents import upload
from app.main import app
from app.database import db
from app.models.schemas import KnowledgeNodeIn, CardUpdate
from app.services import reference_service as refs, graph_service as graph, echo_export_service as exports
from app.services import echo_mapping_service as mappings, echo_workshop as workshop, business_rule_service as rules
from app.services import analysis_service as analysis, card_service as cards

PREFIX=b'''@prefix e: <https://example.org/echo#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
'''
OWL=PREFIX+b'''e:Construction a owl:Class; rdfs:label "Construction".
e:Distance a owl:Class; rdfs:label "Distance minimale".
e:value a owl:DatatypeProperty; rdfs:label "valeur"; rdfs:domain e:Distance; rdfs:range xsd:decimal.
e:unit a owl:DatatypeProperty; rdfs:label "unite"; rdfs:domain e:Distance; rdfs:range xsd:string.
e:source a owl:ObjectProperty; rdfs:label "source".
'''
VOC=PREFIX+b'''e:Building a skos:Concept; skos:prefLabel "Construction"; skos:altLabel "Batiment";
 skos:hiddenLabel "construction neuve"; skos:definition "Ouvrage construit"; skos:broader e:Asset; skos:related e:Limit.
e:Asset a skos:Concept; skos:prefLabel "Bien"; skos:narrower e:Building.
e:Limit a skos:Concept; skos:prefLabel "Limite separative".
'''
SHACL=PREFIX+b'''e:DistanceShape a sh:NodeShape; sh:targetClass e:Distance;
 sh:property [sh:path e:value; sh:minCount 1; sh:maxCount 1; sh:datatype xsd:decimal];
 sh:property [sh:path e:unit; sh:minCount 1; sh:in ("m" "cm")];
 sh:property [sh:path e:source; sh:minCount 1; sh:nodeKind sh:IRI].
e:VocabularyShape a sh:NodeShape; sh:targetClass skos:Concept;
 sh:property [sh:path skos:prefLabel; sh:minCount 1];
 sh:property [sh:path skos:definition; sh:minCount 1].
'''


def package():
    fixtures=Path(__file__).with_name('fixtures')
    a=refs.import_reference('Echo_Test.owl.ttl',(fixtures/'Echo_Test.owl.ttl').read_bytes())
    b=refs.import_reference('Echo_Test.voc.ttl',(fixtures/'Echo_Test.voc.ttl').read_bytes())
    c=refs.import_reference('Echo_Test.shacl.ttl',(fixtures/'Echo_Test.shacl.ttl').read_bytes())
    assert a['id']==b['id']==c['id']
    return c


def concept(label='Construction',description='Ouvrage construit'):
    return graph.create_node(KnowledgeNodeIn(label=label,type='object',description=description,status='accepted'))


@pytest.mark.parametrize('data,layer_name',[(OWL,'owl'),(VOC,'voc'),(SHACL,'shacl')])
def test_individual_layers(data,layer_name):
    result=refs.import_reference('One.ttl',data)
    assert result['profile']['echo']['layers'][layer_name]['state'] in {'imported','partial'}
    assert result['profile']['echo']['rdf_read']
    assert not result['profile']['echo']['rdf_export_ready']


def test_logical_repository_three_layers_and_source_bytes_preserved():
    result=package()
    profile=result['profile']['echo']
    assert len(refs.list_repositories())==1
    assert len(profile['files'])==3
    assert len(profile['owl']['classes'])==2 and len(profile['owl']['properties'])==3
    assert profile['voc']['term_count']==3 and profile['voc']['alias_count']>=2
    assert profile['shacl']['interpreted']==7 and profile['shacl']['uninterpreted']==0
    assert profile['confidence']=='sufficient'
    with db.get_db() as conn:
        for row in conn.execute('SELECT * FROM reference_files'):
            assert hashlib.sha256(row['source_content']).hexdigest()==row['content_hash']


@pytest.mark.parametrize('extension',['ttl','xml','shacl'])
def test_mixed_file_and_local_extensions(extension):
    result=refs.import_reference('Mixed.'+extension,OWL+VOC+SHACL,layer='mixed')
    assert all(v['state']!='not_provided' for v in result['profile']['echo']['layers'].values())


def test_explicit_association_and_layer_correction_are_idempotent():
    first=refs.import_reference('A.ttl',OWL)
    refs.import_reference('B.ttl',VOC,first['id'],'voc')
    refs.import_reference('B-renamed.ttl',VOC,first['id'],'mixed')
    assert len(refs.files(first['id']))==2
    assert any(f['layer']=='mixed' for f in refs.files(first['id']))


def test_unsupported_shapes_and_insufficient_profile_are_explicit():
    unknown=SHACL+b'e:Complex a sh:NodeShape; sh:targetClass e:Distance; sh:sparql [sh:select "SELECT ?this WHERE {}"].'
    result=refs.import_reference('Complex.shacl.ttl',unknown)
    assert result['profile']['echo']['shacl']['uninterpreted']==1
    empty=refs.import_reference('Custom.ttl',PREFIX+b'e:a e:custom "value".',layer='voc')
    assert empty['profile']['echo']['confidence']=='insufficient'
    assert empty['profile']['echo']['layers']['voc']['state']=='insufficient'


def test_automatic_recognition_alias_and_owl_voc_separation():
    reference=package()
    node=concept()
    before=graph.get_node(node['id'])
    payload=exports.build_package(reference['id'])
    recognized=payload['recognized_existing_echo_elements']
    assert {m['target_layer'] for m in recognized}=={'owl','voc'}
    assert all(m['status']=='candidate' for m in recognized)
    assert not payload['proposed_new_concepts']
    assert graph.get_node(node['id'])==before
    alias=concept('Batiment')
    payload=exports.build_package(reference['id'])
    assert any(m['node_id']==alias['id'] and m['target_layer']=='voc' for m in payload['recognized_existing_echo_elements'])


def test_ambiguous_or_rejected_mapping_is_never_silently_recognized():
    reference=package()
    node=concept()
    exports.build_package(reference['id'])
    m=mappings.mappings(node['id'])[0]
    mappings.decide(m['id'],'exactMatch','rejected')
    more=PREFIX+b'e:Alternative a skos:Concept; skos:prefLabel "Construction".'
    refs.import_reference('More.ttl',more,reference['id'])
    payload=exports.build_package(reference['id'])
    assert all(m['target_layer']!='voc' for m in payload['recognized_existing_echo_elements'])
    assert not any(item.get('id')==m['id'] for item in payload['proposed_owl_alignments']+payload['proposed_voc_alignments'])
    assert next(i for i in mappings.mappings(node['id']) if i['id']==m['id'])['status']=='rejected'


def rule_card(unit='m'):
    doc=upload(b'Les constructions sont implantees a 4 m de la limite.')
    raw={'main_effect':{'label':'Implantation','description':'Distance minimale de 4 m.'},'business_category':'regle_contrainte',
         'source_excerpt':'Les constructions sont implantees a 4 m de la limite.',
         'business_rules':[{'label':'Distance minimale','description':'Distance minimale de 4 metres.', 'value':'4','unit':unit,
            'owl_class_uri':'https://example.org/echo#Distance','source_excerpt':'Les constructions sont implantees a 4 m de la limite.'}]}
    card=analysis._store_card(doc,raw,[],extraction_mode='sober')
    return cards.accept_card(card['id'])


@pytest.mark.parametrize('unit,status',[('m','conformant'),('','to_complete'),('km','nonconformant')])
def test_business_rule_value_unit_source_and_shacl(unit,status):
    reference=package()
    card=rule_card(unit)
    payload=exports.build_package(reference['id'])
    rule=payload['ecume_rules'][0]
    assert rule['value']=='4' and rule['unit']==unit and rule['source_document_id']==card['document_id']
    checks=[c for c in payload['shacl_checks'] if c['element_id']==rule['id']]
    assert any(c['status']==status for c in checks),checks
    assert all(c['status']!='not_verifiable' for c in checks),checks
    assert payload['control_report']['ready_for_automatic_import'] is False


def test_unknown_path_is_not_verified_and_new_concept_gets_vocabulary_check():
    reference=package()
    refs.import_reference('Extra.ttl',PREFIX+b'e:S a sh:NodeShape; sh:targetClass skos:Concept; sh:property [sh:path e:zone; sh:minCount 1].',reference['id'])
    node=concept('Gestion energetique','')
    payload=exports.build_package(reference['id'])
    assert payload['proposed_new_concepts'][0]['id']==node['id']
    assert payload['proposed_voc_terms'][0]['label']==node['label']
    checks=payload['shacl_checks']
    assert any(c['status']=='to_complete' for c in checks)
    assert any(c['status']=='not_verifiable' for c in checks)


def test_rule_correction_invalidates_card_not_shared_knowledge():
    reference=package()
    card=rule_card()
    rule=rules.from_card(card)[0]
    updated=rules.update(card['id'],rule['id'],{'unit':'cm'})
    assert updated['status']=='to_confirm'
    assert not exports.build_package(reference['id'])['ecume_rules']
    assert updated['extraction_details']['business_rules'][0]['unit']=='cm'


def test_context_is_bounded_and_includes_expected_properties():
    package()
    context=json.loads(workshop.extraction_context('Construction distance minimale Batiment'))
    assert context[0]['terms'] and context[0]['expected_rules']
    assert len(json.dumps(context,ensure_ascii=False))<=9000


def test_migrations_preserve_old_repository_and_human_decision():
    reference=package()
    node=concept()
    exports.build_package(reference['id'])
    mapping=mappings.mappings(node['id'])[0]
    mappings.decide(mapping['id'],'closeMatch','validated')
    before=mappings.mappings(node['id'])
    db.init_db(); db.init_db()
    assert mappings.mappings(node['id'])==before
    assert len(refs.files(reference['id']))==3


def test_http_layer_import_card_report_json_csv_and_source_deletion():
    with TestClient(app) as client:
        response=client.post('/references/import',files={'file':('Echo_Test.owl.ttl',OWL)},data={'layer':'owl'})
        assert response.status_code==200
        rid=response.json()['id']
        for filename,data,layer_name in [('Echo_Test.voc.ttl',VOC,'voc'),('Echo_Test.shacl.ttl',SHACL,'shacl')]:
            assert client.post('/references/import',files={'file':(filename,data)},data={'repository_id':rid,'layer':layer_name}).status_code==200
        card=rule_card()
        assert client.get('/references/cards/'+card['id']+'/workshop').json()[0]['rules']
        report=client.get('/references/'+rid+'/report').json()
        assert report['new_business_rules']==1
        with zipfile.ZipFile(exports.export_csv(rid)) as archive:
            assert 'echo_shacl_report.csv' in archive.namelist()
            assert json.loads(archive.read('echo_enrichment.json'))['ecume_rules']
        refs.delete_repository(rid,'SUPPRIMER')
        assert analysis.get_card(card['id'])


def test_target_definition_change_marks_human_mapping_stale():
    reference=package(); node=concept()
    exports.build_package(reference['id'])
    mapping=next(m for m in mappings.mappings(node['id']) if m['target_uri'].endswith('Building'))
    mappings.decide(mapping['id'],'exactMatch','validated')
    refs.import_reference('Definition.ttl',PREFIX+b'e:Building skos:definition "Autre definition.".',reference['id'])
    updated=next(m for m in mappings.mappings(node['id']) if m['id']==mapping['id'])
    assert updated['status']=='validated' and updated['stale']
    assert not any(m['id']==mapping['id'] for m in exports.build_package(reference['id'])['recognized_existing_echo_elements'])


def test_analysis_receives_three_layer_context_and_preserves_rules(monkeypatch):
    import asyncio
    reference=package()
    doc=upload()
    with db.get_db() as conn:
        conn.execute('UPDATE source_documents SET content_text=? WHERE id=?',('Construction : distance minimale de 4 m.',doc['id']))
    class Provider:
        async def analyze_document(self,**kwargs):
            context=json.loads(self.echo_context)
            assert context[0]['terms'] and context[0]['expected_rules']
            return {'cards':[{'main_effect':{'label':'Distance minimale','description':'Distance de 4 m.'},'source_excerpt':'Construction : distance minimale de 4 m.',
                'business_rules':[{'label':'Distance minimale','value':'4','unit':'m','source_excerpt':'Construction : distance minimale de 4 m.'}]}]}
    monkeypatch.setattr(analysis,'_provider',lambda:Provider())
    result=asyncio.run(analysis.analyze_document(doc['id']))
    card=result['cards'][0]
    rule=card['extraction_details']['business_rules'][0]
    assert rule['value']=='4' and rule['source_verified']
    cards.accept_card(card['id'])
    assert exports.build_package(reference['id'])['ecume_rules']


def test_invented_rule_source_is_flagged_without_deleting_proposal():
    document={'id':'source','content_text':'Une construction.'}
    extracted=rules.extract({'business_rules':[{'label':'Distance','value':'4','source_excerpt':'Extrait invente.'}]})
    assert rules.verify_sources(extracted,document)
    assert len(extracted)==1 and not extracted[0]['source_verified']


def test_relation_target_class_is_checked_on_working_projection():
    from app.models.schemas import KnowledgeEdgeIn
    reference=package()
    additional=PREFIX+b'''e:concerne a owl:ObjectProperty; rdfs:label "concerne".
e:RelationShape a sh:NodeShape; sh:targetClass e:Construction;
 sh:property [sh:path e:concerne; sh:class e:Distance].'''
    refs.import_reference('Relations.ttl',additional,reference['id'])
    source=concept(); target=concept('Bien')
    graph.create_edge(KnowledgeEdgeIn(source_node_id=source['id'],target_node_id=target['id'],relation_type='concerne',status='accepted'))
    payload=exports.build_package(reference['id'])
    assert any(c['element_id']==source['id'] and c.get('constraint','').endswith('ClassConstraintComponent') and c['status']=='nonconformant' for c in payload['shacl_checks'])


def test_shacl_timeout_never_means_conformant_and_can_retry(monkeypatch):
    import subprocess
    reference=package(); concept()
    def timeout(*args,**kwargs):
        raise subprocess.TimeoutExpired('worker',20)
    monkeypatch.setattr(workshop.subprocess,'run',timeout)
    payload=exports.build_package(reference['id'])
    assert all(c['status']=='not_verifiable' and c['retryable'] for c in payload['shacl_checks'])
