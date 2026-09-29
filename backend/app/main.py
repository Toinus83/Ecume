from __future__ import annotations

import os

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.database.db import init_db
from app.models.schemas import (
    AliasRequest,
    CardUpdate,
    KnowledgeEdgeIn,
    KnowledgeNodeIn,
    LLMSettings,
    RDFSettings,
    ManualCardRequest,
    MergeCardRequest,
    MergeNodeRequest,
    ResetDatabaseRequest,
    SuggestionDecision,
    ImportSettings,
    DeleteDocumentRequest,
    DocumentDomainDecision,
    ValidationSettings,
    OrphanUpdate,
    ValidationApplyRequest,
    SuggestionRepair,
    SuggestionTargetCreate,
)
from app.services import (
    admin_service,
    analysis_service,
    card_service,
    coherence_service,
    changelog_service,
    document_service,
    export_service,
    graph_service,
    job_service,
    validation_service,
    orphan_service,
)


app = FastAPI(title="ECUME API", version="0.1.0")

from app.routers.references import router as references_router
app.include_router(references_router)
from app.routers.review import router as review_router
app.include_router(review_router)

cors_origins = [
    value.strip()
    for value in os.getenv(
        "ECUME_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if value.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"^http://(?:localhost|127\.0\.0\.1):517\d$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()
    job_service.recover_interrupted_jobs()
    document_service.recover_pending_purges()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/dashboard")
def dashboard() -> dict[str, int]:
    return graph_service.dashboard_stats()


@app.get("/changes")
def recent_changes(limit: int = Query(default=30, ge=1, le=200)) -> list[dict]:
    return changelog_service.recent_changes(limit)


@app.get("/admin/llm")
def get_llm_settings() -> dict:
    return admin_service.get_llm_settings()


@app.put("/admin/llm")
def update_llm_settings(settings: LLMSettings) -> dict:
    return admin_service.update_llm_settings(settings)


@app.post("/admin/llm/test")
async def test_llm_settings() -> dict:
    try:
        return await admin_service.test_llm_settings()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Test LLM impossible : {exc}") from exc


@app.get("/admin/rdf")
def get_rdf_settings() -> dict:
    return admin_service.get_rdf_settings()


@app.put("/admin/rdf")
def update_rdf_settings(settings: RDFSettings) -> dict:
    return admin_service.update_rdf_settings(settings)


@app.post("/admin/rdf/test/{action}")
async def test_rdf_settings(action: str) -> dict:
    try:
        return await admin_service.test_rdf_settings(action)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Test RDF impossible : {exc}") from exc


@app.post("/admin/rdf/echo/check/{check_name}")
def check_echo_profile(check_name: str) -> dict:
    try:
        return admin_service.check_echo_profile(check_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/admin/rdf/ontocast/test")
async def test_ontocast() -> dict:
    return await admin_service.test_ontocast()


@app.post("/admin/database/reset")
def reset_database(request: ResetDatabaseRequest) -> dict:
    try:
        return admin_service.reset_database(
            confirmation=request.confirmation,
            delete_uploads=request.delete_uploads,
            delete_exports=request.delete_exports,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), upload_id: str = Query(default="", max_length=80)) -> dict:
    try:
        document = await document_service.save_upload(file, upload_id)
        return document_service.document_summary(document["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/imports/{upload_id}/cancel")
def cancel_import(upload_id: str) -> dict:
    try:
        return document_service.request_import_cancel(upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/documents")
def list_documents() -> list[dict]:
    return document_service.list_documents()


@app.get("/imports/settings")
def import_settings() -> dict:
    return document_service.get_import_settings()


@app.get("/validation/settings")
def validation_settings() -> dict:
    return validation_service.get_settings()


@app.put("/validation/settings")
def save_validation_settings(settings: ValidationSettings) -> dict:
    return validation_service.save_settings(settings)


@app.post("/validation/apply")
def apply_validation(request: ValidationApplyRequest) -> dict:
    return validation_service.apply_to_undecided(request.card_ids, request.settings.model_dump())


@app.put("/imports/settings")
def save_import_settings(settings: ImportSettings) -> dict:
    return document_service.save_import_settings(settings.retention_policy)


@app.put("/documents/{document_id}/retention")
def document_retention(document_id: str, settings: ImportSettings) -> dict:
    try:
        return document_service.set_retention_policy(document_id, settings.retention_policy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/documents/{document_id}/domain")
def document_domain(document_id: str, decision: DocumentDomainDecision) -> dict:
    try:
        return document_service.confirm_domain(document_id, **decision.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/documents/{document_id}/purge")
def purge_document(document_id: str) -> dict:
    try:
        return document_service.purge_source(document_id)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Purge non terminee : {exc}") from exc


@app.post("/documents/{document_id}/source")
async def restore_document_source(document_id: str, file: UploadFile = File(...)) -> dict:
    try:
        return await run_in_threadpool(document_service.restore_source, document_id, file)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/documents/{document_id}")
def delete_document(document_id: str, request: DeleteDocumentRequest) -> dict:
    try:
        return document_service.delete_document(document_id, **request.model_dump())
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/documents/{document_id}")
def get_document(document_id: str) -> dict:
    document = document_service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document introuvable.")
    return document


@app.post("/documents/{document_id}/analyze")
async def analyze_document(document_id: str, settings: ValidationSettings | None = None, extraction_mode: str = Query(default="sober", pattern="^(sober|balanced|exhaustive)$"), fill_mode: str | None = Query(default=None, pattern="^(manual|prefilled)$")) -> dict:
    try:
        return job_service.start_analysis_job(document_id, settings.model_dump() if settings else None, extraction_mode=extraction_mode, fill_mode=fill_mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/jobs")
def list_jobs(limit: int = Query(default=20, ge=1, le=100)) -> list[dict]:
    return job_service.list_jobs(limit)


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job introuvable.")
    return job


@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    try:
        return job_service.cancel_analysis_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/cards")
def list_cards() -> list[dict]:
    return analysis_service.list_cards()


@app.get("/cards/{card_id}")
def get_card(card_id: str) -> dict:
    card = analysis_service.get_card(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Carte introuvable.")
    return card


@app.post("/cards")
def create_manual_card(request: ManualCardRequest) -> dict:
    try:
        return analysis_service.create_manual_card(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/cards/{card_id}/accept")
def accept_card(card_id: str, orphan: bool = Query(default=False)) -> dict:
    try:
        return card_service.accept_card(card_id, orphan=orphan)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/cards/{card_id}/update")
def update_card(card_id: str, update: CardUpdate) -> dict:
    try:
        return card_service.update_card(card_id, update)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/cards/{card_id}/merge")
def merge_card(card_id: str, request: MergeCardRequest) -> dict:
    try:
        return card_service.merge_card(card_id, request.target_card_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/cards/{card_id}")
def delete_card(card_id: str) -> dict:
    try:
        return card_service.delete_card(card_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/cards/{card_id}/concepts/{node_id}")
def detach_concept(card_id: str, node_id: str) -> dict:
    try:
        return card_service.detach_concept(card_id, node_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/cards/{card_id}/suggestions/{suggestion_id}/decision")
def decide_suggestion(card_id: str, suggestion_id: str, decision: SuggestionDecision) -> dict:
    try:
        return coherence_service.decide_suggestion(card_id, suggestion_id, decision.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/cards/{card_id}/suggestions/{suggestion_id}/repair")
def repair_suggestion(card_id: str, suggestion_id: str, correction: SuggestionRepair) -> dict:
    try:
        return coherence_service.repair_suggestion(card_id, suggestion_id, correction)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/graph")
def get_graph(
    filter: str = Query(default="all"),
    node_id: str | None = Query(default=None),
    scope: str = Query(default="validated", pattern="^(validated|all)$"),
) -> dict:
    return graph_service.graph_payload(filter_mode=filter, node_id=node_id, scope=scope)


@app.post("/cards/{card_id}/suggestions/{suggestion_id}/target")
def create_suggestion_target(card_id: str, suggestion_id: str, request: SuggestionTargetCreate) -> dict:
    try:
        return coherence_service.create_suggestion_target(card_id, suggestion_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/graph/nodes")
def create_node(node: KnowledgeNodeIn) -> dict:
    return graph_service.create_node(node)


@app.delete("/graph/nodes/{node_id}")
def delete_node(node_id: str) -> dict:
    try:
        return graph_service.delete_node(node_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/graph/nodes/similar")
def find_similar_nodes(label: str, type: str | None = Query(default=None)) -> list[dict]:
    return graph_service.find_similar_nodes(label, type)


@app.post("/graph/nodes/{node_id}/aliases")
def add_alias(node_id: str, request: AliasRequest) -> dict:
    try:
        return graph_service.add_alias(node_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/graph/nodes/{node_id}/merge")
def merge_node(node_id: str, request: MergeNodeRequest) -> dict:
    try:
        return graph_service.merge_nodes(node_id, request.target_node_id, request.relation_note)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/graph/edges")
def create_edge(edge: KnowledgeEdgeIn) -> dict:
    from app.database.db import transaction
    try:
        with transaction():
            card_id = edge.metadata.get("card_id")
            if card_id:
                card = card_service.require_card(card_id)
                if edge.source_node_id not in card_service._all_card_node_ids(card):
                    raise ValueError("La source du lien doit appartenir a la carte.")
            result = graph_service.create_edge(edge)
            coherence_service.refresh_states()
            return next(item for item in graph_service.list_edges() if item["id"] == result["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/graph/edges/{edge_id}")
def delete_edge(edge_id: str) -> dict:
    try:
        return graph_service.delete_edge(edge_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/graph/orphans")
def get_orphans() -> list[dict]:
    return graph_service.find_orphans()


@app.post("/graph/nodes/{node_id}/orphan")
def update_orphan(node_id: str, request: OrphanUpdate) -> dict:
    try:
        return orphan_service.update_orphan(node_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/cards/{card_id}/concept-proposals/{proposal_id}/{action}")
def decide_concept_proposal(card_id: str, proposal_id: str, action: str) -> dict:
    from app.services.salience_service import decide_concept
    try:
        return decide_concept(card_id, proposal_id, action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/graph/targets")
def search_targets(q: str = Query(default="", max_length=200), source_id: str = "", document_id: str = "",
                   scope: str = Query(default="all", pattern="^(all|validated|document|close)$"),
                   node_type: str = Query(default="", pattern="^(|effect|object|action|condition|task|theme)$"),
                   offset: int = Query(default=0, ge=0, le=100000), limit: int = Query(default=8, ge=1, le=8)) -> dict:
    return graph_service.search_targets(q, source_id=source_id, document_id=document_id, scope=scope, node_type=node_type, offset=offset, limit=limit)


@app.get("/graph/search")
def search_graph(q: str = Query(default="", max_length=200)) -> list[dict]:
    return graph_service.search_validated_graph(q)


@app.get("/export/json")
def export_json(scope: str = Query(default="validated", pattern="^(validated|all)$")) -> FileResponse:
    return FileResponse(export_service.export_json(scope), filename="ecume_knowledge.json")


@app.get("/export/jsonld")
def export_jsonld(scope: str = Query(default="validated", pattern="^(validated|all)$")) -> FileResponse:
    return FileResponse(export_service.export_jsonld(scope), filename="ecume_export.jsonld")


@app.get("/export/csv")
def export_csv(scope: str = Query(default="validated", pattern="^(validated|all)$")) -> FileResponse:
    return FileResponse(export_service.export_csv_bundle(scope), filename="ecume_csv_export.zip")


@app.get("/export/memgraph")
def export_memgraph(scope: str = Query(default="validated", pattern="^(validated|all)$")) -> FileResponse:
    return FileResponse(
        export_service.export_memgraph_bundle(scope), filename="ecume_memgraph_export.zip"
    )


@app.get("/export/ttl")
@app.get("/export/rdf-skos")
def export_rdf_skos(scope: str = Query(default="validated", pattern="^(validated|all)$")) -> FileResponse:
    return FileResponse(
        export_service.export_turtle(scope), filename="ecume_export.ttl", media_type="text/turtle"
    )


@app.get("/export/archimate-json")
def export_archimate_json() -> FileResponse:
    return FileResponse(
        export_service.export_archimate_candidates_json(),
        filename="ecume_archimate_candidates.json",
    )


@app.get('/export/ontology-draft')
def export_ontology_draft() -> FileResponse:
    from app.services.ontology_draft import export_bundle
    return FileResponse(export_bundle(), filename='ecume_ontology_review.zip')
