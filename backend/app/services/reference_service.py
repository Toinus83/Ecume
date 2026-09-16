from __future__ import annotations

import hashlib
import json
from pathlib import PurePath
import uuid
import re
import copy

from app.database.db import atomic, get_db, now_iso
from app.services.changelog_service import record_change
from app.services.reference_parser import parse_reference, MAX_BYTES

REPOSITORY_COLUMNS = 'id, name, filename, format, content_hash, created_at, active, namespace, version, profile'


def decode(row) -> dict:
    result = dict(row)
    for field in ('profile', 'aliases', 'types', 'properties'):
        if field in result:
            result[field] = json.loads(result[field])
    if 'active' in result:
        result['active'] = bool(result['active'])
    return result


def list_repositories() -> list[dict]:
    with get_db() as conn:
        return [decode(row) for row in conn.execute(f'SELECT {REPOSITORY_COLUMNS} FROM reference_repositories ORDER BY name COLLATE NOCASE, id')]


def require_repository(repository_id: str) -> dict:
    with get_db() as conn:
        row = conn.execute(f'SELECT {REPOSITORY_COLUMNS} FROM reference_repositories WHERE id = ?', (repository_id,)).fetchone()
    if not row:
        raise ValueError('Referentiel introuvable.')
    return decode(row)


def terms(repository_id: str, query: str = '', offset: int = 0) -> dict:
    require_repository(repository_id)
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM reference_terms WHERE repository_id = ? ORDER BY label COLLATE NOCASE, uri', (repository_id,)).fetchall()
    needle = query.strip().casefold()
    values = [decode(row) for row in rows if not needle or needle in (' '.join(str(row[key]) for key in ('label','aliases','definition','uri'))).casefold()]
    return {'items':values[offset:offset+8], 'total':len(values), 'has_more':offset+8<len(values)}


def _import_single(filename: str, data: bytes) -> dict:
    name = filename.replace('\\', '/').rsplit('/', 1)[-1]
    extension = PurePath(name).suffix.lower()
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Le fichier doit contenir entre 1 octet et 5 Mo.')
    digest = hashlib.sha256(data).hexdigest()
    with get_db() as conn:
        existing = conn.execute('SELECT id FROM reference_repositories WHERE content_hash = ?', (digest,)).fetchone()
    if existing:
        return {**require_repository(existing['id']), 'already_imported':True}
    parsed = parse_reference(data, extension, digest)
    return _store(name, data, digest, parsed)


def files(repository_id: str) -> list[dict]:
    with get_db() as conn:
        return [decode(row) for row in conn.execute('SELECT id,filename,content_hash,format,layer,created_at,profile FROM reference_files WHERE repository_id=? ORDER BY created_at,id',(repository_id,))]


@atomic
def import_reference(filename: str, data: bytes, repository_id: str = '', layer: str = 'auto') -> dict:
    if layer not in {'auto','owl','voc','shacl','mixed'}:
        raise ValueError('Couche inconnue.')
    name = filename.replace('\\','/').rsplit('/',1)[-1]
    parsed = parse_reference(data, PurePath(name).suffix.lower(), hashlib.sha256(data).hexdigest())
    match = re.match(r'(.+)\.(owl|voc|shacl)\.(ttl|rdf|xml)$',name,re.I)
    if not repository_id and match:
        repository_id = next((r['id'] for r in list_repositories() if r['name'].casefold()==match[1].casefold()),'')
    if repository_id:
        result = require_repository(repository_id)
    else:
        result = _import_single(name,data)
        repository_id = result['id']
        if match and not result.get('already_imported'):
            with get_db() as conn:
                conn.execute('UPDATE reference_repositories SET name=? WHERE id=?',(match[1],repository_id))
    with get_db() as conn:
        current = conn.execute('SELECT * FROM reference_files WHERE repository_id=?',(repository_id,)).fetchall()
        if not current:
            old = conn.execute('SELECT * FROM reference_repositories WHERE id=?',(repository_id,)).fetchone()
            old_parsed = parse_reference(old['source_content'],PurePath(old['filename']).suffix.lower(),old['content_hash'])
            conn.execute('INSERT INTO reference_files VALUES (?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),repository_id,old['filename'],old['content_hash'],old['format'],'auto',old['created_at'],json.dumps(old_parsed),old['source_content']))
        digest = hashlib.sha256(data).hexdigest()
        existing = conn.execute('SELECT id FROM reference_files WHERE repository_id=? AND content_hash=?',(repository_id,digest)).fetchone()
        if existing:
            if layer!='auto':
                conn.execute('UPDATE reference_files SET layer=? WHERE id=?',(layer,existing['id']))
        else:
            if len(current)>=12:
                raise ValueError('Maximum 12 fichiers par referentiel dans le MVP.')
            conn.execute('INSERT INTO reference_files VALUES (?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),repository_id,name,digest,parsed['format'],layer,now_iso(),json.dumps(parsed),data))
        _rebuild(repository_id)
    record_change(entity_type='reference',entity_id=repository_id,action='file_associated',origin='user',details={'filename':name,'content_hash':digest,'layer':layer})
    return {**require_repository(repository_id),'already_imported':bool(result.get('already_imported') or existing and current)}


def _rebuild(repository_id: str):
    records = files(repository_id)
    parsed = [record['profile'] for record in records]
    combined = copy.deepcopy(parsed[0]['profile'])
    terms_by_uri, relations = {}, {}
    for item in parsed:
        for term in item['terms']:
            if term['uri'] in terms_by_uri:
                old = terms_by_uri[term['uri']]
                old['aliases'] = sorted(set(old['aliases']+term['aliases']+([term['label']] if term['label']!=old['label'] else [])))
                old['types'] = sorted(set(old['types']+term['types']))
                old['definition'] = '\n'.join(dict.fromkeys(filter(None,[old['definition'],term['definition']])))
                for key,values in term['properties'].items():
                    old['properties'].setdefault(key,[]).extend(v for v in values if v not in old['properties'].get(key,[]))
            else:
                terms_by_uri[term['uri']] = copy.deepcopy(term)
        for rel in item['relations']:
            relations[(rel['source_uri'],rel['target_uri'],rel['relation_type'])] = rel
    if len(terms_by_uri)+len(relations)>100000:
        raise ValueError('Referentiel logique trop volumineux pour le MVP.')
    for key in ('label_properties','alias_properties','definition_properties','comment_properties','hierarchy_properties','associative_properties','other_properties','base_uris','warnings'):
        combined[key] = sorted({value for item in parsed for value in item['profile'].get(key,[])})
    combined['namespaces'] = {key:value for item in parsed for key,value in item['profile']['namespaces'].items()}
    echoes = [item['profile']['echo'] for item in parsed]
    echo = copy.deepcopy(echoes[0])
    for kind,fields in {'owl':['classes','properties'],'shacl':['shapes']}.items():
        for field in fields:
            echo[kind][field] = list({item['uri']:item for profile in echoes for item in profile[kind][field]}.values())
    echo['voc'] = {'term_count':sum('http://www.w3.org/2004/02/skos/core#Concept' in t['types'] for t in terms_by_uri.values()),'alias_count':sum(len(t['aliases']) for t in terms_by_uri.values())}
    for status in ('interpreted','uninterpreted'):
        echo['shacl'][status] = sum(s['status']==status for s in echo['shacl']['shapes'])
    echo['warnings'] = sorted({warning for profile in echoes for warning in profile['warnings']})
    for kind in ('owl','voc','shacl'):
        detected = any(p['layers'][kind]['state']!='not_provided' for p in echoes)
        declared = any(r['layer'] in {kind,'mixed'} for r in records)
        echo['layers'][kind] = {'state':'partial' if detected and (echo['shacl']['uninterpreted'] if kind=='shacl' else echo['warnings']) else 'imported' if detected else 'insufficient' if declared else 'not_provided'}
        if declared and not detected:
            echo['warnings'].append(f'Couche {kind.upper()} declaree mais aucun element standard reconnu.')
    echo['alignment_ready'] = any(p['alignment_ready'] for p in echoes)
    echo['warnings'].extend(w for w in combined['warnings'] if any(marker in w for marker in ('owl:imports','URI relatives','Plusieurs versions','pas declares')))
    echo['confidence'] = 'insufficient' if not echo['alignment_ready'] else 'partial' if echo['warnings'] else 'sufficient'
    echo['files'] = [{key:r[key] for key in ('id','filename','content_hash','format','layer','created_at')} for r in records]
    combined.update(echo=echo,term_count=len(terms_by_uri),relation_count=len(relations))
    with get_db() as conn:
        for term in terms_by_uri.values():
            old=conn.execute('SELECT * FROM reference_terms WHERE repository_id=? AND uri=?',(repository_id,term['uri'])).fetchone()
            if old:
                from app.services.echo_mapping_service import target_signature
                conn.execute("UPDATE echo_mappings SET target_signature=? WHERE repository_id=? AND target_uri=? AND target_signature=''",(target_signature(dict(old)),repository_id,term['uri']))
            conn.execute('''INSERT INTO reference_terms (id,repository_id,uri,label,aliases,definition,comment,language,types,properties) VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(repository_id,uri) DO UPDATE SET label=excluded.label,aliases=excluded.aliases,definition=excluded.definition,types=excluded.types,properties=excluded.properties''',
                (str(uuid.uuid4()),repository_id,term['uri'],term['label'],json.dumps(term['aliases']),term['definition'],term['comment'],term['language'],json.dumps(term['types']),json.dumps(term['properties'])))
        conn.execute('DELETE FROM reference_relations WHERE repository_id=?',(repository_id,))
        conn.executemany('INSERT INTO reference_relations VALUES (?,?,?,?,?)',[(repository_id,r['source_uri'],r['target_uri'],r['relation_type'],r['label']) for r in relations.values()])
        conn.execute('UPDATE reference_repositories SET profile=? WHERE id=?',(json.dumps(combined),repository_id))


@atomic
def _store(filename: str, data: bytes, digest: str, parsed: dict) -> dict:
    with get_db() as conn:
        existing = conn.execute('SELECT id FROM reference_repositories WHERE content_hash = ?', (digest,)).fetchone()
        if existing:
            return {**require_repository(existing['id']), 'already_imported':True}
        repository_id = str(uuid.uuid4())
        conn.execute('''INSERT INTO reference_repositories
            (id,name,filename,format,content_hash,created_at,namespace,version,profile,source_content)
            VALUES (?,?,?,?,?,?,?,?,?,?)''', (repository_id, parsed['name'] or PurePath(filename).stem, filename,
            parsed['format'], digest, now_iso(), parsed['namespace'], parsed['version'], json.dumps(parsed['profile']), data))
        conn.executemany('''INSERT INTO reference_terms
            (id,repository_id,uri,label,aliases,definition,comment,language,types,properties) VALUES (?,?,?,?,?,?,?,?,?,?)''',
            [(str(uuid.uuid4()), repository_id, term['uri'], term['label'], json.dumps(term['aliases']), term['definition'],
              term['comment'], term['language'], json.dumps(term['types']), json.dumps(term['properties'])) for term in parsed['terms']])
        conn.executemany('''INSERT INTO reference_relations (repository_id,source_uri,target_uri,relation_type,label) VALUES (?,?,?,?,?)''',
            [(repository_id, item['source_uri'], item['target_uri'], item['relation_type'], item['label']) for item in parsed['relations']])
        record_change(entity_type='reference', entity_id=repository_id, action='imported_read_only', origin='user',
                      details={'filename':filename, 'content_hash':digest, 'term_count':len(parsed['terms'])})
    return {**require_repository(repository_id), 'already_imported':False}


@atomic
def set_active(repository_id: str, active: bool) -> dict:
    before = require_repository(repository_id)
    with get_db() as conn:
        conn.execute('UPDATE reference_repositories SET active = ? WHERE id = ?', (int(active), repository_id))
    record_change(entity_type='reference', entity_id=repository_id, action='activation_changed', origin='user',
                  details={'before':before['active'], 'active':active})
    return require_repository(repository_id)


@atomic
def delete_repository(repository_id: str, confirmation: str) -> dict:
    repository = require_repository(repository_id)
    if confirmation != 'SUPPRIMER':
        raise ValueError('Saisissez SUPPRIMER pour effacer la copie locale et ses correspondances.')
    with get_db() as conn:
        decisions = [dict(row) for row in conn.execute('SELECT * FROM echo_mappings WHERE repository_id = ?', (repository_id,))]
        for table in ('echo_validation_reports','reference_files','echo_mappings','reference_relations','reference_terms'):
            conn.execute(f'DELETE FROM {table} WHERE repository_id = ?', (repository_id,))
        conn.execute('DELETE FROM reference_repositories WHERE id = ?', (repository_id,))
    record_change(entity_type='reference', entity_id=repository_id, action='deleted_local_copy', origin='user',
                  details={'repository':repository, 'mapping_decisions':decisions})
    return {'deleted':True, 'knowledge_preserved':True}
