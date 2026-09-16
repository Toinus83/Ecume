"""Isolated, bounded SHACL Core validation; consumes JSON, never imported RDF code."""
import json
import sys
from rdflib import Graph, URIRef, BNode, Literal
from rdflib.collection import Collection
from rdflib.namespace import RDF, SH
from pyshacl import validate


def term(item):
    if item['kind']=='uri':
        return URIRef(item['value'])
    return Literal(item['value'],datatype=URIRef(item['datatype']) if item.get('datatype') else None,lang=item.get('language') or None)


def run(payload):
    data=Graph()
    for item in payload['items']:
        subject=URIRef(item['uri'])
        for cls in item['classes']:
            data.add((subject,RDF.type,URIRef(cls)))
        for path,values in item['properties'].items():
            for v in values:
                data.add((subject,URIRef(path),term(v)))
    results=[]
    for item in payload['items']:
        applicable=[s for s in payload['shapes'] if set(s['target_classes']) & set(item['classes'])]
        if not applicable:
            results.append({'element_id':item['id'],'status':'not_verifiable','message':'Aucune forme applicable avec un positionnement suffisamment explicite.'})
        for shape in applicable:
            base={'element_id':item['id'],'shape_uri':shape['uri'],'shape_label':shape['label'],'path':shape['path'],'severity':shape['severity']}
            if shape['status']!='interpreted' or shape['path'] in item['unknown_paths']:
                results.append({**base,'status':'not_verifiable','message':'Forme ou projection non interpretable : '+', '.join(shape['unsupported'] or ['propriete metier sans correspondance connue'])})
                continue
            if not shape['rules']:
                continue
            sg=Graph()
            s=BNode()
            sg.add((s,RDF.type,SH.PropertyShape if shape['path'] else SH.NodeShape))
            sg.add((s,SH.targetNode,URIRef(item['uri'])))
            if shape['path']:
                sg.add((s,SH.path,URIRef(shape['path'])))
            sg.add((s,SH.severity,URIRef(shape['severity'])))
            for rule in shape['rules']:
                expected=rule['expected']
                if rule['constraint']=='in':
                    head=BNode(); Collection(sg,head,[term(v) for v in expected]); obj=head
                else:
                    obj=term(expected)
                sg.add((s,SH[rule['constraint']],obj))
            conforms,report,_=validate(data,shacl_graph=sg,inference='none',advanced=False,js=False,do_owl_imports=False)
            violations=list(report.subjects(RDF.type,SH.ValidationResult))
            if conforms:
                results.append({**base,'status':'conformant','message':'Conforme aux contraintes simples verifiees sur la projection de travail.'})
            for violation in violations:
                component=report.value(violation,SH.sourceConstraintComponent)
                message={SH.MinCountConstraintComponent:'Information obligatoire manquante.',SH.MaxCountConstraintComponent:'Trop de valeurs pour cette information.',
                    SH.DatatypeConstraintComponent:'Type de valeur inattendu.',SH.ClassConstraintComponent:'La cible ne porte pas le type attendu.',
                    SH.InConstraintComponent:'Valeur absente de la liste autorisee.',SH.NodeKindConstraintComponent:'Nature de valeur inattendue.',
                    SH.PatternConstraintComponent:'Le format attendu n est pas respecte.'}.get(component,'Contrainte non satisfaite.')
                results.append({**base,'status':'to_complete' if component==SH.MinCountConstraintComponent else 'nonconformant',
                    'message':shape['message'] or message,'technical_message':str(report.value(violation,SH.resultMessage) or ''),
                    'constraint':str(component),'value':str(report.value(violation,SH.value) or '')})
    return results


if __name__=='__main__':
    try:
        print(json.dumps(run(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({'error':str(exc)[:500]}))
        sys.exit(1)
