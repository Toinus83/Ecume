from __future__ import annotations

from difflib import SequenceMatcher
import hashlib
import json
import uuid

from app.database.db import atomic, get_db, now_iso
from app.services import graph_service as graph, reference_service as references
from app.services.coherence_service import is_valid

MATCH_TYPES = {'exactMatch','closeMatch','broadMatch','narrowMatch','relatedMatch'}
STATUSES = {'validated','to_review','rejected'}


def target_signature(term: dict) -> str:
    aliases=term.get('aliases',[])
    if isinstance(aliases,str):
        aliases=json.loads(aliases)
    return hashlib.sha256(json.dumps([term.get('label',''),sorted(aliases),term.get('definition','')],ensure_ascii=False).encode()).hexdigest()


def signature(node: dict) -> str:
    values = {key:node.get(key) for key in ('label','description','business_category','level')}
    with get_db() as conn:
        values['aliases'] = [row[0] for row in conn.execute('SELECT label FROM knowledge_node_aliases WHERE node_id=? ORDER BY label', (node['id'],))]
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def mappings(node_id: str = '', repository_id: str = '') -> list[dict]:
    with get_db() as conn:
        rows = conn.execute('''SELECT m.*, r.name repository_name, r.active repository_active,
            t.label target_label, t.definition target_definition, t.aliases target_aliases
            FROM echo_mappings m JOIN reference_repositories r ON r.id = m.repository_id
            JOIN reference_terms t ON t.repository_id = m.repository_id AND t.uri = m.target_uri
            JOIN knowledge_nodes n ON n.id = m.node_id
            WHERE (? = '' OR m.node_id = ?) AND (? = '' OR m.repository_id = ?)
            ORDER BY r.name COLLATE NOCASE, m.score DESC, t.label COLLATE NOCASE, m.id''',
            (node_id,node_id,repository_id,repository_id)).fetchall()
    nodes = {node['id']:node for node in graph.list_nodes()}
    signatures = {node_id:signature(nodes[node_id]) for node_id in {row['node_id'] for row in rows}}
    return [{**dict(row), 'target_aliases':json.loads(row['target_aliases']),
             'node_label':nodes[row['node_id']]['label'], 'repository_active':bool(row['repository_active']),
             'stale':row['node_signature'] != signatures[row['node_id']] or bool(row['target_signature'] and row['target_signature'] != target_signature({'label':row['target_label'],'aliases':row['target_aliases'],'definition':row['target_definition']}))} for row in rows]


def _words(value: str) -> set[str]:
    ignored = {'avec','dans','pour','cette','ceux','sans','etre','comme','entre','plus','moins'}
    return {word for word in graph._normalize(value).split() if len(word)>3 and word not in ignored}


def _candidate(node: dict, aliases: list[str], term: dict, context: str) -> tuple[float,str,str] | None:
    left = [graph._normalize(value) for value in [node['label'],*aliases] if value]
    right = [graph._normalize(value) for value in [term['label'],*term['aliases']] if value]
    if set(left) & set(right):
        return 1.0, 'exactMatch', 'Libelle ou synonyme identique. Le meme sens reste a confirmer.'
    similarity = max((SequenceMatcher(None,a,b).ratio() for a in left for b in right), default=0)
    words = _words(node.get('description','')+' '+context)
    reference_words = _words(term['definition']+' '+term['comment'])
    overlap = len(words & reference_words) / max(1,min(len(words),len(reference_words)))
    if similarity >= .66:
        score = min(.96, .85*similarity + .15*overlap)
        return round(score,4), 'closeMatch', f'Proximite des noms {similarity:.0%}; contexte et definition {overlap:.0%}. Candidat lexical, pas une equivalence prouvee.'
    if len(words & reference_words) >= 3 and overlap >= .5:
        return round(min(.79,.5+.25*overlap),4), 'relatedMatch', 'Plusieurs mots significatifs communs dans les definitions ou le contexte documentaire. Sens a verifier.'
    return None


@atomic
def propose(repository_id: str = '', node_id: str = '') -> dict:
    if repository_id:
        repository = references.require_repository(repository_id)
        if not repository['active']:
            raise ValueError('Activez le referentiel avant de rechercher des correspondances.')
    repositories = [item for item in references.list_repositories() if item['active'] and (not repository_id or item['id']==repository_id)]
    if not repositories:
        raise ValueError('Aucun referentiel actif. Importez ou activez une reference.')
    nodes = [node for node in graph.list_nodes() if is_valid(node) and (not node_id or node['id']==node_id)]
    if node_id and not nodes:
        raise ValueError('Validez le concept metier avant de chercher une correspondance.')
    counts = {'concepts':len(nodes),'created':0,'updated':0,'human_decisions_preserved':0,'without_candidate':0}
    from app.services.changelog_service import record_change
    with get_db() as conn:
        terms_by_repository = {repository['id']:[references.decode(row) for row in conn.execute('SELECT * FROM reference_terms WHERE repository_id=?', (repository['id'],))] for repository in repositories}
        if len(nodes)*sum(map(len,terms_by_repository.values())) > 250000:
            raise ValueError('Ce lot est trop grand pour une recherche rapide. Lancez les correspondances concept par concept depuis les cartes.')
        node_ids = {node['id'] for node in nodes}
        counts['human_decisions_preserved'] = sum(1 for row in conn.execute("SELECT node_id,repository_id FROM echo_mappings WHERE decision_origin='user'")
                                                 if row['node_id'] in node_ids and row['repository_id'] in terms_by_repository)
        aliases = {}
        for row in conn.execute('SELECT node_id,label FROM knowledge_node_aliases'):
            aliases.setdefault(row['node_id'],[]).append(row['label'])
        contexts = {}
        for row in conn.execute('''SELECT b.node_id,c.theme_label,c.source_excerpt FROM card_concepts b
                JOIN extracted_cards c ON c.id=b.card_id WHERE c.status IN ('accepted','accepted_orphan')'''):
            contexts.setdefault(row['node_id'],[]).append(row['theme_label']+' '+row['source_excerpt'][:1200])
        for node in nodes:
            found = False
            for repository in repositories:
                terms = terms_by_repository[repository['id']]
                matches = []
                for term in terms:
                    candidate = _candidate(node, aliases.get(node['id'],[]),term,' '.join(contexts.get(node['id'],[])[:5])+' '+node.get('business_category','').replace('_',' '))
                    if candidate:
                        matches.append((candidate,term))
                matches.sort(key=lambda item:(-item[0][0],item[1]['label'].casefold(),item[1]['uri']))
                for (score,kind,reason),term in matches[:5]:
                    found = True
                    current = conn.execute('SELECT * FROM echo_mappings WHERE node_id=? AND repository_id=? AND target_uri=?',
                                           (node['id'],repository['id'],term['uri'])).fetchone()
                    if current and current['decision_origin']=='user':
                        continue
                    timestamp = now_iso()
                    mapping_id = current['id'] if current else str(uuid.uuid4())
                    conn.execute('''INSERT INTO echo_mappings
                        (id,node_id,repository_id,target_uri,match_type,score,reason,node_signature,created_at,updated_at,target_signature)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(node_id,repository_id,target_uri) DO UPDATE SET
                        match_type=excluded.match_type,score=excluded.score,reason=excluded.reason,
                        node_signature=excluded.node_signature,updated_at=excluded.updated_at,status='candidate',target_signature=excluded.target_signature ''',
                        (mapping_id,node['id'],repository['id'],term['uri'],kind,score,reason,signature(node),timestamp,timestamp,target_signature(term)))
                    counts['updated' if current else 'created'] += 1
            if not found:
                counts['without_candidate'] += 1
        record_change(entity_type='echo_mapping', entity_id=repository_id or node_id or 'active_references', action='candidates_searched', origin='user', details=counts)
    return counts


@atomic
def decide(mapping_id: str, match_type: str, status: str) -> dict:
    from app.services.changelog_service import record_change
    if match_type not in MATCH_TYPES or status not in STATUSES:
        raise ValueError('Decision de correspondance invalide.')
    with get_db() as conn:
        before = conn.execute('SELECT * FROM echo_mappings WHERE id=?', (mapping_id,)).fetchone()
        if not before:
            raise ValueError('Correspondance introuvable.')
        node = graph.get_node(before['node_id'])
        if not node or not is_valid(node):
            raise ValueError('Le concept doit etre valide avant de decider sa correspondance.')
        repository = references.require_repository(before['repository_id'])
        if not repository['active']:
            raise ValueError('Reactivez le referentiel avant de decider une correspondance.')
        term=conn.execute('SELECT * FROM reference_terms WHERE repository_id=? AND uri=?',(repository['id'],before['target_uri'])).fetchone()
        conn.execute('''UPDATE echo_mappings SET match_type=?,status=?,decision_origin='user',node_signature=?,updated_at=?,target_signature=? WHERE id=?''',
                     (match_type,status,signature(node),now_iso(),target_signature(dict(term)),mapping_id))
        record_change(entity_type='echo_mapping',entity_id=mapping_id,action=status,origin='user',
                      details={'before':dict(before),'match_type':match_type,'node_id':node['id'],'repository_id':repository['id']})
    return next(item for item in mappings(before['node_id'],before['repository_id']) if item['id']==mapping_id)
