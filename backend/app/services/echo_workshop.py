"""One projection of validated ECUME knowledge, not a second source of truth."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

from rdflib.namespace import OWL, SKOS, RDFS, XSD
from app.database.db import get_db, now_iso
from app.services import reference_service as references, echo_mapping_service as mappings, graph_service as graph
from app.services.business_rule_service import from_card


def layer(term):
    types=term.get('types',[])
    return 'voc' if str(SKOS.Concept) in types else 'owl'


def extraction_context(chunk: str) -> str:
    words=set(graph._normalize(chunk).split())
    output=[]
    for repository in references.list_repositories():
        if not repository['active']:
            continue
        with get_db() as conn:
            terms=[references.decode(row) for row in conn.execute('SELECT * FROM reference_terms WHERE repository_id=?',(repository['id'],))]
        scored=sorted(terms,key=lambda t:-len(set(graph._normalize(t['label']+' '+' '.join(t['aliases'])).split()) & words))
        selected=[t for t in scored if set(graph._normalize(t['label']+' '+' '.join(t['aliases'])).split()) & words][:12]
        echo=repository['profile'].get('echo',{})
        output.append({'repository':repository['name'],'terms':[{'uri':t['uri'],'label':t['label'],'aliases':t['aliases'][:6],'definition':t['definition'][:300],'layer':layer(t)} for t in selected],
            'expected_rules':[{'label':s['label'],'target_classes':s['target_classes'],'path':s['path'],'rules':s['rules']} for s in echo.get('shacl',{}).get('shapes',[]) if s['status']=='interpreted'][:12]})
        if len(json.dumps(output,ensure_ascii=False))>9000:
            output.pop(); break
    return json.dumps(output,ensure_ascii=False)


def synchronize(repository_id: str, node_ids=None):
    repository=references.require_repository(repository_id)
    if not repository['active']:
        return ['Referentiel inactif : aucune nouvelle reconnaissance.']
    try:
        if node_ids is None:
            mappings.propose(repository_id)
        else:
            for node_id in node_ids:
                mappings.propose(repository_id,node_id)
    except ValueError as exc:
        return [str(exc)]
    return []


def enrich(payload: dict, synchronize_candidates: bool = True) -> dict:
    repository=payload['target_reference']
    echo=repository['profile'].get('echo',{})
    warnings=[w['message'] for w in payload['warnings'] if w['code']=='echo_search_incomplete']
    if synchronize_candidates and echo:
        warnings=synchronize(repository['id'],[n['id'] for n in payload['concepts']] if len(payload['concepts'])<20 else None)
    nodes=payload['concepts']
    with get_db() as conn:
        terms=[references.decode(row) for row in conn.execute('SELECT * FROM reference_terms WHERE repository_id=?',(repository['id'],))]
    term_by_uri={t['uri']:t for t in terms}
    all_mappings=[{**m,'element_type':'concept','target_layer':layer(term_by_uri.get(m['target_uri'],{}))} for m in mappings.mappings(repository_id=repository['id']) if m['node_id'] in {n['id'] for n in nodes}]
    recognized=[]
    for node in nodes:
        node_matches=[m for m in all_mappings if m['node_id']==node['id']]
        names={graph._normalize(v) for v in [node['label'],*node.get('aliases',[])]}
        for kind in ('owl','voc'):
            # Uniqueness is checked against all terms, not just the top-five suggestions.
            exact=[t for t in terms if layer(t)==kind and (kind=='voc' or set(t['types']) & {str(OWL.Class),str(RDFS.Class)}) and names & {graph._normalize(v) for v in [t['label'],*t['aliases']]}]
            if len(exact)!=1 or warnings or not repository['active']:
                continue
            match=next((m for m in node_matches if m['target_uri']==exact[0]['uri']),None)
            if match and not match['stale'] and match['status'] not in {'rejected','to_review'} and (match['decision_origin']!='user' or match['status']=='validated'):
                recognized.append({**match,'recognition':'unambiguous_lexical_match','status':match['status'],
                    'message':'Terme existant reconnu ; aucune validation metier ou equivalence formelle deduite.'})
    recognized_ids={m['node_id'] for m in recognized}
    rules=[r for card in payload.get('_cards',[]) for r in from_card(card)]
    for rule in rules:
        for warning in rule.get('warnings',[]):
            payload['warnings'].append({'code':'rule_source_to_verify','entity_id':rule['id'],'message':warning})
    owl_classes=echo.get('owl',{}).get('classes',[])
    owl_by_uri={c['uri']:c for c in owl_classes}
    rule_mappings=[]
    for rule in rules:
        candidates=[c for c in owl_classes if c['uri']==rule.get('owl_class_uri')]
        if not candidates:
            names={graph._normalize(rule['label']),graph._normalize(rule.get('rule_type',''))}
            candidates=[c for c in owl_classes if graph._normalize(c['label']) in names]
        rule['owl_candidates']=[{'uri':c['uri'],'label':c['label'],'status':'candidate'} for c in candidates[:3]]
        for c in candidates[:3]:
            rule_mappings.append({'element_id':rule['id'],'element_type':'rule','target_layer':'owl','target_uri':c['uri'],'target_label':c['label'],'status':'candidate','reason':'Positionnement de la regle a confirmer.'})
    new_concepts=[]
    for node in nodes:
        candidates=[m for m in all_mappings if m['node_id']==node['id'] and m['status']!='rejected']
        if node['id'] not in recognized_ids:
            new_concepts.append({**node,'classification':'to_review' if candidates or warnings else 'new_concept',
                                 'nearby_echo':candidates,'novelty':'proposed_not_proven_absent'})
    checks=check(repository,nodes,rules,recognized,all_mappings,payload['proposed_relations'])
    for rule in rules:
        for term in terms:
            if layer(term)=='voc' and graph._normalize(rule['label']) in {graph._normalize(v) for v in [term['label'],*term['aliases']]}:
                rule_mappings.append({'element_id':rule['id'],'element_type':'rule','target_layer':'voc','target_uri':term['uri'],'target_label':term['label'],'status':'candidate','reason':'Terme de regle present dans le vocabulaire.'})
        for shape_uri in {c.get('shape_uri') for c in checks if c['element_id']==rule['id']} - {None}:
            rule_mappings.append({'element_id':rule['id'],'element_type':'rule','target_layer':'shacl','target_uri':shape_uri,'status':'candidate','reason':'Forme applicable au positionnement de travail de la regle.'})
    relation_mappings=[]
    for relation in payload['proposed_relations']:
        props=[p for p in echo.get('owl',{}).get('properties',[]) if graph._normalize(p['label'])==graph._normalize(relation['relation_type'])]
        for prop in props[:3]:
            relation_mappings.append({'element_id':relation['id'],'element_type':'relation','target_layer':'owl','target_uri':prop['uri'],'target_label':prop['label'],'status':'candidate','reason':'Libelle de relation identique ; domaine et portee a verifier.'})
    report=payload['control_report']
    report.update(files=echo.get('files',[]),profile_confidence=echo.get('confidence','insufficient'),
        owl_classes=len(owl_classes),owl_properties=len(echo.get('owl',{}).get('properties',[])),voc_terms=echo.get('voc',{}).get('term_count',0),
        shacl_shapes=len(echo.get('shacl',{}).get('shapes',[])),shacl_interpreted=echo.get('shacl',{}).get('interpreted',0),shacl_uninterpreted=echo.get('shacl',{}).get('uninterpreted',0),
        recognized_existing=len(recognized_ids),new_concepts=sum(n['classification']=='new_concept' for n in new_concepts),new_business_rules=len(rules),
        shacl_counts=dict(Counter(c['status'] for c in checks)),ready_for_automatic_import=False)
    payload.update(target_repository=repository,echo_profile=echo,owl_profile=echo.get('owl',{}),voc_profile=echo.get('voc',{}),shacl_profile=echo.get('shacl',{}),
        recognized_existing_echo_elements=recognized,ecume_concepts=nodes,ecume_rules=rules,
        proposed_new_concepts=new_concepts,proposed_voc_terms=[{'node_id':n['id'],'label':n['label'],'definition':n['description'],'aliases':n['aliases'],'status':'proposed','source_ids':n['source_ids']} for n in nodes if not any(m['node_id']==n['id'] and m['target_layer']=='voc' for m in recognized)],
        proposed_owl_alignments=[m for m in all_mappings if m['target_layer']=='owl' and m['status'] not in {'rejected','to_review'} and not m['stale']]+[m for m in rule_mappings if m['target_layer']=='owl']+relation_mappings,
        proposed_voc_alignments=[m for m in all_mappings if m['target_layer']=='voc' and m['status'] not in {'rejected','to_review'} and not m['stale']]+[m for m in rule_mappings if m['target_layer']=='voc'],
        proposed_shacl_alignments=[m for m in rule_mappings if m['target_layer']=='shacl'],shacl_checks=checks,
        review_items=[*payload['items_to_review'],*[c for c in checks if c['status']!='conformant']])
    for warning in [*warnings,*echo.get('warnings',[])]:
        payload['warnings'].append({'code':'echo_workshop','entity_id':repository['id'],'message':warning})
    payload['metadata']['version']='2.0'
    from app.services.review_service import workspace
    payload['recognized_document_mentions'] = [item for item in workspace()['items']
        if item['status']=='known' and any(t.get('repository_id')==repository['id'] for t in [item.get('target') or {}, *item.get('candidates',[])])]
    payload.pop('_cards',None)
    return payload


FIELD_NAMES={
    'label':{'label','preflabel','libelle','nom','name'},'description':{'definition','description','comment'},
    'unit':{'unit','unite'},'value':{'value','valeur'},'source':{'source','sources','provenance'},
    'condition':{'condition','conditions'},'exception':{'exception','exceptions'},
}


def check(repository,nodes,rules,recognized,all_mappings,relations=None):
    relations=relations or []
    echo=repository['profile'].get('echo',{})
    shapes=echo.get('shacl',{}).get('shapes',[])
    entities=[*nodes,*rules]
    if not shapes:
        return [{'element_id':e['id'],'status':'not_verifiable','message':'Aucune regle de controle fournie.'} for e in entities]
    if len(entities)*len(shapes)>10000:
        return [{'element_id':e['id'],'status':'not_verifiable','message':'Lot trop volumineux pour le controle synchrone du MVP.'} for e in entities]
    items=[]
    property_labels={p['uri']:p['label'] for p in echo.get('owl',{}).get('properties',[])}
    for entity in entities:
        owl_class_uris={c['uri'] for c in echo.get('owl',{}).get('classes',[])}
        classes=[m['target_uri'] for m in recognized if m['node_id']==entity['id'] and m['target_layer']=='owl' and m['target_uri'] in owl_class_uris]
        if any(m['node_id']==entity['id'] and m['target_layer']=='voc' for m in recognized):
            classes.append(str(SKOS.Concept))
        classes.extend(m['target_uri'] for m in all_mappings if m['node_id']==entity['id'] and m['status']=='validated' and not m['stale'] and m['target_uri'] in owl_class_uris)
        classes.extend(c['uri'] for c in entity.get('owl_candidates',[]))
        # New vocabulary proposals can be checked against the declared SKOS vocabulary shape.
        if not classes and entity in nodes and echo.get('voc',{}).get('term_count'):
            classes.append(str(SKOS.Concept))
        item={'id':entity['id'],'uri':'urn:ecume:'+('rule:' if entity in rules else 'node:')+entity['id'],'classes':list(set(classes)),'properties':{},'unknown_paths':[]}
        for shape in shapes:
            path=shape['path']
            if not path:
                continue
            name=graph._normalize(property_labels.get(path,path.rsplit('#',1)[-1].rsplit('/',1)[-1]))
            matching_relations=[r for r in relations if graph._normalize(r['relation_type'])==name]
            if matching_relations:
                item['properties'][path]=[{'value':'urn:ecume:node:'+r['target_node_id'],'kind':'uri'} for r in matching_relations if r['source_node_id']==entity['id']]
                continue
            field=next((key for key,names in FIELD_NAMES.items() if name in names),None)
            if field is None:
                item['unknown_paths'].append(path); continue
            values=entity.get(field)
            if field=='source':
                values=['urn:ecume:document:'+s for s in entity.get('source_ids',[]) or [entity.get('source_document_id','')] if s]
            if not isinstance(values,list):
                values=[values] if values not in ('',None) else []
            expected=next((r['expected']['value'] for r in shape['rules'] if r['constraint']=='datatype'),None)
            converted=[]
            for v in values:
                datatype=''
                text=str(v)
                if field=='value' and expected in {str(XSD.decimal),str(XSD.integer),str(XSD.double),str(XSD.float)}:
                    try:
                        float(text.replace(',','.')); datatype=expected; text=text.replace(',','.')
                    except ValueError:
                        pass
                converted.append({'value':text,'kind':'uri' if field=='source' else 'literal','datatype':datatype})
            item['properties'][path]=converted
        items.append(item)
    fingerprint=hashlib.sha256(json.dumps({'projection_version':2,'items':items,'shapes':shapes},sort_keys=True).encode()).hexdigest()
    with get_db() as conn:
        cached=conn.execute('SELECT report FROM echo_validation_reports WHERE repository_id=? AND fingerprint=? ORDER BY created_at DESC LIMIT 1',(repository['id'],fingerprint)).fetchone()
        if cached:
            previous=json.loads(cached[0])
            if not any(c.get('retryable') for c in previous):
                return previous
    try:
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('echo_shacl_worker.py'))],input=json.dumps({'items':items,'shapes':shapes}),
                              capture_output=True,text=True,encoding='utf-8',timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        checks=json.loads(result.stdout)
        if result.returncode or not isinstance(checks,list):
            raise ValueError('Le moteur de controle ne peut pas interpreter ce lot.')
    except (subprocess.TimeoutExpired,ValueError,OSError):
        checks=[{'element_id':e['id'],'status':'not_verifiable','retryable':True,'message':'Controle interrompu ou non interpretable ; aucune conformite presumee.'} for e in entities]
    for c in checks:
        c['projection']='Projection de travail candidate, pas validation juridique ni garantie de reimport.'
    with get_db() as conn:
        conn.execute('INSERT INTO echo_validation_reports VALUES (?,?,?,?,?)',(str(uuid.uuid4()),repository['id'],now_iso(),fingerprint,json.dumps(checks)))
        conn.execute('DELETE FROM echo_validation_reports WHERE repository_id=? AND id NOT IN (SELECT id FROM echo_validation_reports WHERE repository_id=? ORDER BY created_at DESC LIMIT 5)',(repository['id'],repository['id']))
    return checks
