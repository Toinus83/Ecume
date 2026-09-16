import copy
import json
import re
import uuid

from app.database.db import atomic, get_db


def extract(raw: dict) -> list[dict]:
    from app.services.salience_service import score, strings
    inputs = raw.get('business_rules',[])
    if not isinstance(inputs,list):
        inputs=[]
    if not inputs:
        inputs = [{'label':text[:100],'description':text,'source_excerpt':raw.get('source_excerpt','')} for text in strings(raw.get('rule_details'))]
    rules=[]
    for item in inputs[:12]:
        if not isinstance(item,dict) or not (item.get('label') or item.get('description')):
            continue
        rule={key:str(item.get(key) or '')[:1200] for key in ('label','description','rule_type','unit','condition','exception','source_excerpt','reason','owl_class_uri')}
        rule['source_excerpt'] = rule['source_excerpt'] or str(raw.get('source_excerpt') or '')[:1200]
        value=item.get('value')
        rule['value']=str(value)[:80] if value is not None and isinstance(value,(str,float,int)) and not isinstance(value,bool) else ''
        if not rule['value']:
            match=re.search(r'\b(\d+(?:[.,]\d+)?)\s*(m[eè]tres?|m|cm|mm|km|%)(?!\w)',rule['description'],re.I)
            if match:
                rule['value'],rule['unit']=match.groups()
        rule.update(id=str(uuid.uuid4()),origin='llm',confidence=score(item.get('confidence')),salience_score=score(item.get('salience_score')),
                    concerned_labels=strings(item.get('concerned_labels')),source_document_id='',status='proposed')
        rules.append(rule)
    return rules


def from_card(card: dict) -> list[dict]:
    return [{**rule,'card_id':card['id'],'source_document_id':rule.get('source_document_id') or card['document_id'],
             'source_excerpt':rule.get('source_excerpt') or card.get('source_excerpt',''),
             'status':card['status'],'business_validation_status':card['business_validation_status'],
             'concept_ids':[node for values in card['graph_node_ids'].values() for node in (values if isinstance(values,list) else [values]) if node]}
            for rule in (card.get('extraction_details') or {}).get('business_rules',[])]


def verify_sources(rules: list[dict], document: dict) -> list[str]:
    normalize=lambda text:' '.join(str(text).casefold().split())
    content=normalize(document.get('content_text',''))
    warnings=[]
    for rule in rules:
        excerpt=normalize(rule.get('source_excerpt',''))
        issues=[]
        if not excerpt or excerpt not in content:
            issues.append('Extrait de regle non retrouve dans le texte source.')
        if rule.get('value') and not re.search(r'(?<!\d)'+re.escape(normalize(rule['value']))+r'(?!\d)',excerpt):
            issues.append('Valeur de regle non retrouvee dans son extrait.')
        rule['source_verified']=not issues
        rule['warnings']=issues
        rule['source_document_id']=document['id']
        warnings.extend(issues)
    return sorted(set(warnings))


@atomic
def update(card_id: str, rule_id: str, changes: dict):
    from app.services.card_service import require_card, update_card
    from app.models.schemas import CardUpdate
    from app.services.changelog_service import record_change
    card=require_card(card_id)
    details=copy.deepcopy(card.get('extraction_details') or {})
    rule=next((r for r in details.get('business_rules',[]) if r['id']==rule_id),None)
    if rule is None:
        raise ValueError('Regle introuvable.')
    before=copy.deepcopy(rule)
    for key in ('label','description','value','unit','condition','exception'):
        if key in changes:
            rule[key]=str(changes[key] or '')[:1200]
    if not rule['label'].strip():
        raise ValueError('Le libelle est obligatoire.')
    rule['origin']='user'
    from app.services.document_service import get_document
    document=get_document(rule.get('source_document_id') or card['document_id'])
    if document and document.get('content_text'):
        verify_sources([rule],document)
    else:
        rule['source_verified']=False
        rule['warnings']=['Source purgee ou absente : verifier la correction avec l extrait conserve.']
    with get_db() as conn:
        conn.execute('UPDATE extracted_cards SET extraction_details=? WHERE id=?',(json.dumps(details),card_id))
    result=update_card(card_id,CardUpdate(status='to_confirm'))
    record_change(entity_type='business_rule',entity_id=rule_id,action='corrected',origin='user',details={'before':before,'after':rule,'card_id':card_id})
    return result
