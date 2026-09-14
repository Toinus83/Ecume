from fastapi import APIRouter, File, HTTPException, Query, UploadFile
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


@router.post('/mappings/search')
def search_mappings(request: MappingSearch):
    return call(echo.propose, request.repository_id, request.node_id)


@router.patch('/mappings/{mapping_id}')
def decide_mapping(mapping_id: str, request: MappingDecision):
    return call(echo.decide, mapping_id, request.match_type, request.status)


@router.post('/import')
def import_reference(file: UploadFile = File(...)):
    data = file.file.read(MAX_BYTES + 1)
    return call(references.import_reference, file.filename or '', data)


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
