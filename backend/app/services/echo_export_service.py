from __future__ import annotations

from collections import Counter
import csv
import io
import json
import uuid
import zipfile

from app.database.db import atomic, get_db, now_iso
from app.services import export_service as exports, reference_service as references, echo_mapping_service as echo
from app.services import graph_service

MATCH_DESCRIPTIONS = {
    'exactMatch':'ECUME et Echo : meme sens, a confirmer si candidat.',
    'closeMatch':'Sens proches, sans affirmer une equivalence stricte.',
    'broadMatch':'Le terme Echo cible est plus general que le concept ECUME source.',
    'narrowMatch':'Le terme Echo cible est plus precis que le concept ECUME source.',
    'relatedMatch':'Concepts lies, sans equivalence ni hierarchie affirmee.',
}


@atomic
def build_package(repository_id: str, card_id: str = '') -> dict:
    repository = references.require_repository(repository_id)
    snapshot = exports._complete_export_payload('validated')
    if card_id:
        snapshot['cards']=[card for card in snapshot['cards'] if card['id']==card_id]
        ids={node_id for card in snapshot['cards'] for values in card['graph_node_ids'].values() for node_id in (values if isinstance(values,list) else [values]) if node_id}
        snapshot['nodes']=[node for node in snapshot['nodes'] if node['id'] in ids]
    nodes = {node['id']:node for node in snapshot['nodes']}
    warnings = [{'code':'reference_profile','entity_id':repository_id,'message':message} for message in repository['profile']['warnings']]
    if not repository['active']:
        warnings.append({'code':'inactive_reference','entity_id':repository_id,'message':'Reference inactive pour les nouvelles recherches ; cible choisie explicitement pour ce rapport.'})
    local_importance = {}
    evidence_cards = []
    for card in snapshot['cards']:
        details = card.get('extraction_details') or {}
        main_id = card['graph_node_ids'].get('effect')
        if main_id:
            local_importance.setdefault(main_id,[]).append({'card_id':card['id'],'document_id':card['document_id'],
                'importance':'principal' if details.get('managed') else 'legacy_unclassified', 'salience_score':None,
                'confidence':card.get('business_confidence'), 'reason':card.get('business_justification',''), 'retained':True})
        if details.get('managed'):
            for item in details.get('concepts',[]):
                if item.get('active') and item.get('node_id') and (item['importance']=='principal' or item['importance']=='secondary' and item.get('retained')):
                    local_importance.setdefault(item['node_id'],[]).append({**{key:item.get(key) for key in ('importance','salience_score','confidence','reason','retained')},
                        'card_id':card['id'],'document_id':card['document_id']})
        else:
            for role in ('objects','actions','conditions','tasks','theme'):
                ids = card['graph_node_ids'].get(role,[])
                for node_id in ids if isinstance(ids,list) else [ids]:
                    if node_id:
                        local_importance.setdefault(node_id,[]).append({'card_id':card['id'],'document_id':card['document_id'],
                            'importance':'legacy_unclassified','salience_score':None,'confidence':None,'reason':'Connaissance historique validee, non reclassee.','retained':True})
        evidence_cards.append({'id':card['id'],'document_id':card['document_id'],'main_effect':card['main_effect'],
            'business_validation_status':card['business_validation_status'],'business_confidence':card.get('business_confidence'),
            'source_excerpt':card.get('source_excerpt','')[:1200], 'rule_details':details.get('rule_details',[]),
            'source_checks':details.get('source_checks',[]),'source_excerpts':details.get('source_excerpts',[]),
            'validation_decision':card.get('validation_decision',{})})
    # Defensive filter for managed-only nodes; legacy and explicit standalone decisions stay compatible.
    with get_db() as conn:
        bound_ids = {row[0] for row in conn.execute('SELECT DISTINCT node_id FROM card_concepts')}
    excluded_weak = {node_id for node_id,node in nodes.items() if node_id in bound_ids and node_id not in local_importance
                     and node.get('metadata',{}).get('standalone_status') not in {'accepted','accepted_orphan'}
                     and node.get('orphan_status')!='accepted_orphan'}
    nodes = {node_id:node for node_id,node in nodes.items() if node_id not in excluded_weak}
    if repository['profile'].get('echo'):
        from app.services.echo_workshop import synchronize
        for warning in synchronize(repository_id,list(nodes) if len(nodes)<20 else None):
            warnings.append({'code':'echo_search_incomplete','entity_id':repository_id,'message':warning})
    all_mappings = [item for item in echo.mappings(repository_id=repository_id) if item['node_id'] in nodes]
    primary_mappings = []
    review = []
    rejected_mappings = 0
    for item in all_mappings:
        if item['status']=='rejected':
            rejected_mappings += 1
            continue
        item = {**item, 'direction':'ECUME -> Echo', 'meaning':MATCH_DESCRIPTIONS[item['match_type']],
                'effective_status':'to_review' if item['stale'] else item['status']}
        if item['effective_status']=='to_review':
            review.append(item)
        else:
            primary_mappings.append(item)
    by_node = {}
    for item in primary_mappings:
        by_node.setdefault(item['node_id'],[]).append(item)
    concepts, enrichments = [], []
    for node_id,node in nodes.items():
        matches = by_node.get(node_id,[])
        validated = [item for item in matches if item['status']=='validated']
        exact = [item for item in validated if item['match_type']=='exactMatch']
        classification = 'enrichment' if exact else 'alignment' if validated else 'possible_duplicate' if any(item['match_type'] in {'exactMatch','closeMatch'} for item in matches) else 'to_review' if any(item['node_id']==node_id for item in review) else 'new_concept'
        concept = {key:node.get(key) for key in ('id','uri','label','canonical_label','type','description','business_category','level',
                    'status','business_validation_status','business_confidence','confidence','source_ids','source_titles','created_at','updated_at')}
        concept.update(aliases=[item['label'] for item in node.get('aliases',[])], source_excerpt=node.get('source_excerpt','')[:1200],
            classification=classification, proposal_status='proposed_for_reference_review',
            salience_by_card=local_importance.get(node_id,[]), without_validated_mapping=not validated,
            archimate_candidate=node.get('archimate_mapping',{}), echo_mapping_ids=[item['id'] for item in matches])
        concepts.append(concept)
        if not node.get('description'):
            warnings.append({'code':'missing_definition','entity_id':node_id,'message':'Definition du concept ECUME absente.'})
        for mapping in exact:
            existing_labels = {graph_service._normalize(value) for value in [mapping['target_label'],*mapping['target_aliases']]}
            proposed_aliases = list(dict.fromkeys(value for value in [node['label'],*concept['aliases']] if graph_service._normalize(value) not in existing_labels))
            definition = node.get('description','')
            if graph_service._normalize(definition)==graph_service._normalize(mapping['target_definition']):
                definition = ''
            if proposed_aliases or definition:
                enrichments.append({'node_id':node_id,'node_label':node['label'],'mapping_id':mapping['id'],
                    'target_uri':mapping['target_uri'],'target_label':mapping['target_label'],'existing_definition':mapping['target_definition'],
                    'proposed_alt_labels':proposed_aliases,'proposed_definition':definition,
                    'strategy':'additional_information_never_automatic_replacement','status':'proposed_for_reference_review',
                    'business_validation_status':node['business_validation_status'],'mapping_status':'validated',
                    'source_ids':node['source_ids'],'source_titles':node['source_titles'],'source_excerpt':concept['source_excerpt']})
    relations = [{**{key:edge.get(key) for key in ('id','source_node_id','source_label','target_node_id','target_label','relation_type','description',
                 'direction','status','business_validation_status','confidence','source_ids','source_titles','created_at','updated_at')},
                 'source_excerpt':edge.get('metadata',{}).get('source_excerpt','')[:1200],
                 'proposal_status':'proposed_for_reference_review','reference_property':None}
                 for edge in snapshot['edges'] if edge['source_node_id'] in nodes and edge['target_node_id'] in nodes]
    if relations:
        warnings.append({'code':'relation_semantics','entity_id':repository_id,'message':'Les relations ECUME ne sont pas automatiquement traduites en proprietes Echo. Correspondance a controler avant reimport.'})
    if review:
        warnings.append({'code':'mappings_to_review','entity_id':repository_id,'message':f'{len(review)} correspondance(s) a revoir, exclues des enrichissements automatiques.'})
    source_ids = {source_id for node in concepts for source_id in node['source_ids']}
    source_ids.update(source_id for edge in relations for source_id in edge['source_ids'])
    source_ids.update(card['document_id'] for card in evidence_cards)
    source_ids.update(rule.get('source_document_id') or card['document_id'] for card in snapshot['cards'] for rule in (card.get('extraction_details') or {}).get('business_rules',[]))
    for card in evidence_cards:
        source_ids.update(check.get('document_id') for check in card['source_checks'] if check.get('document_id'))
    sources = [{key:doc.get(key) for key in ('id','uri','title','filename','file_type','created_at','content_hash','source_status')}
               for doc in snapshot['documents'] if doc['id'] in source_ids]
    for source_id in sorted(source_ids - {source['id'] for source in sources}):
        warnings.append({'code':'missing_source','entity_id':source_id,'message':'Fiche documentaire absente ; identifiant source conserve pour controle.'})
    counts = Counter(item['classification'] for item in concepts)
    mapping_counts = Counter(item['match_type']+':'+item['status'] for item in primary_mappings)
    rejected_nodes = sum(node['status']=='rejected' or node.get('business_validation_status')=='rejected' for node in graph_service.list_nodes())
    report = {'reference_id':repository_id,'reference_name':repository['name'],'profile_status':repository['profile']['status'],
        'concepts':len(concepts),'new_concepts':counts['new_concept'],'enrichments':len(enrichments),'proposed_relations':len(relations),
        'mappings_by_type_and_status':dict(mapping_counts),'validated_without_mapping':sum(item['without_validated_mapping'] for item in concepts),
        'mappings_to_review':len(review),'possible_duplicates':counts['possible_duplicate'], 'rejected_nodes_excluded':rejected_nodes,
        'rejected_mappings_excluded':rejected_mappings,'weak_nodes_excluded':len(excluded_weak),'warnings':warnings,
        'ready_for_automatic_import':False}
    payload = {'metadata':{'format':'ECUME Echo enrichment package','version':'1.0','generated_at':now_iso(),
                        'scope':'validated_business_knowledge','authoritative':False,'source_reference_modified':False,
                        'instruction':'Propositions a controler par un expert avant reimport externe. Aucun changement a appliquer automatiquement.'},
        'target_reference':repository, 'detected_profile':repository['profile'],
        'export_conventions':{'namespace':repository['namespace'],'label_properties':repository['profile']['label_properties'],
            'alias_properties':repository['profile']['alias_properties'],'definition_properties':repository['profile']['definition_properties'],
            'new_concept_uris':'Stable ECUME URNs; no URI minted in the reference namespace.',
            'relation_semantics':exports.RELATION_DESCRIPTIONS,'mapping_semantics':MATCH_DESCRIPTIONS},
        'concepts':concepts,'mappings':primary_mappings,'proposed_enrichments':enrichments,'proposed_relations':relations,
        'sources':sources,'evidence_cards':evidence_cards,'items_to_review':review,'warnings':warnings,'control_report':report}
    from app.services.echo_workshop import enrich
    payload['_cards']=snapshot['cards']
    return enrich(payload, synchronize_candidates=False)


def export_json(repository_id: str):
    payload = build_package(repository_id)
    exports.EXPORT_DIR.mkdir(parents=True,exist_ok=True)
    path = exports.EXPORT_DIR / f'echo_enrichment_{uuid.uuid4()}.json'
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return path


def _csv(rows: list[dict], fields: list[str]) -> str:
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output,fieldnames=fields,extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        values = {}
        for key in fields:
            value = row.get(key,'')
            if isinstance(value,(dict,list)):
                value = json.dumps(value,ensure_ascii=False)
            text = '' if value is None else str(value)
            # Spreadsheet review files must never turn imported text into formulas.
            values[key] = "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text
        writer.writerow(values)
    return output.getvalue()


def export_csv(repository_id: str):
    payload = build_package(repository_id)
    exports.EXPORT_DIR.mkdir(parents=True,exist_ok=True)
    path = exports.EXPORT_DIR / f'echo_review_{uuid.uuid4()}.zip'
    files = {
        'echo_new_concepts.csv':([item for item in payload['concepts'] if item['classification']!='enrichment'],
            ['id','uri','label','aliases','type','business_category','level','description','classification','proposal_status','business_validation_status','business_confidence','confidence','salience_by_card','source_ids','source_titles','source_excerpt','archimate_candidate']),
        'echo_enrichments.csv':(payload['proposed_enrichments'],['node_id','node_label','target_uri','target_label','existing_definition','proposed_alt_labels','proposed_definition','strategy','status','business_validation_status','mapping_status','source_ids','source_titles','source_excerpt']),
        'echo_mappings.csv':([*payload['mappings'],*payload['items_to_review']],['id','node_id','node_label','repository_name','target_uri','target_label','target_definition','match_type','meaning','direction','score','reason','status','effective_status','stale','decision_origin']),
        'echo_relations.csv':(payload['proposed_relations'],['id','source_node_id','source_label','target_node_id','target_label','relation_type','direction','description','status','proposal_status','confidence','source_ids','source_titles','source_excerpt']),
        'echo_warnings.csv':(payload['warnings'],['code','entity_id','message']),
    }
    files.update({
        'echo_recognized_existing.csv':(payload['recognized_existing_echo_elements'],['node_id','node_label','target_layer','target_uri','target_label','recognition','status','reason']),
        'echo_new_voc_terms.csv':(payload['proposed_voc_terms'],['node_id','label','definition','aliases','status','source_ids']),
        'echo_rules.csv':(payload['ecume_rules'],['id','label','description','rule_type','value','unit','condition','exception','source_document_id','source_excerpt','status','reason','confidence','salience_score','owl_candidates']),
        'echo_shacl_report.csv':(payload['shacl_checks'],['element_id','shape_uri','shape_label','path','status','severity','message','projection']),
    })
    files['echo_new_concepts.csv']=(payload['proposed_new_concepts'],files['echo_new_concepts.csv'][1])
    files['echo_mappings.csv']=([*payload['proposed_owl_alignments'],*payload['proposed_voc_alignments'],*payload['proposed_shacl_alignments']],['id','element_id','element_type','node_id','node_label','target_layer','target_uri','target_label','match_type','score','reason','status','stale'])
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
        for name,(rows,fields) in files.items():
            bundle.writestr(name,_csv(rows,fields).encode('utf-8-sig'))
        bundle.writestr('echo_enrichment.json',json.dumps(payload,ensure_ascii=False,indent=2))
        bundle.writestr('echo_control_report.json',json.dumps(payload['control_report'],ensure_ascii=False,indent=2))
        bundle.writestr('README.txt','Lot de controle humain Echo. Ne pas importer automatiquement.\nLe JSON est la version complete et fait autorite sur les CSV de revue.\nLes correspondances se lisent du concept ECUME source vers le terme Echo cible.\nLes definitions proposees ne remplacent jamais automatiquement celles de la reference.\nLes cellules CSV pouvant etre des formules sont protegees par une apostrophe.\n')
    return path
