from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from app.models.schemas import BusinessCategory
from app.services import review_service as review

router = APIRouter(prefix='/review', tags=['review'])

class Decision(BaseModel):
    action: Literal['accept','ignore','update','attach','alias','new','dismiss','keep','qualify']
    label: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=6000)
    fields: dict[str,list[str]] | None = None
    target_id: str = ''
    field_key: Literal['motivation','objects','actors','actions','means','information','rules','result'] | None = None
    field_index: int = Field(default=0, ge=0, le=11)
    business_category: BusinessCategory | None = None
    preserve_identity: bool = False

@router.get('')
def workspace(document_id: str = ''):
    return review.workspace(document_id)

@router.get('/targets')
def targets(q: str = Query(default='',max_length=200)):
    if len(q.strip()) < 2:
        return []
    needle = review.graph._normalize(q)
    matches = [e for e in review.index() if needle in review.graph._normalize(' '.join([e['label'],*e['aliases']]))]
    return sorted(matches, key=lambda e: (review.graph._normalize(e['label']) != needle, e['label'].casefold()))[:8]

@router.post('/{mention_id}/decision')
def decide(mention_id: str, request: Decision):
    try:
        return review.decide(mention_id, request.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
