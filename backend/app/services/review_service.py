"""Document mentions are proposals, not graph nodes. Only a decision materializes them."""
from __future__ import annotations

import json
import re
import uuid
from difflib import SequenceMatcher

from app.database.db import atomic, get_db, now_iso, transaction
from app.services import graph_service as graph, coherence_service as coherence
from app.services.changelog_service import record_change
from app.services.serialization import row_to_dict

QUESTIONS = {
    "motivation": "Pourquoi c'est important ?", "objects": "De quoi parle-t-on ?",
    "actors": "Qui est concerne ?", "actions": "Que fait-on ?", "means": "Avec quels moyens ?",
    "information": "Quelles informations sont utilisees ?", "rules": "Quelles regles ou conditions ?",
    "result": "Quel resultat est attendu ?",
}
DIAGNOSTICS = {graph._normalize(s) for s in ("Passages du document a verifier", "Passage du document a verifier",
    "Texte a controler", "Element incertain", "Analyse partielle", "Aucune extraction", "Effet a qualifier")}

QUALIFICATION_GUIDES = {
    'resultat_recherche': ("Un résultat attendu", "Un état ou un effet que l'on cherche à obtenir."),
    'objectif_haut_niveau': ("Un objectif", "Une orientation ou une finalité générale."),
    'capacite_a_obtenir': ("Une capacité", "Ce que l'organisation doit être capable de faire."),
    'action_activite': ("Une activité", "Quelque chose qui est réalisé pour produire un résultat."),
    'chose_metier': ("Une notion métier", "Un élément dont le métier parle ou sur lequel il agit."),
    'donnee_manipulee': ("Une information traitée", "Une donnée structurée utilisée ou produite par une application."),
    'condition_regle_contrainte': ("Une règle ou contrainte", "Une condition, une limite ou une exigence à respecter."),
    'acteur_organisation': ("Un acteur ou une organisation", "Une personne, une unité ou un organisme qui agit."),
    'role_tenu': ("Un rôle", "Une responsabilité assumée dans un contexte."),
    'service_rendu': ("Un service métier", "Un comportement fourni au métier ou à un utilisateur."),
    'service_applicatif': ("Un service applicatif", "Un comportement fourni par une application."),
    'application_outil': ("Une application ou un outil numérique", "Un logiciel identifiable utilisé pour travailler."),
    'lieu_environnement_physique': ("Un lieu ou environnement physique", "Un bâtiment, une zone ou un espace physique."),
    'ressource_metier': ("Une ressource", "Un moyen ou un actif mobilisé par l'organisation."),
    'element_technique': ("Un élément technique", "Un équipement ou une infrastructure informatique."),
}


def qualification_choices(label, description=''):
    """Offer a few business meanings; never ask the user to know ArchiMate."""
    from app.semantic.archimate_mapping import infer_archimate_mapping
    text = graph._normalize(f"{label} {description}")
    ranked = []
    rules = [
        (('espace','zone','site','terrain','batiment','local','lieu','installation'),
         ['lieu_environnement_physique','chose_metier','ressource_metier']),
        (('application','logiciel','plateforme','outil numerique'),
         ['application_outil','service_applicatif','ressource_metier']),
        (('serveur','reseau','infrastructure','equipement informatique','terminal'),
         ['element_technique','ressource_metier','application_outil']),
        (('acteur','organisation','organisme','equipe','unite','operateur','autorite'),
         ['acteur_organisation','role_tenu','ressource_metier']),
        (('role','responsable','responsabilite','fonction tenue'),
         ['role_tenu','acteur_organisation','capacite_a_obtenir']),
        (('regle','condition','contrainte','seuil','distance','exigence','obligation','interdit'),
         ['condition_regle_contrainte','chose_metier','objectif_haut_niveau']),
        (('donnee','information','message','rapport','position','identifiant'),
         ['donnee_manipulee','chose_metier','resultat_recherche']),
        (('capacite','aptitude','savoir faire'),
         ['capacite_a_obtenir','ressource_metier','service_rendu']),
        (('objectif','finalite','ambition'),
         ['objectif_haut_niveau','resultat_recherche','capacite_a_obtenir']),
        (('resultat','effet','issue attendue'),
         ['resultat_recherche','objectif_haut_niveau','capacite_a_obtenir']),
        (('service','prestation'),
         ['service_rendu','service_applicatif','capacite_a_obtenir']),
        (('action','activite','processus','procedure','detection','classification','analyse','validation'),
         ['action_activite','capacite_a_obtenir','resultat_recherche']),
    ]
    for words, categories in rules:
        if any(word in text for word in words):
            ranked.extend(categories)
    ranked.extend(['chose_metier','ressource_metier','resultat_recherche'])
    selected = list(dict.fromkeys(ranked))[:3]
    result = []
    for position, category in enumerate(selected):
        mapping = infer_archimate_mapping(business_category=category, concept_label=label,
            status='candidate', reason="Traduction candidate du sens métier proposé à l'utilisateur.")
        title, explanation = QUALIFICATION_GUIDES[category]
        result.append({'category':category, 'label':title, 'explanation':explanation,
                       'recommended':position == 0, 'mapping':mapping})
    return result


def diagnostic(label):
    return graph._normalize(str(label)).strip(' .:;!?') in DIAGNOSTICS


def migrate():
    with get_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS review_runs (
            id TEXT PRIMARY KEY, document_id TEXT NOT NULL, report TEXT NOT NULL, created_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS review_mentions (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, document_id TEXT NOT NULL, payload TEXT NOT NULL,
            status TEXT NOT NULL, node_id TEXT NOT NULL DEFAULT '', card_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_review_document ON review_mentions(document_id)")


def index():
    with get_db() as conn:
        nodes = [row_to_dict(r) for r in conn.execute("SELECT * FROM knowledge_nodes")]
        aliases = {}
        for row in conn.execute("SELECT node_id,label FROM knowledge_node_aliases"):
            aliases.setdefault(row['node_id'], []).append(row['label'])
        terms = [dict(r) for r in conn.execute("""SELECT t.*,r.name AS repository_name FROM reference_terms t
            JOIN reference_repositories r ON r.id=t.repository_id WHERE r.active=1""")]
    result = []
    for n in nodes:
        if coherence.is_valid(n) and not diagnostic(n['label']):
            result.append({'id': n['id'], 'label': n['label'], 'kind': 'ecume',
                           'aliases': aliases.get(n['id'], []), 'description': n['description'],
                           'source': 'graphe ECUME'})
    for t in terms:
        types = json.loads(t.get('types', '[]'))
        if not any(v.endswith(('#Concept', '#Class')) for v in types):
            continue
        result.append({'id': t['id'], 'label': t['label'], 'kind': 'echo', 'aliases': json.loads(t['aliases']),
                       'layer':'voc' if any(v.endswith('#Concept') for v in types) else 'owl',
                       'uri': t['uri'], 'repository_id': t['repository_id'], 'repository_name':t['repository_name'],
                       'description': t['definition'], 'source':f"référentiel {t['repository_name']}"})
    return result


def classify(label, entries):
    needle = graph._normalize(label)
    exact = [e for e in entries if needle in [graph._normalize(s) for s in [e['label'], *e['aliases']]]]
    local = [e for e in exact if e['kind'] == 'ecume']
    voc = [e for e in exact if e.get('layer') == 'voc']
    preferred = local or voc or exact
    if len(preferred) == 1:
        return 'known', preferred[0], exact
    if preferred:
        return 'review', None, preferred[:8]
    close = [(max(SequenceMatcher(None, needle, graph._normalize(s)).ratio() for s in [e['label'], *e['aliases']]), e)
             for e in entries]
    candidates = [dict(e, score=round(score, 3),
        reason='Libellé ou variante lexicale proche.', source=e.get('source') or ('graphe ECUME' if e['kind']=='ecume' else 'référentiel Echo'))
        for score, e in sorted(close, key=lambda pair: (-pair[0], pair[1]['label'])) if score >= .5][:8]
    return ('review' if candidates and candidates[0]['score'] >= .7 else 'new'), None, candidates


def locate(text, phrase):
    # Exact text with whitespace tolerance; never invent evidence for a paraphrase.
    if not phrase or len(phrase.strip()) < 2:
        return ''
    pattern = r'(?<!\w)' + r'\s+'.join(re.escape(part) for part in phrase.strip().split()) + r'(?!\w)'
    match = re.search(pattern, text, re.IGNORECASE)
    return text[max(0, match.start()-100):min(len(text), match.end()+180)] if match else ''


def sourced_fields(raw, text, fill_mode):
    result, issues = {}, []
    for key in QUESTIONS:
        result[key] = []
        if fill_mode == 'manual':
            continue
        values = raw.get('fields', {}).get(key, []) if isinstance(raw.get('fields'), dict) else []
        if isinstance(values, str):
            values = [{'text': values}]
        for item in values[:12] if isinstance(values, list) else []:
            if not isinstance(item, dict):
                continue
            value = str(item.get('text', '')).strip()[:500]
            excerpt = str(item.get('source_excerpt', '')).strip()[:1200]
            if value and excerpt and graph._normalize(excerpt) in graph._normalize(text) and locate(excerpt, value):
                result[key].append({'text': value, 'source_excerpt': excerpt, 'origin': 'document'})
            elif value:
                issues.append(f"Champ non source laisse vide : {QUESTIONS[key]}")
    return result, issues


async def analyze(document, provider, chunks, *, fill_mode, progress_callback=None, cancel_check=None):
    from app.services.echo_workshop import extraction_context
    entries, incoming, issues, chunk_reports = index(), [], [], []
    processed_chunks, cancelled = [], False
    provider.fill_mode = fill_mode
    for i, chunk in enumerate(chunks, 1):
        if cancel_check and cancel_check():
            cancelled = True
            break
        if progress_callback:
            progress_callback({'step':'llm_analysis', 'message':f'Lecture de la partie {i}/{len(chunks)}',
                'progress':10+int((i-1)/len(chunks)*70), 'current_chunk':i, 'total_chunks':len(chunks)})
        provider.echo_context = extraction_context(chunk)
        try:
            response = await provider.analyze_document(title=document['title'], content_text=chunk,
                existing_nodes=graph.existing_nodes_for_prompt())
            if not isinstance(response, dict):
                raise ValueError('La reponse du modele n est pas un objet JSON.')
            values = response.get('concepts', response.get('cards'))
            if not isinstance(values, list):
                raise ValueError('Reponse inexploitable : liste de concepts absente.')
            warnings = response.get('warnings', [])
            if isinstance(warnings, list):
                issues.extend({'message':str(w)[:1500], 'part':i} for w in warnings if w)
            chunk_reports.append({'part':i, 'returned':len(values), 'error':''})
            for raw in values:
                if not isinstance(raw, dict):
                    issues.append({'message':'Proposition illisible dans la reponse du modele.', 'part':i})
                    continue
                main = raw.get('main_effect') or {}
                label = str(raw.get('label') or (main.get('label') if isinstance(main, dict) else main) or '').strip()[:240]
                if not label or diagnostic(label):
                    issues.append({'message':'Message de controle ecarte : ce n est pas un concept metier.', 'part':i,
                                   'source_excerpt':str(raw.get('source_excerpt', ''))[:1200]})
                    continue
                excerpt = str(raw.get('source_excerpt', '')).strip()[:1200]
                evidence = bool(excerpt and graph._normalize(excerpt) in graph._normalize(chunk))
                if not evidence:
                    excerpt = locate(chunk, label)
                    evidence = bool(excerpt)
                fields, problems = sourced_fields(raw, chunk, fill_mode)
                from app.services.business_rule_service import extract, verify_sources
                rules = extract(raw) if fill_mode != 'manual' else []
                problems.extend(verify_sources(rules, {**document, 'content_text':chunk}))
                for rule in rules:
                    for key in ('unit','condition','exception'):
                        if rule.get(key) and graph._normalize(rule[key]) not in graph._normalize(rule['source_excerpt']):
                            rule['source_verified'] = False
                            problems.append('Regle incomplete ou non sourcee : verifier les unites, conditions et exceptions.')
                rules = [r for r in rules if r.get('source_verified')]
                for field_values in fields.values():
                    for field in field_values:
                        field_status, field_target, field_candidates = classify(field['text'], entries)
                        field.update(status=field_status, target=field_target, candidates=field_candidates)
                status, target, candidates = classify(label, entries)
                if not evidence:
                    status, target = 'review', None
                    problems.append('Extrait justificatif absent : verifier le document avant de valider.')
                if problems and status == 'new':
                    status = 'review'
                incoming.append({'label':label, 'description':str(raw.get('description') or (main.get('description', '') if isinstance(main, dict) else ''))[:6000],
                    'source_excerpt':excerpt, 'fields':fields, 'issues':problems, 'target':target, 'candidates':candidates,
                    'category':raw.get('business_category', 'non_qualifie'), 'status':status,
                    'origin':'llm', 'business_rules':rules if evidence else []})
            if not values:
                issues.append({'message':'Le modele n a propose aucun concept pour cette partie.', 'part':i})
        except Exception as exc:
            chunk_reports.append({'part':i, 'returned':0, 'error':str(exc)[:1500]})
            issues.append({'message':'Cette partie n a pas pu etre analysee.', 'part':i, 'detail':str(exc)[:1500]})
        from app.services.salience_service import preserve_source_checks
        # Use the existing span guard only as a report, never as a graph proposal.
        checks = preserve_source_checks([{'main_effect':{'description':''}}], chunk, i, document['id'])
        evidence = graph._normalize(' '.join(x['source_excerpt']+' '+x['description'] for x in incoming))
        for check in checks[0].get('source_checks',[]):
            if graph._normalize(check['text']) not in evidence:
                issues.append({'message':'Valeur ou exception a verifier dans le document.', 'source_excerpt':check['text'], 'part':i})
        processed_chunks.append(chunk)
        if cancel_check and cancel_check():
            cancelled = True
            break
    # Find existing names independently of the LLM, including when it returns an empty list.
    analyzed_text = '\n\n'.join(processed_chunks)
    for entry in entries:
        for alias in [entry['label'], *entry['aliases']]:
            excerpt = locate(analyzed_text, alias)
            if excerpt:
                status, target, candidates = classify(alias, entries)
                incoming.append({'label':alias, 'description':'', 'source_excerpt':excerpt,
                    'fields':{}, 'issues':[], 'target':target, 'candidates':candidates, 'category':'non_qualifie',
                    'status':status, 'origin':'lexical', 'business_rules':[]})
                break
    unique = {}
    for item in incoming:
        key = (graph._normalize(item['label']), (item.get('target') or {}).get('id', ''))
        if key in unique:
            previous = unique[key]
            for field, values in item['fields'].items():
                previous['fields'].setdefault(field, [])
                previous['fields'][field] = list({v['text']:v for v in [*previous['fields'][field], *values]}.values())
            previous['issues'] = list(dict.fromkeys([*previous['issues'], *item['issues']]))
            previous['business_rules'].extend(item['business_rules'])
        else:
            unique[key] = item
    report = {'text_read':bool(analyzed_text.strip()), 'text_characters':len(analyzed_text),
        'chunks':chunk_reports, 'issues':issues, 'fill_mode':fill_mode,
        'cancelled':cancelled, 'chunks_processed':len(processed_chunks), 'total_chunks':len(chunks),
        'concepts_found':len({(x.get('target') or {}).get('id') or graph._normalize(x['label']) for x in unique.values()}),
        'new':sum(x['status']=='new' for x in unique.values()),
        'known_ecume':len({x['target']['id'] for x in unique.values() if x['status']=='known' and x['target']['kind']=='ecume'}),
        'known_echo':len({t['id'] for x in unique.values() if x['status']=='known' for t in [x['target']] if t['kind']=='echo'}),
        'review':sum(x['status']=='review' for x in unique.values()),
        'analysis_problem':any(c['error'] for c in chunk_reports)}
    report['message'] = (f"Analyse arretee apres {len(processed_chunks)} partie(s) sur {len(chunks)}. Les premiers concepts restent disponibles." if cancelled else
        'Analyse incomplete : consulter les points a verifier.' if report['analysis_problem'] else
        'Aucun concept exploitable detecte. Ce resultat ne prouve pas que le document ne contient rien de nouveau.' if not unique else
        'Aucun nouveau concept propose. Les elements reconnus et les points a verifier restent consultables.' if not report['new'] else
        'Analyse terminee. Les nouveaux concepts attendent votre decision.')
    run_id, timestamp = str(uuid.uuid4()), now_iso()
    with transaction() as conn:
        conn.execute('INSERT INTO review_runs VALUES (?,?,?,?)', (run_id,document['id'],json.dumps(report),timestamp))
        for item in unique.values():
            conn.execute('INSERT INTO review_mentions VALUES (?,?,?,?,?,?,?,?,?)',
                (str(uuid.uuid4()),run_id,document['id'],json.dumps(item),item['status'],
                 item['target']['id'] if item.get('target') and item['target']['kind']=='ecume' else '', '',timestamp,timestamp))
        record_change(entity_type='document',entity_id=document['id'],action='review_partially_prepared' if cancelled else 'review_prepared',origin='llm',source_id=document['id'],details=report)
    from app.services.document_service import propose_domain
    propose_domain(document['id'])
    return {'document_id':document['id'], 'cards':[], 'warnings':[i['message'] for i in issues],
            'review_report':report, 'cancelled':cancelled}


def _decode(row):
    payload = json.loads(row['payload'])
    if row['card_id']:
        from app.services.analysis_service import get_card
        card = get_card(row['card_id'])
        if card:
            payload.update(label=card['main_effect']['label'],description=card['main_effect']['description'],
                fields=card.get('extraction_details',{}).get('simple_fields',payload.get('fields',{})),
                category=card['business_category'], archimate_mapping=card.get('archimate_mapping'))
            row = {**dict(row), 'status':'validated' if coherence.is_valid(card) else
                'ignored' if card['status'] in ('rejected','linked') else 'review',
                'node_id':card['graph_node_ids'].get('effect',''), 'updated_at':max(row['updated_at'],card['updated_at'])}
    from app.semantic.archimate_mapping import infer_archimate_mapping
    payload['archimate_mapping'] = payload.get('archimate_mapping') or infer_archimate_mapping(
        business_category=payload.get('category','non_qualifie'), concept_label=payload['label'])
    payload['qualification_choices'] = qualification_choices(payload['label'], payload.get('description',''))
    return {**payload, **{k:row[k] for k in ('id','document_id','status','node_id','card_id','updated_at')}}


def workspace(document_id=''):
    from app.services.analysis_service import list_cards
    with get_db() as conn:
        all_mentions = [_decode(r) for r in conn.execute('SELECT * FROM review_mentions ORDER BY created_at DESC') if not document_id or r['document_id']==document_id]
        reports = [{**json.loads(r['report']), 'document_id':r['document_id'], 'id':r['id']} for r in conn.execute('SELECT * FROM review_runs ORDER BY created_at DESC') if not document_id or r['document_id']==document_id]
        titles = {r['id']:r['filename'] for r in conn.execute('SELECT id,filename FROM source_documents UNION SELECT id,filename FROM document_references')}
    # Keep decisions and only the latest undecided occurrence per document/label.
    mentions, seen = [], set()
    valid_targets = {e['id'] for e in index()}
    for item in all_mentions:
        key = (item['document_id'], graph._normalize(item['label']))
        if key in seen and item['status'] in ('new','review','known'):
            continue
        seen.add(key)
        item['document_title'] = titles.get(item['document_id'], '')
        if item['status'] == 'known' and (item.get('target') or {}).get('id') not in valid_targets:
            item['status'] = 'review'
            item['issues'] = [*item.get('issues',[]), 'Le concept rattache a ete retire ou modifie. Choisir une nouvelle cible.']
        mentions.append(item)
    bound = {m['card_id'] for m in all_mentions if m['card_id']}
    alerts = []
    for card in list_cards():
        if card['id'] in bound or (document_id and card['document_id'] != document_id) or card['status']=='linked':
            continue
        if diagnostic(card['main_effect']['label']):
            alerts.append({'message':'Ancienne alerte technique, pas un concept metier. Donnee historique conservee.', 'source_excerpt':card['source_excerpt']})
            continue
        mentions.append({'id':'legacy:'+card['id'], 'card_id':card['id'], 'document_id':card['document_id'],
            'document_title':titles.get(card['document_id'],''), 'archimate_mapping':card.get('archimate_mapping'),
            'business_rules':card.get('extraction_details',{}).get('business_rules',[]),
            'node_id':card['graph_node_ids'].get('effect',''), 'label':card['main_effect']['label'],
            'description':card['main_effect']['description'], 'source_excerpt':card['source_excerpt'],
            'fields':card.get('extraction_details',{}).get('simple_fields', {key:[{'text':v,'origin':'legacy','source_excerpt':card['source_excerpt']} for v in card.get(role,[])] for key,role in [('objects','objects'),('actions','actions'),('rules','conditions')]}), 'issues':[], 'target':None, 'candidates':[],
            'status':'validated' if coherence.is_valid(card) else 'ignored' if card['status']=='rejected' else 'review' if card['status']=='to_confirm' else 'new',
            'updated_at':card['updated_at']})
    return {'items':mentions, 'reports':reports, 'issues':alerts}


@atomic
def decide(mention_id, request):
    from app.services import card_service, analysis_service
    from app.models.schemas import CardUpdate
    action = request['action']
    if mention_id.startswith('legacy:'):
        card_id = mention_id.split(':',1)[1]
        card = card_service.require_card(card_id)
        if diagnostic(card['main_effect']['label']):
            raise ValueError('Une alerte technique ne peut pas etre validee comme concept.')
        if action == 'accept':
            card_service.accept_card(card_id)
        elif action == 'ignore':
            card_service.update_card(card_id, CardUpdate(status='rejected'))
        elif action == 'update':
            main = dict(card['main_effect'], label=request.get('label',card['main_effect']['label']), description=request.get('description',card['main_effect']['description']))
            changes = {role:request['fields'].get(key,[]) for key,role in [('objects','objects'),('actions','actions'),('rules','conditions')]} if 'fields' in request else {}
            card_service.update_card(card_id, CardUpdate(main_effect=main, **changes))
        elif action == 'qualify':
            category = request.get('business_category')
            if not category or category == 'non_qualifie':
                raise ValueError('Choisir une signification métier proposée.')
            was_valid = coherence.is_valid(card)
            card_service.update_card(card_id, CardUpdate(business_category=category))
            if was_valid:
                card_service.accept_card(card_id)
        else:
            raise ValueError('Cette action demande une nouvelle analyse pour les anciennes cartes.')
        return {'ok':True}
    with get_db() as conn:
        row = conn.execute('SELECT * FROM review_mentions WHERE id=?',(mention_id,)).fetchone()
        if not row:
            raise ValueError('Proposition introuvable.')
        item = _decode(row)
        before = json.loads(json.dumps(item))
        if item['card_id'] and card_service.require_card(item['card_id'])['status']=='linked':
            raise ValueError('Cette carte a ete fusionnee. Modifiez la carte cible de la fusion.')
        if action == 'keep':
            return item
        if action == 'qualify':
            from app.semantic.archimate_mapping import infer_archimate_mapping, normalize_business_category
            category = normalize_business_category(request.get('business_category'))
            if category == 'non_qualifie':
                raise ValueError('Choisir une signification métier proposée.')
            item['category'] = category
            item['archimate_mapping'] = infer_archimate_mapping(
                business_category=category, concept_label=item['label'], status='inferred_from_user_answer',
                reason="L'utilisateur a précisé ce que représente le concept ; ECUME a traduit ce choix en candidat ArchiMate.")
            if item['card_id']:
                card = card_service.require_card(item['card_id'])
                was_valid = coherence.is_valid(card)
                card_service.update_card(card['id'], CardUpdate(business_category=category))
                if was_valid:
                    card_service.accept_card(card['id'])
        elif request.get('field_key'):
            values = item.get('fields',{}).get(request['field_key'],[])
            position = request.get('field_index',0)
            if position >= len(values) or action not in ('attach','new'):
                raise ValueError('Champ ou action introuvable.')
            value = values[position]
            if action == 'attach':
                target = next((e for e in index() if e['id']==request.get('target_id')), None)
                if not target:
                    raise ValueError('Choisir une cible valide.')
                value.update(target=target, status='known', force_new=False, mapping_origin='user')
            else:
                value.update(target=None, node_id='', status='new', force_new=True, mapping_origin='user')
            item['status'] = 'review'
            if item['card_id']:
                _sync_card(item)
        elif action == 'update':
            for field in ('label','description'):
                if field in request:
                    item[field] = request[field].strip()
            if not item['label'] or diagnostic(item['label']):
                raise ValueError('Donner un vrai nom de concept metier.')
            if 'fields' in request:
                updated = {}
                for key, values in request['fields'].items():
                    if key not in QUESTIONS:
                        continue
                    previous = {v['text']:v for v in item['fields'].get(key,[])}
                    updated[key] = []
                    for value in dict.fromkeys(str(v).strip()[:500] for v in values):
                        if value:
                            status, target, candidates = classify(value, index())
                            updated[key].append(previous.get(value) or {'text':value, 'source_excerpt':'', 'origin':'user',
                                'status':status, 'target':target, 'candidates':candidates})
                    updated[key] = updated[key][:12]
                item['fields'] = updated
            item['status'] = 'review'
            if not request.get('preserve_identity'):
                item['target'] = None
            if item['card_id']:
                _sync_card(item)
        elif action in ('attach','alias','new','dismiss'):
            if item['card_id']:
                raise ValueError('Corriger ce concept depuis sa carte validee ; ne pas changer son identite silencieusement.')
            if action in ('attach','alias'):
                target = next((e for e in index() if e['id']==request.get('target_id')), None)
                if not target:
                    raise ValueError('Choisir un concept valide ou une reference active.')
                if action == 'alias' and target['kind'] == 'ecume':
                    graph._attach_variant(target['id'], item['label'], 'synonym', item['document_id'])
                item.update(target=target, node_id=target['id'] if target['kind']=='ecume' else '', status='known', force_new=False, mapping_origin='user')
            else:
                item.update(target=None, node_id='', status='new', force_new=True,
                            mapping_origin='user_new' if action == 'new' else 'user_dismissed_matches')
        elif action == 'ignore':
            item['status'] = 'ignored'
            if item['card_id']:
                card_service.update_card(item['card_id'], CardUpdate(status='rejected'))
        elif action == 'accept':
            if diagnostic(item['label']):
                raise ValueError('Une alerte n est pas un concept metier.')
            # Recheck inside the transaction: another document may have validated this name.
            status, target, candidates = classify(item['label'], index())
            if item.get('mapping_origin') == 'user' and item.get('target') and not item['card_id']:
                target = next((e for e in index() if e['id']==item['target']['id']), None)
                if not target:
                    raise ValueError('Le rattachement choisi n est plus disponible. Choisissez une autre cible.')
                status = 'known'
            if status == 'review' and not item.get('force_new') and not item['card_id']:
                raise ValueError('Un concept proche existe : choisissez le rattachement ou confirmez la creation d un nouveau concept.')
            if status == 'known' and not item.get('force_new') and not item['card_id']:
                item.update(status='known',target=target,node_id=target['id'] if target['kind']=='ecume' else '')
            else:
                if not item['card_id']:
                    document = analysis_service.get_document(item['document_id'])
                    if not document:
                        raise ValueError('Document supprime : cette proposition ne peut plus etre materialisee.')
                    raw = {'main_effect':{'label':item['label'],'description':item['description']},
                        'source_excerpt':item['source_excerpt'], 'business_category':item.get('category','non_qualifie'),
                        'archimate_mapping':item.get('archimate_mapping'),
                        'simple_fields':item['fields'], 'business_rules':item.get('business_rules',[]),
                        'force_new':item.get('force_new',False)}
                    card = analysis_service._store_card(document,raw,[])
                    item['card_id'] = card['id']
                else:
                    card = card_service.require_card(item['card_id'])
                    card_service.update_card(card['id'], CardUpdate(main_effect={**card['main_effect'], 'label':item['label'], 'description':item['description']}))
                card = card_service.accept_card(item['card_id'])
                item.update(status='validated', node_id=card['graph_node_ids']['effect'])
        else:
            raise ValueError('Action inconnue.')
        timestamp = now_iso()
        conn.execute('UPDATE review_mentions SET payload=?, status=?,node_id=?,card_id=?,updated_at=? WHERE id=?',
            (json.dumps(item),item['status'],item['node_id'],item['card_id'],timestamp,mention_id))
        record_change(entity_type='mention',entity_id=mention_id,action=action,origin='user',source_id=item['document_id'],details={'before':before,'after':item})
    return item


def _sync_card(item):
    from app.services import card_service
    from app.services.review_graph import synchronize
    from app.models.schemas import CardUpdate
    card = card_service.require_card(item['card_id'])
    details = {**card.get('extraction_details',{}), 'simple_fields':item['fields']}
    with get_db() as conn:
        conn.execute('UPDATE extracted_cards SET extraction_details=? WHERE id=?', (json.dumps(details),card['id']))
    updated = card_service.update_card(card['id'], CardUpdate(status='to_confirm',
        main_effect={**card['main_effect'],'label':item['label'],'description':item['description']}))
    synchronize(card, updated)
