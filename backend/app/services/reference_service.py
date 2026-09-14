from __future__ import annotations

import hashlib
import json
from pathlib import PurePath
import uuid

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


def import_reference(filename: str, data: bytes) -> dict:
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
        for table in ('echo_mappings','reference_relations','reference_terms'):
            conn.execute(f'DELETE FROM {table} WHERE repository_id = ?', (repository_id,))
        conn.execute('DELETE FROM reference_repositories WHERE id = ?', (repository_id,))
    record_change(entity_type='reference', entity_id=repository_id, action='deleted_local_copy', origin='user',
                  details={'repository':repository, 'mapping_decisions':decisions})
    return {'deleted':True, 'knowledge_preserved':True}
