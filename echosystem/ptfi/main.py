from fastapi import FastAPI, HTTPException, Query, Path, Body
import logging
import uvicorn
from contextlib import asynccontextmanager
import uuid
from typing import List, Optional, Dict, Any
import asyncpg
import json
from datetime import datetime, timezone

from .config import settings
from . import db_clients
from .db_clients import init_postgres_pool, close_postgres_pool, init_neo4j_driver, close_neo4j_driver, get_postgres_pool, get_neo4j_driver
from .models import (
    TraitCandidateDisplayModel, PaginatedTraitCandidateResponseModel, EvidenceSnippet,
    UserRefinedTraitActionModel, TraitActionRequestModel, TraitActionResponseModel, UpdatedTraitDetailsDisplay,
    CustomTraitRequestModel, CustomTraitResponseModel, # Added new models
    TraitCategoryEnum # Import TraitCategoryEnum for type hinting if needed by new endpoint
)
from .pkg_service_client_ptfi import (
    update_pkg_trait_status_and_properties,
    add_custom_trait_to_pkg,
    update_communication_style_in_pkg, # Import new function
    PKGServiceClientPTFIError
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting up {settings.APP_NAME} in {settings.APP_ENV} mode...")
    await init_postgres_pool()
    await init_neo4j_driver()
    yield
    logger.info(f"Shutting down {settings.APP_NAME}...")
    await close_postgres_pool()
    await close_neo4j_driver()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Persona Trait Finalization Interface (PTFI) for EchoSphere.",
    lifespan=lifespan
)

# Root and Health Check endpoints (omitted for brevity, assumed present and correct)
@app.get(settings.API_V1_STR + "/health", tags=["Health Check"])
async def health_check():
    pg_status = "not_initialized"
    if db_clients.pg_pool_ptfi and not db_clients.pg_pool_ptfi.is_closing():
        try:
            async with db_clients.pg_pool_ptfi.acquire() as conn: await conn.execute("SELECT 1")
            pg_status = "ok"
        except Exception: pg_status = "error"
    elif db_clients.pg_pool_ptfi: pg_status = "closing"
    neo4j_status = "not_initialized"
    if db_clients.neo4j_driver_ptfi:
        try: await db_clients.neo4j_driver_ptfi.verify_connectivity(); neo4j_status = "ok"
        except Exception: neo4j_status = "error"
    final_status = "ok"
    if pg_status == "error" or neo4j_status == "error": final_status = "error"
    elif pg_status == "not_initialized" or neo4j_status == "not_initialized": final_status = "degraded"
    logger.info(f"Health check: app_status={final_status}, postgres_status={pg_status}, neo4j_status={neo4j_status}")
    return {"status": final_status, "service": settings.APP_NAME, "environment": settings.APP_ENV,
            "log_level": settings.LOG_LEVEL, "postgres_status": pg_status, "neo4j_status": neo4j_status}

@app.get("/", tags=["Root"])
async def root(): return {"message": f"Welcome to {settings.APP_NAME}"}


@app.get(
    settings.API_V1_STR + "/users/{user_id}/persona/traits/candidates",
    response_model=PaginatedTraitCandidateResponseModel,
    tags=["PTFI - Trait Candidates"]
)
async def get_trait_candidates_for_user(
    user_id: uuid.UUID = Path(..., description="ID of the user"),
    status: Optional[List[str]] = Query(None, description="Filter by status(es)"),
    category: Optional[str] = Query(None, description="Filter by trait category"),
    sortBy: str = Query("creation_timestamp", description="Sort field"),
    sortOrder: str = Query("desc", description="Sort order: 'asc' or 'desc'"),
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100)
):
    # ... (implementation from Turn 93 - code omitted for brevity) ...
    pg_pool = await db_clients.get_postgres_pool(); offset = (page - 1) * limit
    allowed_sort = {"traitName": "trait_name", "traitCategory": "trait_category", "confidenceScore": "confidence_score",
                    "creationTimestamp": "creation_timestamp", "lastUpdatedTimestamp": "last_updated_timestamp", "status": "status"}
    db_sort_field = allowed_sort.get(sortBy, "creation_timestamp")
    sort_o = "DESC" if sortOrder.lower() == "desc" else "ASC"
    conds = ["user_id = $1"]; params: List[Any] = [user_id]; pc = 2
    if status:
        s_ph = ", ".join([f"${pc + i}" for i in range(len(status))]); conds.append(f"status IN ({s_ph})")
        params.extend(status); pc += len(status)
    if category: conds.append(f"trait_category = ${pc}"); params.append(category); pc += 1
    where = " AND ".join(conds)
    data_q = f"SELECT * FROM extracted_trait_candidates WHERE {where} ORDER BY {db_sort_field} {sort_o} LIMIT ${pc} OFFSET ${pc + 1};"
    params_data = params + [limit, offset]; count_q = f"SELECT COUNT(*) FROM extracted_trait_candidates WHERE {where};"
    try:
        async with pg_pool.acquire() as c:
            total = await c.fetchval(count_q, *params) or 0; db_rows = await c.fetch(data_q, *params_data)
        cands = [TraitCandidateDisplayModel.model_validate(dict(r)) for r in db_rows]
        return PaginatedTraitCandidateResponseModel(data=cands, total=total, page=page, limit=limit)
    except Exception as e: logger.error(f"PTFI: Error fetching trait candidates: {e}", exc_info=True); raise HTTPException(500, "Failed to fetch trait candidates.")


@app.post(
    settings.API_V1_STR + "/users/{user_id}/persona/traits/candidates/{candidate_id}/action",
    response_model=TraitActionResponseModel,
    tags=["PTFI - Trait Actions"]
)
async def handle_trait_candidate_action(
    user_id: uuid.UUID = Path(..., description="User ID"),
    candidate_id: uuid.UUID = Path(..., description="Candidate Trait ID"),
    action_request: TraitActionRequestModel = Body(...)
):
    # ... (implementation from Turn 96 - code omitted for brevity) ...
    logger.info(f"Action '{action_request.userDecision}' for candidate {candidate_id}, user {user_id}")
    pg_pool = await db_clients.get_postgres_pool(); neo_driver = await db_clients.get_neo4j_driver()
    orig_cand_data = None; updated_pg_status = None
    try:
        async with pg_pool.acquire() as c: orig_cand_db_row = await c.fetchrow("SELECT * FROM extracted_trait_candidates WHERE candidate_id = $1 AND user_id = $2", candidate_id, user_id)
        if not orig_cand_db_row: raise HTTPException(404, "Trait candidate not found.")
        orig_cand_data = TraitCandidateDisplayModel.model_validate(dict(orig_cand_db_row))
    except Exception as e: raise HTTPException(500, f"DB error fetching candidate: {str(e)}")

    log_entry: Optional[UserRefinedTraitActionModel] = None
    try:
        async with pg_pool.acquire() as c, c.transaction():
            status_map = {"confirmed_asis": "confirmed_by_user", "confirmed_modified": "confirmed_by_user", "rejected": "rejected_by_user"}
            new_pg_status = status_map.get(action_request.userDecision)
            if new_pg_status:
                await c.execute("UPDATE extracted_trait_candidates SET status = $1, last_updated_timestamp = $2 WHERE candidate_id = $3", new_pg_status, datetime.now(timezone.utc), candidate_id)
                updated_pg_status = new_pg_status
            mods = action_request.modifications
            log_entry = UserRefinedTraitActionModel(userID=user_id, traitID_in_pkg=candidate_id, originalCandidateID=candidate_id, userDecision=action_request.userDecision,
                refinedTraitName=mods.refinedTraitName if mods else None, refinedTraitDescription=mods.refinedTraitDescription if mods else None,
                refinedTraitCategory=mods.refinedTraitCategory if mods else None, userConfidenceRating=mods.userConfidenceRating if mods else None,
                customizationNotes=action_request.rejectionReason if action_request.userDecision == "rejected" else (mods.customizationNotes if mods else None))
            log_id = await c.fetchval("INSERT INTO user_refined_trait_actions (refinement_action_id, user_id, trait_id_in_pkg, original_candidate_id, user_decision, refined_trait_name, refined_trait_description, refined_trait_category, user_confidence_rating, customization_notes, linked_evidence_override, action_timestamp) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING refinement_action_id;",
                log_entry.refinementActionID, log_entry.userID, log_entry.traitID_in_pkg, log_entry.originalCandidateID, log_entry.userDecision, log_entry.refinedTraitName, log_entry.refinedTraitDescription, log_entry.refinedTraitCategory, log_entry.userConfidenceRating, log_entry.customizationNotes, json.dumps([e.model_dump(mode='json') for e in log_entry.linkedEvidenceOverride]) if log_entry.linkedEvidenceOverride else None, log_entry.actionTimestamp)
            if not log_id: raise Exception("Failed to log action.")
            log_entry.refinementActionID = log_id
    except Exception as e: raise HTTPException(500, f"Server error during PG update: {str(e)}")

    updated_pkg_trait: Optional[Dict[str,Any]] = None
    try:
        async with neo_driver.session() as s: # type: ignore
            updated_pkg_trait = await update_pkg_trait_status_and_properties(s, user_id, candidate_id, action_request.userDecision, action_request.modifications.model_dump(exclude_none=True) if action_request.modifications else None, orig_cand_data.model_dump())
        if not updated_pkg_trait: logger.error(f"PKG update failed for {candidate_id} but PG succeeded.")
    except Exception as e: logger.error(f"PTFI: PKG error for {candidate_id}: {e}", exc_info=True)

    updated_trait_disp = UpdatedTraitDetailsDisplay.model_validate(updated_pkg_trait) if updated_pkg_trait else None
    return TraitActionResponseModel(message=f"Action '{action_request.userDecision}' processed.", refinementActionID=log_entry.refinementActionID if log_entry else uuid.uuid4(), updatedTraitCandidateStatus=updated_pg_status, updatedTraitInPKG=updated_trait_disp)

@app.post(
    settings.API_V1_STR + "/users/{user_id}/persona/traits/custom",
    response_model=CustomTraitResponseModel, status_code=201, tags=["PTFI - Trait Actions"]
)
async def add_custom_user_trait(
    user_id: uuid.UUID = Path(..., description="User ID"),
    custom_trait_data: CustomTraitRequestModel = Body(...)
):
    # ... (implementation from Turn 99 - code omitted for brevity) ...
    logger.info(f"Adding custom trait '{custom_trait_data.traitName}' for user {user_id}")
    pg_pool = await db_clients.get_postgres_pool(); neo_driver = await db_clients.get_neo4j_driver()
    new_pkg_trait: Optional[Dict[str, Any]] = None
    try:
        async with neo_driver.session() as s: # type: ignore
            new_pkg_trait = await add_custom_trait_to_pkg(s, user_id, custom_trait_data.traitName, custom_trait_data.traitCategory, custom_trait_data.traitDescription, custom_trait_data.userConfidenceRating, custom_trait_data.supportingEvidence_userText)
        if not new_pkg_trait or not new_pkg_trait.get("traitID_in_pkg"): raise HTTPException(500, "Failed to create custom trait in PKG.")
    except Exception as e: logger.error(f"PTFI: PKG error creating custom trait: {e}", exc_info=True); raise HTTPException(500, "Error with PKG for custom trait.")

    new_trait_id = uuid.UUID(new_pkg_trait["traitID_in_pkg"])
    log_entry: Optional[UserRefinedTraitActionModel] = None
    try:
        async with pg_pool.acquire() as c, c.transaction():
            log_data = UserRefinedTraitActionModel(userID=user_id, traitID_in_pkg=new_trait_id, userDecision='user_added_confirmed', refinedTraitName=custom_trait_data.traitName, refinedTraitDescription=custom_trait_data.traitDescription, refinedTraitCategory=custom_trait_data.traitCategory, userConfidenceRating=custom_trait_data.userConfidenceRating, customizationNotes=custom_trait_data.customizationNotes,
                linkedEvidenceOverride=[EvidenceSnippet(type="user_provided_text", content=t, sourcePackageID=uuid.uuid5(uuid.NAMESPACE_DNS, f"user_input_{user_id}")) for t in custom_trait_data.supportingEvidence_userText if t.strip()] if custom_trait_data.supportingEvidence_userText else [])
            log_id = await c.fetchval("INSERT INTO user_refined_trait_actions (refinement_action_id, user_id, trait_id_in_pkg, user_decision, refined_trait_name, refined_trait_description, refined_trait_category, user_confidence_rating, customization_notes, linked_evidence_override, action_timestamp) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING refinement_action_id;",
                log_data.refinementActionID, log_data.userID, log_data.traitID_in_pkg, log_data.userDecision, log_data.refinedTraitName, log_data.refinedTraitDescription, log_data.refinedTraitCategory, log_data.userConfidenceRating, log_data.customizationNotes, json.dumps([e.model_dump(mode='json') for e in log_data.linkedEvidenceOverride]) if log_data.linkedEvidenceOverride else None, log_data.actionTimestamp)
            if not log_id: raise Exception("Failed to log custom trait action.")
            log_entry = log_data; log_entry.refinementActionID = log_id
    except Exception as e: logger.error(f"PTFI: DB error logging custom trait: {e}", exc_info=True); raise HTTPException(500, "Custom trait created in PKG, but failed to log action.")

    updated_trait_disp = UpdatedTraitDetailsDisplay.model_validate(new_pkg_trait) if new_pkg_trait else None
    return CustomTraitResponseModel(message=f"Custom trait '{custom_trait_data.traitName}' added.", newTrait=updated_trait_disp, refinementActionID=log_entry.refinementActionID if log_entry else uuid.uuid4())


# New Endpoint for Communication Styles
@app.put(
    settings.API_V1_STR + "/users/{user_id}/persona/communication-styles",
    response_model=Dict[str, Any], # Or a more specific response model
    tags=["PTFI - Communication Styles"]
)
async def update_user_communication_styles(
    user_id: uuid.UUID = Path(..., description="ID of the user whose communication styles are to be updated"),
    styles_update_request: Dict[str, Any] = Body(..., description="Object where keys are style dimension names (e.g., 'FormalityLevel', 'HumorUsage') and values are the new preferences.")
):
    # TODO: Implement actual authentication and ensure user_id from path matches token.
    logger.info(f"Updating communication styles for user_id: {user_id} with data: {styles_update_request}")

    if not styles_update_request:
        raise HTTPException(status_code=400, detail="No style updates provided.")

    neo_driver = await db_clients.get_neo4j_driver()
    updated_styles_summary = {}

    try:
        async with neo_driver.session() as session: # type: ignore
            for style_dimension, new_value in styles_update_request.items():
                # Basic validation for key/value can be added here
                if not isinstance(style_dimension, str) or not style_dimension.strip():
                    logger.warning(f"Skipping invalid style dimension name: {style_dimension}")
                    continue

                updated_style = await update_communication_style_in_pkg(
                    session=session,
                    user_id=user_id,
                    style_dimension_name=style_dimension,
                    new_value=new_value # Value can be string, number, bool, or simple dict/list (store as JSON string if complex)
                )
                if updated_style:
                    updated_styles_summary[style_dimension] = updated_style.get("styleValue", new_value)
                else:
                    # Log individual update failure but continue with others
                    logger.error(f"Failed to update communication style '{style_dimension}' for user {user_id} in PKG.")
                    updated_styles_summary[style_dimension] = {"error": "update_failed"}


        if not updated_styles_summary: # If all updates failed or no valid styles provided
             raise HTTPException(status_code=400, detail="No valid communication styles were processed or all updates failed.")

        return {"message": "Communication styles updated.", "updated_styles": updated_styles_summary}

    except PKGServiceClientPTFIError as e:
        logger.error(f"PTFI: PKG Service Client Error updating communication styles for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interacting with Persona Knowledge Graph for communication styles.")
    except Exception as e:
        logger.error(f"PTFI: Unexpected error updating communication styles for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Server error updating communication styles.")


if __name__ == "__main__":
    log_config_uvicorn = uvicorn.config.LOGGING_CONFIG
    log_config_uvicorn["formatters"]["access"]["fmt"] = '%(asctime)s - %(levelname)s - %(client_addr)s - "%(request_line)s" %(status_code)s'
    log_config_uvicorn["formatters"]["default"]["fmt"] = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    for logger_name_uvicorn in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        log_config_uvicorn["loggers"][logger_name_uvicorn]["level"] = settings.LOG_LEVEL.upper()
    logger.info(f"Starting Uvicorn server for {settings.APP_NAME} on http://0.0.0.0:8002 ...")
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True, log_config=log_config_uvicorn)
```
