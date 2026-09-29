import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from test_mvp import isolated_data_dir
from test_documents import upload
from app.database import db
from app.main import app
from app.models.schemas import KnowledgeNodeIn, ManualCardRequest, MainEffect
from app.services import review_service as review, graph_service as graph
from app.services import analysis_service as analysis, document_service as documents
from app.services import card_service, export_service, job_service, validation_service


class Provider:
    def __init__(self, response):
        self.response = response

    async def analyze_document(self, **kwargs):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def run(response, text='Detection sonar avec Operateur SONAR.', mode='prefilled', source=None):
    source = source or upload(text.encode())
    result = asyncio.run(review.analyze(source, Provider(response), [text], fill_mode=mode))
    return source, result, review.workspace(source['id'])


def concept(label='Detection sonar', **kw):
    return {'label':label, 'description':'Detection sonar avec Operateur SONAR.',
            'source_excerpt':'Detection sonar avec Operateur SONAR.', **kw}


def known(label='Operateur SONAR'):
    return graph.create_node(KnowledgeNodeIn(label=label,type='object',status='accepted',
        business_validation_status='validated_by_user',metadata={'origin':'user'}))


def test_empty_analysis_is_explained_and_numeric_sources_are_not_cards():
    source, result, work = run({'concepts':[], 'warnings':['Aucune notion identifiee.']}, 'Distance minimale de 4 m sauf exception.')
    assert result['review_report']['text_read']
    assert result['review_report']['concepts_found'] == 0
    assert any('4 m' in i.get('source_excerpt','') for i in work['reports'][0]['issues'])
    assert not work['items'] and not analysis.list_cards() and not graph.list_nodes()
    assert documents.get_document(source['id'])['content_text']


@pytest.mark.parametrize('label', ['Passages du document a verifier','Texte a controler','Analyse partielle','Aucune extraction'])
def test_diagnostics_never_become_concepts(label):
    _, result, work = run({'concepts':[concept(label)]})
    assert not work['items']
    assert result['review_report']['issues']
    assert not graph.list_nodes()


def test_mentions_wait_for_validation_then_fields_reuse_validated_identity():
    actor = known()
    _, _, work = run({'concepts':[concept(fields={'actors':[{'text':'Operateur SONAR','source_excerpt':'Detection sonar avec Operateur SONAR.'}]})]})
    item = next(i for i in work['items'] if i['label']=='Detection sonar')
    assert len(graph.list_nodes()) == 1
    accepted = review.decide(item['id'], {'action':'accept'})
    assert accepted['status'] == 'validated'
    card = analysis.get_card(accepted['card_id'])
    assert card['graph_node_ids']['objects'] == [actor['id']]
    assert len(graph.graph_payload()['nodes']) == 2
    assert len(graph.graph_payload()['edges']) == 1
    assert graph.graph_payload()['edges'][0]['relation_type'] == 'concerne'
    review.decide(item['id'], {'action':'accept'})
    assert len(graph.list_nodes()) == 2


def test_manual_mode_does_not_prefill_or_create_links():
    _, _, work = run({'concepts':[concept(fields={'actors':[{'text':'Operateur SONAR','source_excerpt':'Detection sonar avec Operateur SONAR.'}]})]}, mode='manual')
    item = work['items'][0]
    assert not any(item['fields'].values())
    review.decide(item['id'], {'action':'accept'})
    assert len(graph.graph_payload()['nodes']) == 1
    assert not graph.list_edges()


def test_known_alias_visible_without_new_card_even_when_model_returns_nothing():
    actor = known()
    graph._attach_variant(actor['id'],'OSM','synonym','')
    _, result, work = run({'concepts':[]}, 'OSM intervient sur le contact.')
    assert result['review_report']['known_ecume'] == 1
    assert work['items'][0]['label'] == 'OSM'
    assert work['items'][0]['target']['id'] == actor['id']
    assert not analysis.list_cards()


def test_ambiguous_match_requires_identity_choice():
    actor = known()
    _, _, work = run({'concepts':[concept('Operateurs SONAR')]}, 'Les Operateurs SONAR suivent les contacts.')
    item = next(i for i in work['items'] if i['label']=='Operateurs SONAR')
    assert item['status'] == 'review'
    assert item['candidates'][0]['score'] >= .5
    assert item['candidates'][0]['reason'] and item['candidates'][0]['source'] == 'graphe ECUME'
    with pytest.raises(ValueError, match='proche'):
        review.decide(item['id'],{'action':'accept'})
    attached = review.decide(item['id'],{'action':'attach','target_id':actor['id']})
    assert attached['status']=='known'
    review.decide(item['id'],{'action':'new'})
    created = review.decide(item['id'],{'action':'accept'})
    assert created['node_id'] != actor['id']


def test_unsourced_fields_are_empty_and_reported():
    _, _, work = run({'concepts':[concept(fields={'actors':[{'text':'Amiral','source_excerpt':'Amiral invente'}]})]})
    item = work['items'][0]
    assert item['status']=='review' and not item['fields']['actors']
    assert item['issues']


def test_editing_validated_fields_withdraws_only_local_claim_and_preserves_sources():
    actor = known()
    _, _, work = run({'concepts':[concept(fields={'actors':[{'text':'Operateur SONAR','source_excerpt':'Detection sonar avec Operateur SONAR.'}]})]})
    item = next(i for i in work['items'] if i['label']=='Detection sonar')
    saved = review.decide(item['id'],{'action':'accept'})
    review.decide(item['id'],{'action':'update','fields':{'actors':['Operateur SONAR'],'means':['Console']} })
    assert graph.get_node(actor['id'])['status']=='accepted'
    updated = next(i for i in review.workspace()['items'] if i['id']==item['id'])
    assert updated['fields']['actors'][0]['source_excerpt']
    assert updated['fields']['means'][0]['origin']=='user'
    assert saved['node_id'] not in {n['id'] for n in graph.graph_payload()['nodes']}
    review.decide(item['id'],{'action':'accept'})
    assert {'Detection sonar','Console','Operateur SONAR'} == {n['label'] for n in graph.graph_payload()['nodes']}


def test_editing_one_field_preserves_known_concept_identity():
    actor = known()
    _, _, work = run({'concepts':[]}, 'Operateur SONAR intervient sur le contact.')
    item = next(i for i in work['items'] if i['target'] and i['target']['id'] == actor['id'])

    updated = review.decide(item['id'], {
        'action':'update',
        'preserve_identity':True,
        'fields':{'actors':['Operateur SONAR']},
    })

    assert updated['status'] == 'review'
    assert updated['target']['id'] == actor['id']
    assert len(graph.list_nodes()) == 1


def test_acceptance_rolls_back_all_materialization(monkeypatch):
    _, _, work = run({'concepts':[concept()]})
    def fail(*a,**k):
        raise ValueError('interruption')
    monkeypatch.setattr(card_service,'accept_card',fail)
    with pytest.raises(ValueError):
        review.decide(work['items'][0]['id'],{'action':'accept'})
    assert not analysis.list_cards() and not graph.list_nodes()
    assert review.workspace()['items'][0]['status']=='new'


@pytest.mark.parametrize('response',[{}, {'concepts':'incorrect'}, ValueError('LLM indisponible')])
def test_analysis_failure_is_reported_not_silent_empty_success(response):
    _, result, _ = run(response)
    assert result['review_report']['analysis_problem']
    assert result['warnings']


def test_source_purge_keeps_mentions_and_export_provenance():
    known()
    source, _, _ = run({'concepts':[]})
    documents.purge_source(source['id'])
    work=review.workspace(source['id'])
    assert work['items'][0]['source_excerpt']
    payload=export_service._complete_export_payload()
    assert payload['document_mentions']
    assert source['id'] in payload['nodes'][0]['source_ids']


def test_migrations_additive_and_thresholds_unchanged():
    before=validation_service.get_settings()
    source, _, work=run({'concepts':[concept()]})
    db.init_db(); db.init_db()
    assert validation_service.get_settings()==before
    assert review.workspace(source['id'])['items']==work['items']


def test_failed_job_never_purges_source(monkeypatch):
    source=upload()
    with db.get_db() as conn:
        conn.execute("UPDATE source_documents SET retention_policy='purge_after_success' WHERE id=?",(source['id'],))
    monkeypatch.setattr(analysis,'_provider',lambda:Provider(ValueError('hors ligne')))
    async def process():
        job=job_service.start_analysis_job(source['id'],fill_mode='prefilled')
        await asyncio.gather(*list(job_service._tasks))
        return job_service.get_job(job['id'])
    job=asyncio.run(process())
    assert job['status']=='failed'
    assert job['metadata']['review_report']['analysis_problem']
    assert documents.get_document(source['id'])['content_text']


def test_review_api_and_target_search_limit():
    for i in range(12): known(f'Acteur {i:02}')
    with TestClient(app) as client:
        assert len(client.get('/review/targets?q=Acteur').json())==8
        assert client.get('/review/targets?q=A').json()==[]
        assert client.get('/review').status_code==200
        assert client.post('/review/absent/decision',json={'action':'accept'}).status_code==400


def test_echo_three_layers_recognized_without_materializing_duplicate_and_exported():
    from test_echo_layers import package
    from app.services import echo_export_service
    repository=package()
    _, result, work=run({'concepts':[]},'La Construction respecte les limites.')
    assert result['review_report']['known_echo']==1
    assert work['items'][0]['target']['kind']=='echo'
    assert work['items'][0]['target']['layer']=='voc'
    assert not graph.list_nodes()
    # Existing export keeps known document mentions even with no new local node.
    # Exercise the public package projection used by JSON and CSV.
    path=echo_export_service.export_json(repository['id'])
    payload=json.loads(path.read_text(encoding='utf-8'))
    assert payload['recognized_document_mentions'][0]['label']=='Construction'


def test_ontology_review_bundle_is_explicit_complete_and_conservative():
    import zipfile
    from rdflib import Graph
    from rdflib.namespace import RDF, OWL, SH
    from app.services.ontology_draft import export_bundle
    known()
    run({'concepts':[concept()]})
    with zipfile.ZipFile(export_bundle()) as bundle:
        expected={'ecume_draft.owl.ttl','ecume_draft.voc.ttl','ecume_draft.shacl.ttl',
                  'ecume_knowledge.json','README.txt','manifest.json','proposals.csv','control_report.html'}
        assert expected <= set(bundle.namelist())
        for name in ('ecume_draft.owl.ttl','ecume_draft.voc.ttl','ecume_draft.shacl.ttl'):
            assert len(Graph().parse(data=bundle.read(name),format='turtle'))>0
        payload=json.loads(bundle.read('ecume_knowledge.json'))
        assert [n['label'] for n in payload['nodes']]==['Operateur SONAR']
        manifest=json.loads(bundle.read('manifest.json'))
        assert manifest['statut']=='review_required'
        assert manifest['nombre_propositions_voc']==1
        assert manifest['nombre_propositions_owl']==0
        assert manifest['nombre_propositions_shacl']==0
        owl_graph=Graph().parse(data=bundle.read('ecume_draft.owl.ttl'),format='turtle')
        shacl_graph=Graph().parse(data=bundle.read('ecume_draft.shacl.ttl'),format='turtle')
        assert not list(owl_graph.subjects(RDF.type,OWL.Class))
        assert not list(shacl_graph.subjects(RDF.type,SH.NodeShape))
        assert 'Proposition à revoir' in bundle.read('README.txt').decode()
        assert 'ECUME ne modifie pas directement le référentiel Echo' in bundle.read('control_report.html').decode()


def test_document_domain_is_proposed_then_confirmed_explicitly():
    source,_,_=run({'concepts':[]},'Le recrutement et la formation du personnel structurent les ressources humaines.')
    summary=documents.document_summary(source['id'])
    assert summary['proposed_domain']=='RH'
    assert summary['domain_status']=='unconfirmed'
    updated=documents.confirm_domain(source['id'],'RH',['FORMATION'])
    assert updated['confirmed_domain']=='RH'
    assert updated['secondary_domains']==['FORMATION']
    assert updated['domain_status']=='confirmed'


def test_alias_decision_reuses_local_concept_and_records_variant():
    actor=known('Maire')
    _,_,work=run({'concepts':[concept('Le maire')]},'Le maire valide le permis.')
    item=next(value for value in work['items'] if value['label']=='Le maire')
    decided=review.decide(item['id'],{'action':'alias','target_id':actor['id']})
    assert decided['status']=='known' and decided['target']['id']==actor['id']
    with db.get_db() as conn:
        aliases=[row['label'] for row in conn.execute('SELECT label FROM knowledge_node_aliases WHERE node_id=?',(actor['id'],))]
    assert 'Le maire' in aliases


def test_import_can_be_stopped_without_persisting_partial_document():
    import io
    from fastapi import UploadFile
    upload_id='cancel-upload-test'
    class CancellingStream(io.BytesIO):
        def read(self,*args,**kwargs):
            value=super().read(*args,**kwargs)
            if value:
                documents.request_import_cancel(upload_id)
            return value
    with pytest.raises(ValueError,match='arrêté'):
        documents._save_upload(UploadFile(filename='large.txt',file=CancellingStream(b'x'*2048)),upload_id)
    assert not documents.list_documents()


def test_full_delete_and_reset_remove_review_records_but_purge_does_not():
    from app.services.admin_service import reset_database
    source,_,_=run({'concepts':[concept()]})
    documents.delete_document(source['id'],confirmation='SUPPRIMER',delete_knowledge=True,
        knowledge_confirmation='SUPPRIMER LES CONNAISSANCES')
    assert not review.workspace()['items'] and not review.workspace()['reports']
    run({'concepts':[concept()]})
    reset_database(confirmation='RESET ECUME',delete_uploads=False,delete_exports=False)
    assert not review.workspace()['items'] and not review.workspace()['reports']


def test_external_card_edit_is_reflected_without_restoring_stale_content():
    from app.models.schemas import CardUpdate
    _,_,work=run({'concepts':[concept()]})
    item=review.decide(work['items'][0]['id'],{'action':'accept'})
    card=analysis.get_card(item['card_id'])
    card_service.update_card(card['id'],CardUpdate(main_effect={**card['main_effect'],'description':'Correction depuis le graphe'}))
    updated=next(i for i in review.workspace()['items'] if i['id']==item['id'])
    assert updated['status']=='review' and updated['description']=='Correction depuis le graphe'
    review.decide(item['id'],{'action':'accept'})
    assert analysis.get_card(card['id'])['main_effect']['description']=='Correction depuis le graphe'


def test_known_short_acronym_and_withdrawn_target():
    node=known('C2')
    _,_,work=run({'concepts':[]},'Le C2 coordonne les acteurs.')
    assert work['items'][0]['status']=='known'
    graph.delete_node(node['id'])
    assert review.workspace()['items'][0]['status']=='review'


def test_edit_remains_possible_after_document_deleted_without_knowledge():
    source,_,work=run({'concepts':[concept()]})
    item=review.decide(work['items'][0]['id'],{'action':'accept'})
    documents.delete_document(source['id'],confirmation='SUPPRIMER')
    review.decide(item['id'],{'action':'update','description':'Correction humaine conservee'})
    assert review.decide(item['id'],{'action':'accept'})['status']=='validated'


def test_unsourced_rule_number_is_not_exported_as_business_knowledge():
    _,_,work=run({'concepts':[concept(business_rules=[{'label':'Distance','value':'99','unit':'m','source_excerpt':'Detection sonar avec Operateur SONAR.'}])]})
    item=work['items'][0]
    assert not item['business_rules']
    assert item['status']=='review'


def test_unknown_mapping_offers_relevant_business_choices_and_persists_user_answer():
    text='Les espaces publics accueillent les usages du quartier.'
    raw={'concepts':[{'label':'espaces publics','description':text,'source_excerpt':text}]}
    _,_,work=run(raw,text)
    item=work['items'][0]
    assert item['archimate_mapping']['candidate_element']=='Unknown'
    assert len(item['qualification_choices'])==3
    assert item['qualification_choices'][0]['category']=='lieu_environnement_physique'
    assert item['qualification_choices'][0]['mapping']['candidate_element']=='Facility'
    review.decide(item['id'],{'action':'qualify','business_category':'lieu_environnement_physique'})
    qualified=next(i for i in review.workspace()['items'] if i['id']==item['id'])
    assert qualified['category']=='lieu_environnement_physique'
    assert qualified['archimate_mapping']['candidate_element']=='Facility'
    accepted=review.decide(item['id'],{'action':'accept'})
    card=analysis.get_card(accepted['card_id'])
    assert card['business_category']=='lieu_environnement_physique'
    assert card['archimate_mapping']['candidate_layer']=='Physical'
    assert card['archimate_mapping']['candidate_element']=='Facility'


def test_qualification_is_an_explicit_user_decision_and_does_not_change_identity():
    _,_,work=run({'concepts':[concept()]})
    item=work['items'][0]
    review.decide(item['id'],{'action':'qualify','business_category':'action_activite'})
    with db.get_db() as conn:
        row=conn.execute("SELECT * FROM change_log WHERE entity_type='mention' AND entity_id=? ORDER BY created_at DESC",(item['id'],)).fetchone()
    assert row['action']=='qualify' and row['origin']=='user'
    assert not graph.list_nodes()


def test_legacy_validated_card_can_be_qualified_without_losing_validation():
    source=upload()
    card=analysis.create_manual_card(ManualCardRequest(
        document_id=source['id'],theme_label='Territoire',
        main_effect=MainEffect(label='Espaces publics'),
        source_excerpt='Espaces publics'))
    card_service.accept_card(card['id'])
    review.decide('legacy:'+card['id'],{'action':'qualify','business_category':'lieu_environnement_physique'})
    updated=analysis.get_card(card['id'])
    assert updated['status'] in {'accepted','accepted_orphan'}
    assert updated['business_category']=='lieu_environnement_physique'
    assert updated['archimate_mapping']['candidate_element']=='Facility'


def test_user_stop_keeps_only_concepts_from_completed_chunks():
    class PartialProvider:
        fill_mode = 'prefilled'
        calls = 0
        async def analyze_document(self, **kwargs):
            self.calls += 1
            text = kwargs['content_text']
            label = 'Premier concept' if self.calls == 1 else 'Second concept'
            return {'concepts':[{'label':label,'description':text,'source_excerpt':text}]}

    source = upload(b'Premier concept document.\n\nSecond concept document.')
    provider = PartialProvider()
    result = asyncio.run(review.analyze(
        source, provider, ['Premier concept document.', 'Second concept document.'],
        fill_mode='prefilled', cancel_check=lambda: provider.calls >= 1,
    ))
    assert result['cancelled'] is True
    assert result['review_report']['chunks_processed'] == 1
    assert [item['label'] for item in review.workspace(source['id'])['items']] == ['Premier concept']


def test_job_cancellation_is_not_failure_and_never_purges_source(monkeypatch):
    source = upload()
    with db.get_db() as conn:
        conn.execute("UPDATE source_documents SET retention_policy='purge_after_success' WHERE id=?", (source['id'],))

    async def partial_analysis(document_id, progress_callback=None, cancel_check=None, **kwargs):
        if progress_callback:
            progress_callback({'step':'llm_analysis','progress':35,'current_chunk':1,'total_chunks':3})
        while not cancel_check():
            await asyncio.sleep(0.01)
        return {'document_id':document_id, 'cards':[{'id':'partial-card'}], 'warnings':[], 'cancelled':True,
                'review_report':{'message':'Analyse arretee apres 1 partie sur 3.', 'cancelled':True}}

    monkeypatch.setattr(analysis, 'analyze_document', partial_analysis)
    async def process():
        job = job_service.start_analysis_job(source['id'], fill_mode='prefilled')
        while job_service.get_job(job['id'])['status'] != 'running':
            await asyncio.sleep(0.01)
        requested = job_service.cancel_analysis_job(job['id'])
        assert requested['status'] == 'cancelling'
        await asyncio.gather(*list(job_service._tasks))
        return job_service.get_job(job['id'])
    job = asyncio.run(process())
    assert job['status'] == 'cancelled'
    assert job['result_card_ids'] == ['partial-card']
    assert not job['error']
    assert documents.get_document(source['id'])['content_text']
