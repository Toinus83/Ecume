from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.database.db import init_db
from app.models.schemas import (
    AliasRequest,
    CardUpdate,
    KnowledgeEdgeIn,
    KnowledgeNodeIn,
    LLMSettings,
    ManualCardRequest,
    MergeCardRequest,
    MergeNodeRequest,
    ResetDatabaseRequest,
)
from app.services import (
    admin_service,
    analysis_service,
    card_service,
    changelog_service,
    document_service,
    export_service,
    graph_service,
    job_service,
)


app = FastAPI(title="ECUME API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


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
async def upload_document(file: UploadFile = File(...)) -> dict:
    try:
        return await document_service.save_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/documents")
def list_documents() -> list[dict]:
    return document_service.list_documents()


@app.get("/documents/{document_id}")
def get_document(document_id: str) -> dict:
    document = document_service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document introuvable.")
    return document


@app.post("/documents/{document_id}/analyze")
async def analyze_document(document_id: str) -> dict:
    try:
        return job_service.start_analysis_job(document_id)
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


@app.get("/graph")
def get_graph(
    filter: str = Query(default="all"),
    node_id: str | None = Query(default=None),
) -> dict:
    return graph_service.graph_payload(filter_mode=filter, node_id=node_id)


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
    return graph_service.create_edge(edge)


@app.delete("/graph/edges/{edge_id}")
def delete_edge(edge_id: str) -> dict:
    try:
        return graph_service.delete_edge(edge_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/graph/orphans")
def get_orphans() -> list[dict]:
    return graph_service.find_orphans()


@app.get("/export/json")
def export_json() -> FileResponse:
    return FileResponse(export_service.export_json(), filename="ecume_export.json")


@app.get("/export/jsonld")
def export_jsonld() -> FileResponse:
    return FileResponse(export_service.export_jsonld(), filename="ecume_export.jsonld")


@app.get("/export/csv")
def export_csv() -> FileResponse:
    return FileResponse(export_service.export_csv_bundle(), filename="ecume_csv_export.zip")


@app.get("/export/memgraph")
def export_memgraph() -> FileResponse:
    return FileResponse(
        export_service.export_memgraph_bundle(), filename="ecume_memgraph_export.zip"
    )


@app.get("/export/rdf-skos")
def export_rdf_skos() -> FileResponse:
    return FileResponse(
        export_service.export_rdf_skos_skeleton(), filename="ecume_skos_skeleton.ttl"
    )
