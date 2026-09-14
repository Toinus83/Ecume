import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from test_mvp import isolated_data_dir
from test_documents import knowledge_snapshot, upload, create_card
from app.database import db
from app.main import app
from app.services import reference_service as references
from app.services.reference_parser import parse_reference

TTL = b'''@prefix e: <https://example.org/echo#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
e: a owl:Ontology; rdfs:label "Reference locale"@fr; owl:versionInfo "1.2".
e:Acces a skos:Concept; skos:prefLabel "Acces"@fr; skos:altLabel "Desserte"@fr;
 skos:definition "Possibilite de rejoindre les constructions."@fr;
 skos:broader e:Mobilite; skos:related e:Voie .
e:Mobilite a skos:Concept; skos:prefLabel "Mobilite"@fr; skos:narrower e:Acces .
e:Voie a owl:Class; rdfs:label "Voie"@fr; rdfs:comment "Infrastructure de circulation."@fr .'''

XML = b'''<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#" xmlns:owl="http://www.w3.org/2002/07/owl#">
 <owl:Class rdf:about="https://example.org/echo#Acces"><rdfs:label xml:lang="fr">Acces</rdfs:label>
 <rdfs:subClassOf rdf:resource="https://example.org/echo#Mobilite"/></owl:Class>
</rdf:RDF>'''


def test_import_ttl_profile_and_separate_storage():
    create_card(upload())
    before = knowledge_snapshot()
    reference = references.import_reference('Echo_Quelconque.ttl', TTL)
    assert reference['name'] == 'Reference locale'
    assert reference['version'] == '1.2'
    assert reference['namespace'] == 'https://example.org/echo#'
    assert reference['profile']['main_language'] == 'fr'
    assert reference['profile']['term_count'] == 3
    assert reference['profile']['relation_count'] == 3
    term = next(item for item in references.terms(reference['id'])['items'] if item['label']=='Acces')
    assert term['aliases'] == ['Desserte']
    assert 'constructions' in term['definition']
    assert before['knowledge_nodes'] == knowledge_snapshot()['knowledge_nodes']
    with db.get_db() as conn:
        assert conn.execute('SELECT source_content FROM reference_repositories').fetchone()[0] == TTL
    assert 'source_content' not in reference
    assert reference['content_hash'] == hashlib.sha256(TTL).hexdigest()


@pytest.mark.parametrize('extension', ['rdf','owl'])
def test_rdfxml_and_owl_import(extension):
    reference = references.import_reference('Example.'+extension, XML)
    assert reference['format'] == 'RDF/XML'
    assert reference['profile']['owl_class_count'] == 1
    assert reference['profile']['relation_count'] == 1


def test_owl_turtle_serialization_is_detected():
    assert references.import_reference('Example.owl', TTL)['format'] == 'Turtle'


def test_reimport_is_idempotent_and_keeps_activation():
    first = references.import_reference('Example.ttl', TTL)
    references.set_active(first['id'], False)
    second = references.import_reference('Renamed.ttl', TTL)
    assert second['already_imported'] and not second['active']
    assert first['id'] == second['id']
    assert len(references.list_repositories()) == 1


def test_delete_reference_requires_confirmation_and_preserves_knowledge():
    create_card(upload())
    before = knowledge_snapshot()['knowledge_nodes']
    reference = references.import_reference('Example.ttl', TTL)
    with pytest.raises(ValueError):
        references.delete_repository(reference['id'], '')
    assert references.delete_repository(reference['id'], 'SUPPRIMER')['knowledge_preserved']
    assert references.list_repositories() == []
    assert knowledge_snapshot()['knowledge_nodes'] == before


@pytest.mark.parametrize('data,extension', [(b'not RDF','.ttl'), (TTL,'.jsonld'), (b'', '.ttl'),
    (b'<!DOCTYPE rdf:RDF [<!ENTITY x SYSTEM "file:///C:/Windows/win.ini">]><rdf:RDF/>','.rdf')])
def test_invalid_and_external_entities_are_rejected(data, extension):
    with pytest.raises(ValueError):
        references.import_reference('Example'+extension, data)
    assert references.list_repositories() == []


def test_remote_imports_not_loaded_and_partial_profile_is_explicit(monkeypatch):
    import urllib.request
    def forbidden(*args, **kwargs):
        raise AssertionError('Network accessed')
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    parsed = parse_reference(TTL+b'\n<https://example.org/o> owl:imports <http://127.0.0.1:1/remote.owl> .', '.ttl', 'hash')
    assert parsed['profile']['status'] == 'partial'
    assert any('owl:imports' in warning for warning in parsed['profile']['warnings'])


def test_unknown_conventions_are_preserved_not_invented():
    parsed = parse_reference(b'<https://example.org/a> <https://example.org/name> "Unknown".', '.ttl', 'hash')
    assert parsed['profile']['status'] == 'partial'
    assert not parsed['terms']
    assert parsed['profile']['label_properties'] == []
    assert 'https://example.org/name' in parsed['profile']['other_properties']


def test_reference_http_upload_and_sample():
    with TestClient(app) as client:
        result = client.post('/references/import', files={'file':('Echo.ttl', TTL,'text/turtle')})
        assert result.status_code == 200, result.text
        reference_id = result.json()['id']
        assert client.get(f'/references/{reference_id}/terms?q=Acces').json()['total'] == 1
        assert client.patch(f'/references/{reference_id}', json={'active':False}).json()['active'] is False
        assert client.request('DELETE', f'/references/{reference_id}', json={'confirmation':'SUPPRIMER'}).status_code == 200


def test_reference_size_and_triple_limits_leave_no_partial_import(monkeypatch):
    from app.services import reference_parser as parser
    monkeypatch.setattr(parser, 'MAX_BYTES', len(TTL)-1)
    with pytest.raises(ValueError, match='5 Mo'):
        references.import_reference('TooLarge.ttl', TTL)
    monkeypatch.setattr(parser, 'MAX_BYTES', len(TTL)+1)
    monkeypatch.setattr(parser, 'MAX_TRIPLES', 2)
    with pytest.raises(ValueError, match='triplets'):
        references.import_reference('TooMany.ttl', TTL)
    assert references.list_repositories() == []
