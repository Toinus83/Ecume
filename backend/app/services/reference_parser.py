from __future__ import annotations

from collections import Counter
from contextvars import ContextVar
import sys
import xml.sax

from defusedxml import ElementTree as SafeXML
from defusedxml.common import DefusedXmlException
from rdflib import Graph, URIRef, Literal, BNode
from rdflib.namespace import RDF, RDFS, OWL, SKOS
from rdflib.plugin import get as get_plugin
from rdflib.parser import Parser

MAX_BYTES = 5 * 1024 * 1024
MAX_TRIPLES = 100000
_reading_reference = ContextVar('reading_reference', default=False)


def _restrict_parser(event, args):
    if _reading_reference.get() and (event == 'open' or event == 'urllib.Request' or event.startswith('socket.')):
        raise ValueError('Acces externe interdit pendant la lecture du referentiel.')


# Load parser code before enforcing in-memory-only reads in this context/thread.
get_plugin('turtle', Parser)
get_plugin('xml', Parser)
xml.sax.make_parser()
sys.addaudithook(_restrict_parser)


class BoundedGraph(Graph):
    def add(self, triple):
        if len(self) >= MAX_TRIPLES:
            raise ValueError('Referentiel trop volumineux : maximum 100 000 triplets.')
        return super().add(triple)


LABELS = (SKOS.prefLabel, RDFS.label)
ALIASES = (SKOS.altLabel, SKOS.hiddenLabel)
DEFINITIONS = (SKOS.definition,)
HIERARCHY = (SKOS.broader, SKOS.narrower, RDFS.subClassOf)
ASSOCIATIVE = (SKOS.related, OWL.equivalentClass)
TERM_TYPES = (OWL.Class, RDFS.Class, SKOS.Concept)


def namespace(uri: str) -> str:
    if '#' in uri:
        return uri.rsplit('#', 1)[0] + '#'
    return uri.rsplit('/', 1)[0] + '/' if '/' in uri else ''


def local_name(uri: str) -> str:
    return uri.rsplit('#', 1)[-1].rsplit('/', 1)[-1].rsplit(':', 1)[-1]


def _literals(graph, subject, predicates):
    values = [(str(value), value.language or '', str(predicate)) for predicate in predicates
              for value in graph.objects(subject, predicate) if isinstance(value, Literal)]
    return sorted(set(values), key=lambda item: (0 if item[1].startswith('fr') else 1 if not item[1] else 2, predicates.index(URIRef(item[2])), item))


def parse_reference(data: bytes, extension: str, digest: str) -> dict:
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Le fichier doit contenir entre 1 octet et 5 Mo.')
    if extension not in {'.ttl', '.rdf', '.owl'}:
        raise ValueError('Formats acceptes : TTL, RDF/XML et OWL en RDF/XML ou Turtle.')
    base = f'https://ecume.invalid/reference/{digest}/'
    formats = ['turtle'] if extension == '.ttl' else ['xml', 'turtle']
    graph = None
    detected = ''
    for format_name in formats:
        candidate = BoundedGraph(bind_namespaces='none')
        try:
            if format_name == 'xml':
                SafeXML.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
            token = _reading_reference.set(True)
            try:
                candidate.parse(data=data, format=format_name, publicID=base)
            finally:
                _reading_reference.reset(token)
            graph, detected = candidate, 'RDF/XML' if format_name == 'xml' else 'Turtle'
            break
        except DefusedXmlException as exc:
            raise ValueError('XML refuse : declarations DTD et entites externes interdites.') from exc
        except Exception as exc:
            if isinstance(exc, ValueError) and ('volumineux' in str(exc) or 'Acces externe' in str(exc)):
                raise
    if graph is None or not len(graph):
        raise ValueError('Referentiel illisible ou vide. Verifiez la syntaxe Turtle ou RDF/XML ; OWL/XML fonctionnel non pris en charge.')
    warnings = []
    subjects = {subject for kind in TERM_TYPES for subject in graph.subjects(RDF.type, kind) if isinstance(subject, URIRef)}
    known = set(subjects)
    subjects.update(subject for predicate in (*LABELS, *DEFINITIONS) for subject in graph.subjects(predicate, None)
                    if isinstance(subject, URIRef) and (subject, RDF.type, OWL.Ontology) not in graph
                    and not any((subject, RDF.type, kind) in graph for kind in (RDF.Property, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty)))
    if subjects - known:
        warnings.append('Certains termes etiquetes ne sont pas declares comme classes OWL ou concepts SKOS : profil partiel.')
    if not subjects:
        warnings.append('Aucune classe ou concept etiquete reconnu. Les conventions peuvent etre specifiques.')
    if any(isinstance(value, BNode) for triple in graph for value in triple):
        warnings.append('Structures anonymes conservees dans la copie source, mais non interpretees pour les correspondances.')
    if any(graph.triples((None, OWL.imports, None))):
        warnings.append('Dependances owl:imports non chargees : aucune lecture distante.')
    if any(str(value).startswith(base) for triple in graph for value in triple if isinstance(value, URIRef)):
        warnings.append('URI relatives sans base explicite : resolution sur une base technique ECUME, profil partiel.')
    terms = []
    for subject in sorted(subjects, key=str):
        labels = _literals(graph, subject, LABELS)
        alt = _literals(graph, subject, ALIASES)
        definitions = _literals(graph, subject, DEFINITIONS)
        comments = _literals(graph, subject, (RDFS.comment,))
        properties = {}
        for predicate, value in graph.predicate_objects(subject):
            properties.setdefault(str(predicate), []).append({'value': str(value), 'kind': 'literal' if isinstance(value, Literal) else 'blank' if isinstance(value, BNode) else 'uri',
                'language': value.language or '' if isinstance(value, Literal) else '', 'datatype': str(value.datatype or '') if isinstance(value, Literal) else ''})
        terms.append({'uri': str(subject), 'label': labels[0][0] if labels else local_name(str(subject)),
            'aliases': sorted({value[0] for value in [*alt, *labels[1:]]}),
            'definition': '\n'.join(dict.fromkeys(value[0] for value in definitions)),
            'comment': '\n'.join(dict.fromkeys(value[0] for value in comments)),
            'language': labels[0][1] if labels else '',
            'types': sorted(str(value) for value in graph.objects(subject, RDF.type)), 'properties': properties})
    term_uris = {item['uri'] for item in terms}
    relations = []
    for source, predicate, target in graph:
        if str(source) in term_uris and isinstance(target, URIRef) and predicate not in {RDF.type, OWL.imports, RDFS.isDefinedBy, RDFS.seeAlso}:
            if predicate in HIERARCHY or predicate in ASSOCIATIVE or str(target) in term_uris:
                label = _literals(graph, predicate, LABELS)
                relations.append({'source_uri':str(source), 'target_uri':str(target), 'relation_type':str(predicate),
                                  'label':label[0][0] if label else local_name(str(predicate))})
    used = {str(predicate) for _, predicate, _ in graph}
    uris = {str(value) for triple in graph for value in triple if isinstance(value, URIRef)}
    namespaces = {prefix or '': str(uri) for prefix, uri in graph.namespaces() if any(value.startswith(str(uri)) for value in uris)}
    principal = Counter(namespace(item['uri']) for item in terms if namespace(item['uri']) and not item['uri'].startswith(base))
    language = Counter(value.language for _, _, value in graph if isinstance(value, Literal) and value.language)
    ontologies = sorted(graph.subjects(RDF.type, OWL.Ontology), key=str)
    versions = sorted({str(value) for subject in ontologies for value in graph.objects(subject, OWL.versionInfo)})
    if len(versions) > 1:
        warnings.append('Plusieurs versions declarees ; verifier la version cible avant export.')
    naming = _literals(graph, ontologies[0], LABELS) if ontologies else []
    if not any(str(predicate) in used for predicate in LABELS):
        warnings.append('Propriete de libelle standard absente. Les noms affiches sont derives des URI.')
    profile = {'status': 'partial' if warnings else 'detected', 'warnings':warnings, 'namespaces':namespaces,
        'base_uris':[str(value) for value in ontologies], 'main_language':language.most_common(1)[0][0] if language else '',
        'term_count':len(terms), 'relation_count':len(relations), 'triple_count':len(graph),
        'owl_class_count':len(set(graph.subjects(RDF.type, OWL.Class))), 'skos_concept_count':len(set(graph.subjects(RDF.type, SKOS.Concept))),
        'label_properties':[str(p) for p in LABELS if str(p) in used], 'alias_properties':[str(p) for p in ALIASES if str(p) in used],
        'definition_properties':[str(p) for p in DEFINITIONS if str(p) in used], 'comment_properties':[str(RDFS.comment)] if str(RDFS.comment) in used else [],
        'hierarchy_properties':[str(p) for p in HIERARCHY if str(p) in used], 'associative_properties':[str(p) for p in ASSOCIATIVE if str(p) in used],
        'other_properties':sorted(used - {str(p) for p in (*LABELS,*ALIASES,*DEFINITIONS,*HIERARCHY,*ASSOCIATIVE,RDF.type,RDFS.comment)}),
        'naming_conventions': 'Non inferees : noms de fichiers et URI conserves sans convention imposee.'}
    return {'name':naming[0][0] if naming else '', 'format':detected, 'namespace':principal.most_common(1)[0][0] if principal else '',
            'version':versions[0] if len(versions)==1 else '', 'profile':profile, 'terms':terms,
            'relations':sorted(relations, key=lambda item:(item['source_uri'],item['relation_type'],item['target_uri']))}
