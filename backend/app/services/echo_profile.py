"""Read local RDF conventions without inference or executable SHACL extensions."""
from rdflib import URIRef, Literal, BNode
from rdflib.namespace import RDF, RDFS, OWL, SKOS, SH

SUPPORTED = {'minCount','maxCount','datatype','class','nodeKind','in','pattern','flags'}
ANNOTATIONS = {'name','description','message','severity','order','group','deactivated'}


def value(term):
    return {'value':str(term), 'kind':'literal' if isinstance(term,Literal) else 'blank' if isinstance(term,BNode) else 'uri',
            'datatype':str(term.datatype or '') if isinstance(term,Literal) else '',
            'language':term.language or '' if isinstance(term,Literal) else ''}


def label(graph, subject):
    from app.services.reference_parser import _literals, LABELS, local_name
    labels = _literals(graph,subject,LABELS)
    return labels[0][0] if labels else local_name(str(subject))


def inspect(graph):
    classes = sorted({s for kind in (OWL.Class,RDFS.Class) for s in graph.subjects(RDF.type,kind) if isinstance(s,URIRef)},key=str)
    properties = sorted({s for kind in (OWL.ObjectProperty,OWL.DatatypeProperty,RDF.Property) for s in graph.subjects(RDF.type,kind) if isinstance(s,URIRef)},key=str)
    vocab = sorted({s for s in graph.subjects(RDF.type,SKOS.Concept) if isinstance(s,URIRef)},key=str)
    shapes = set(graph.subjects(RDF.type,SH.NodeShape)) | set(graph.subjects(RDF.type,SH.PropertyShape)) | set(graph.subjects(SH.targetClass,None))
    shapes.update(graph.objects(None,SH.property))
    output = []
    for shape in sorted(shapes,key=str):
        parents = list(graph.subjects(SH.property,shape))
        targets = sorted({str(t) for s in [shape,*parents] for t in graph.objects(s,SH.targetClass) if isinstance(t,URIRef)})
        paths = list(graph.objects(shape,SH.path))
        unknown = []
        rules = []
        for predicate,obj in graph.predicate_objects(shape):
            name = str(predicate).removeprefix(str(SH))
            if str(predicate).startswith(str(SH)) and name not in SUPPORTED | ANNOTATIONS | {'path','targetClass','property'}:
                unknown.append(name)
            if name in SUPPORTED:
                expected = value(obj)
                if name=='in':
                    try:
                        members = list(graph.items(obj))
                        if len(members)>100 or any(isinstance(item,BNode) for item in members):
                            raise ValueError('Unsupported enumeration')
                        expected = [value(item) for item in members]
                    except ValueError:
                        unknown.append('in: liste invalide ou trop grande')
                        expected = []
                rules.append({'constraint':name,'expected':expected})
        if paths and (len(paths)!=1 or not isinstance(paths[0],URIRef)):
            unknown.append('chemin complexe')
        if not targets:
            unknown.append('cible de classe non determinee')
        if graph.value(shape,SH.deactivated) not in (None,Literal(False)):
            unknown.append('forme desactivee')
        output.append({'uri':str(shape),'label':label(graph,shape),'type':'PropertyShape' if paths else 'NodeShape',
            'target_classes':targets,'path':str(paths[0]) if len(paths)==1 and isinstance(paths[0],URIRef) else '',
            'rules':rules,'children':[str(child) for child in graph.objects(shape,SH.property)],
            'severity':str(graph.value(shape,SH.severity) or SH.Violation),
            'message':str(graph.value(shape,SH.message) or ''),'unsupported':sorted(set(unknown)),
            'status':'uninterpreted' if unknown else 'interpreted',
            'raw':[{ 'predicate':str(p), **value(o)} for p,o in graph.predicate_objects(shape)]})
    by_id = {shape['uri']:shape for shape in output}
    for shape in output:
        if any(by_id.get(child,{}).get('status')!='interpreted' for child in shape['children']):
            shape['status']='uninterpreted'
            shape['unsupported'].append('propriete enfant non interpretee')
    def entities(subjects):
        return [{'uri':str(s),'label':label(graph,s),'comment':str(graph.value(s,RDFS.comment) or ''),
                 'types':sorted(str(t) for t in graph.objects(s,RDF.type)),
                 'domains':sorted(str(t) for t in graph.objects(s,RDFS.domain)),
                 'ranges':sorted(str(t) for t in graph.objects(s,RDFS.range)),
                 'parents':sorted(str(t) for t in graph.objects(s,RDFS.subClassOf))} for s in subjects]
    missing = sum(not (list(graph.objects(s,RDFS.label)) or list(graph.objects(s,SKOS.prefLabel))) for s in set(classes+vocab))
    notes = []
    if missing:
        notes.append(f'{missing} terme(s) sans libelle explicite ; nom derive de l URI.')
    if any(s['unsupported'] for s in output):
        notes.append('Certaines formes ne sont pas interpretables dans le sous-ensemble SHACL du MVP.')
    kinds = {'owl':bool(classes or properties),'voc':bool(vocab),'shacl':bool(shapes)}
    enough = bool(classes or vocab) and missing < len(set(classes+vocab))
    namespaces = sorted({str(s).rsplit('#',1)[0]+'#' if '#' in str(s) else str(s).rsplit('/',1)[0]+'/' for s in [*classes,*vocab]})
    if len(namespaces)>1:
        notes.append('Plusieurs espaces de noms : aucun choix automatique de namespace pour les nouvelles URI.')
    confidence = 'insufficient' if not any(kinds.values()) else 'partial' if notes or not enough else 'sufficient'
    return {'version':2,'confidence':confidence,'rdf_read':True,'alignment_ready':enough,
        'rdf_export_ready':False,'rdf_export_reason':'Projection RDF cible non approuvee ; JSON et CSV de revue uniquement.',
        'layers':{kind:{'state':('partial' if notes else 'imported') if present else 'not_provided'} for kind,present in kinds.items()},
        'owl':{'classes':entities(classes),'properties':entities(properties)},
        'voc':{'term_count':len(vocab),'alias_count':sum(len(list(graph.objects(s,p))) for s in vocab for p in (SKOS.altLabel,SKOS.hiddenLabel))},
        'shacl':{'shapes':output,'interpreted':sum(s['status']=='interpreted' for s in output),'uninterpreted':sum(s['status']!='interpreted' for s in output)},
        'warnings':notes}
