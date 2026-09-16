from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse

from app.services import reference_service as references
from app.services import echo_mapping_service as echo
from app.services import echo_export_service as echo_exports
from app.services.reference_parser import MAX_BYTES

router = APIRouter(prefix='/references', tags=['references'])


class Activation(BaseModel):
    active: bool


class Removal(BaseModel):
    confirmation: str


class MappingSearch(BaseModel):
    repository_id: str = ''
    node_id: str = ''


class MappingDecision(BaseModel):
    match_type: str
    status: str


class RuleCorrection(BaseModel):
    label: str
    description: str = ''
    value: str = ''
    unit: str = ''
    condition: str = ''
    exception: str = ''


def call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('')
def list_references():
    return references.list_repositories()


@router.get('/mappings')
def mappings(node_id: str = '', repository_id: str = ''):
    return echo.mappings(node_id, repository_id)


@router.get('/cards/{card_id}/workshop')
def card_workshop(card_id: str):
    from app.services.card_service import require_card
    call(require_card,card_id)
    result=[]
    for repository in references.list_repositories():
        if repository['active']:
            payload=call(echo_exports.build_package,repository['id'],card_id)
            result.append({'repository_id':repository['id'],'name':repository['name'],
                'recognized':payload['recognized_existing_echo_elements'],'new_concepts':payload['proposed_new_concepts'],
                'rules':payload['ecume_rules'],'checks':payload['shacl_checks'],'report':payload['control_report']})
    return result


@router.patch('/cards/{card_id}/rules/{rule_id}')
def correct_rule(card_id: str, rule_id: str, request: RuleCorrection):
    from app.services.business_rule_service import update
    return call(update,card_id,rule_id,request.model_dump())


@router.get('/{repository_id}/report')
def control_report(repository_id: str):
    return call(echo_exports.build_package,repository_id)['control_report']


@router.post('/mappings/search')
def search_mappings(request: MappingSearch):
    return call(echo.propose, request.repository_id, request.node_id)


@router.patch('/mappings/{mapping_id}')
def decide_mapping(mapping_id: str, request: MappingDecision):
    return call(echo.decide, mapping_id, request.match_type, request.status)


@router.post('/import')
def import_reference(file: UploadFile = File(...), repository_id: str = Form(''), layer: str = Form('auto')):
    data = file.file.read(MAX_BYTES + 1)
    return call(references.import_reference, file.filename or '', data, repository_id, layer)


@router.get('/{repository_id}/terms')
def terms(repository_id: str, q: str = Query(default='', max_length=200), offset: int = Query(default=0, ge=0)):
    return call(references.terms, repository_id, q, offset)


@router.get('/{repository_id}/export/{format_name}')
def export_echo(repository_id: str, format_name: str):
    if format_name not in {'json','csv'}:
        raise HTTPException(status_code=400,detail='Formats disponibles : JSON et CSV de controle.')
    path = call(echo_exports.export_json if format_name=='json' else echo_exports.export_csv,repository_id)
    return FileResponse(path,filename='echo_enrichment.json' if format_name=='json' else 'echo_review.zip',
                        media_type='application/json' if format_name=='json' else 'application/zip')


@router.patch('/{repository_id}')
def activate(repository_id: str, request: Activation):
    return call(references.set_active, repository_id, request.active)


@router.delete('/{repository_id}')
def delete(repository_id: str, request: Removal):
    return call(references.delete_repository, repository_id, request.confirmation)
