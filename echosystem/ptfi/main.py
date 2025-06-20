from fastapi import FastAPI, HTTPException, Query, Path, Body
import logging
import uvicorn
from contextlib import asynccontextmanager
import uuid
from typing import List, Optional, Dict, Any
import asyncpg # For catching specific DB errors
import json # For serializing data for UserRefinedTraitActionModel if needed

from .config import settings
from . import db_clients
from .db_clients import init_postgres_pool, close_postgres_pool, init_neo4j_driver, close_neo4j_driver, get_postgres_pool, get_neo4j_driver
from .models import ( # Import all relevant models
    TraitCandidateDisplayModel, PaginatedTraitCandidateResponseModel, EvidenceSnippet,
    UserRefinedTraitActionModel, TraitActionRequestModel, TraitActionResponseModel, UpdatedTraitDetailsDisplay
)
# Import the new PKG service client function
from .pkg_service_client_ptfi import update_pkg_trait_status_and_properties, PKGServiceClientPTFIError

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

# ... (Root and Health Check endpoints as before) ...
@app.get(settings.API_V1_STR + "/health", tags=["Health Check"])
async def health_check():
    pg_status = "not_initialized"
    if db_clients.pg_pool_ptfi and not db_clients.pg_pool_ptfi.is_closing():
        try:
            async with db_clients.pg_pool_ptfi.acquire() as conn:
                await conn.execute("SELECT 1")
            pg_status = "ok"
        except Exception as e:
            logger.error(f"Health check: PostgreSQL connection error: {e}", exc_info=False)
            pg_status = "error"
    elif db_clients.pg_pool_ptfi and db_clients.pg_pool_ptfi.is_closing():
        pg_status = "closing"

    neo4j_status = "not_initialized"
    if db_clients.neo4j_driver_ptfi:
        try:
            await db_clients.neo4j_driver_ptfi.verify_connectivity()
            neo4j_status = "ok"
        except Exception as e:
            logger.error(f"Health check: Neo4j connection error: {e}", exc_info=False)
            neo4j_status = "error"

    final_status = "ok"
    if pg_status == "error" or neo4j_status == "error":
        final_status = "error"
    elif pg_status == "not_initialized" or neo4j_status == "not_initialized":
        final_status = "degraded"

    logger.info(f"Health check for {settings.APP_NAME}: app_status={final_status}, postgres_status={pg_status}, neo4j_status={neo4j_status}")
    return {
        "status": final_status, "service": settings.APP_NAME, "environment": settings.APP_ENV,
        "log_level": settings.LOG_LEVEL, "postgres_status": pg_status, "neo4j_status": neo4j_status
    }

@app.get("/", tags=["Root"])
async def root():
    logger.info(f"{settings.APP_NAME} root endpoint called")
    return {"message": f"Welcome to {settings.APP_NAME}"}


@app.get(
    settings.API_V1_STR + "/users/{user_id}/persona/traits/candidates",
    response_model=PaginatedTraitCandidateResponseModel,
    tags=["PTFI - Trait Candidates"]
)
async def get_trait_candidates_for_user(
    # ... (endpoint implementation as defined in previous step - Turn 93) ...
    user_id: uuid.UUID = Path(..., description="ID of the user whose trait candidates are to be fetched"),
    status: Optional[List[str]] = Query(None, description="Filter by status(es), e.g., 'candidate', 'awaiting_refinement'."),
    category: Optional[str] = Query(None, description="Filter by trait category", max_length=100),
    sortBy: str = Query("creation_timestamp", description="Field to sort by. Use DB column names e.g. 'creation_timestamp', 'confidence_score'."),
    sortOrder: str = Query("desc", description="Sort order: 'asc' or 'desc'"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Number of items per page")
):
    logger.info(f"Fetching trait candidates for user_id: {user_id}, status: {status}, category: {category}, page: {page}, limit: {limit}")
    pg_pool = await db_clients.get_postgres_pool()
    offset = (page - 1) * limit
    allowed_sort_fields = {
        "traitName": "trait_name", "traitCategory": "trait_category", "confidenceScore": "confidence_score",
        "creationTimestamp": "creation_timestamp", "lastUpdatedTimestamp": "last_updated_timestamp", "status": "status"
    }
    db_sort_field = allowed_sort_fields.get(sortBy, "creation_timestamp")
    sort_order_sql = "DESC" if sortOrder.lower() == "desc" else "ASC"
    query_conditions = ["user_id = $1"]
    query_params: List[Any] = [user_id]; param_counter = 2
    if status:
        status_placeholders = ", ".join([f"${param_counter + i}" for i in range(len(status))])
        query_conditions.append(f"status IN ({status_placeholders})")
        query_params.extend(status); param_counter += len(status)
    if category:
        query_conditions.append(f"trait_category = ${param_counter}"); query_params.append(category); param_counter += 1
    where_clause = " AND ".join(query_conditions)
    data_query = f"""
        SELECT candidate_id, user_id, trait_name, trait_description, trait_category,
               supporting_evidence_snippets, confidence_score, originating_models,
               associated_feature_set_ids, status, creation_timestamp, last_updated_timestamp
        FROM extracted_trait_candidates WHERE {where_clause}
        ORDER BY {db_sort_field} {sort_order_sql} LIMIT ${param_counter} OFFSET ${param_counter + 1};
    """
    query_params_data = query_params + [limit, offset]
    count_query = f"SELECT COUNT(*) FROM extracted_trait_candidates WHERE {where_clause};"
    try:
        async with pg_pool.acquire() as connection:
            total_count = await connection.fetchval(count_query, *query_params) or 0
            db_rows = await connection.fetch(data_query, *query_params_data)
        candidates = [TraitCandidateDisplayModel.model_validate(dict(row)) for row in db_rows]
        return PaginatedTraitCandidateResponseModel(data=candidates, total=total_count, page=page, limit=limit)
    except asyncpg.PostgresError as e:
        logger.error(f"PTFI: DB error fetching trait candidates for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch trait candidates.")
    except Exception as e:
        logger.error(f"PTFI: Unexpected error fetching trait candidates for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unexpected error fetching trait candidates.")


@app.post(
    settings.API_V1_STR + "/users/{user_id}/persona/traits/candidates/{candidate_id}/action",
    response_model=TraitActionResponseModel,
    tags=["PTFI - Trait Actions"]
)
async def handle_trait_candidate_action(
    user_id: uuid.UUID = Path(..., description="ID of the user performing the action"),
    candidate_id: uuid.UUID = Path(..., description="ID of the ExtractedTraitCandidate being actioned"),
    action_request: TraitActionRequestModel = Body(...)
):
    # TODO: Implement actual authentication and ensure user_id from path matches token.
    logger.info(f"Handling action '{action_request.userDecision}' for candidate_id: {candidate_id}, user_id: {user_id}")

    pg_pool = await db_clients.get_postgres_pool()
    neo_driver = await db_clients.get_neo4j_driver() # Get Neo4j driver

    original_candidate_db_row = None
    updated_candidate_status_pg = None

    # 1. Fetch the ExtractedTraitCandidate to verify ownership and get details
    try:
        async with pg_pool.acquire() as conn:
            original_candidate_db_row = await conn.fetchrow(
                "SELECT * FROM extracted_trait_candidates WHERE candidate_id = $1 AND user_id = $2",
                candidate_id, user_id
            )
        if not original_candidate_db_row:
            raise HTTPException(status_code=404, detail="Trait candidate not found or access denied.")

        # Convert row to our Pydantic model for easier use, though direct dict access is also fine
        original_candidate_data = TraitCandidateDisplayModel.model_validate(dict(original_candidate_db_row))

    except asyncpg.PostgresError as e:
        logger.error(f"PTFI: DB error fetching candidate {candidate_id} for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error accessing trait candidate.")

    # 2. Perform PostgreSQL updates (candidate status, log action) in a transaction
    user_refined_trait_log_entry: Optional[UserRefinedTraitActionModel] = None
    try:
        async with pg_pool.acquire() as conn:
            async with conn.transaction():
                # Update status of ExtractedTraitCandidate
                new_status_for_candidate_table = ""
                if action_request.userDecision == "confirmed_asis" or action_request.userDecision == "confirmed_modified":
                    new_status_for_candidate_table = "confirmed_by_user"
                elif action_request.userDecision == "rejected":
                    new_status_for_candidate_table = "rejected_by_user"

                if new_status_for_candidate_table:
                    updated_candidate_status_pg_result = await conn.execute(
                        "UPDATE extracted_trait_candidates SET status = $1, last_updated_timestamp = $2 WHERE candidate_id = $3 RETURNING status",
                        new_status_for_candidate_table, datetime.now(timezone.utc), candidate_id
                    )
                    if updated_candidate_status_pg_result: # Check if update happened
                        updated_candidate_status_pg = new_status_for_candidate_table # Store the new status
                    logger.info(f"Updated ExtractedTraitCandidate {candidate_id} status to '{new_status_for_candidate_table}'")

                # Create UserRefinedTraitActionModel log entry
                log_entry_data = UserRefinedTraitActionModel(
                    userID=user_id,
                    traitID_in_pkg=candidate_id, # Using candidate_id as the link to the PKG Trait node
                    originalCandidateID=candidate_id,
                    userDecision=action_request.userDecision,
                    refinedTraitName=action_request.modifications.refinedTraitName if action_request.modifications else None,
                    refinedTraitDescription=action_request.modifications.refinedTraitDescription if action_request.modifications else None,
                    refinedTraitCategory=action_request.modifications.refinedTraitCategory if action_request.modifications else None,
                    userConfidenceRating=action_request.modifications.userConfidenceRating if action_request.modifications else None,
                    customizationNotes=action_request.rejectionReason if action_request.userDecision == "rejected" else \
                                       (action_request.modifications.customizationNotes if action_request.modifications else None),
                    # linkedEvidenceOverride: # Not handled in this simplified request model
                )
                # Save the log entry (DDL for user_refined_trait_actions needs to exist)
                # This assumes your UserRefinedTraitActionModel maps directly to table columns
                # For JSONB fields, ensure data is properly formatted (e.g., model_dump_json)
                log_insert_query = """
                    INSERT INTO user_refined_trait_actions (
                        refinement_action_id, user_id, trait_id_in_pkg, original_candidate_id, user_decision,
                        refined_trait_name, refined_trait_description, refined_trait_category,
                        user_confidence_rating, customization_notes, linked_evidence_override, action_timestamp
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) RETURNING refinement_action_id;
                """
                log_action_id = await conn.fetchval(
                    log_insert_query,
                    log_entry_data.refinementActionID, log_entry_data.userID, log_entry_data.traitID_in_pkg,
                    log_entry_data.originalCandidateID, log_entry_data.userDecision, log_entry_data.refinedTraitName,
                    log_entry_data.refinedTraitDescription, log_entry_data.refinedTraitCategory, log_entry_data.userConfidenceRating,
                    log_entry_data.customizationNotes,
                    json.dumps([e.model_dump(mode='json') for e in log_entry_data.linkedEvidenceOverride]) if log_entry_data.linkedEvidenceOverride else None,
                    log_entry_data.actionTimestamp
                )
                if not log_action_id:
                    raise Exception("Failed to log user refinement action.")
                user_refined_trait_log_entry = log_entry_data # Use the Pydantic model instance
                user_refined_trait_log_entry.refinementActionID = log_action_id # Ensure it has the ID from DB

    except asyncpg.PostgresError as e:
        logger.error(f"PTFI: DB transaction error for candidate {candidate_id}, user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error during trait action processing.")
    except Exception as e: # Catch other errors like the one from log_action_id check
        logger.error(f"PTFI: Unexpected error in transaction for candidate {candidate_id}, user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Server error processing trait action.")


    # 3. PKG Interaction (outside PG transaction, as it's a separate system)
    updated_pkg_trait_details_dict: Optional[Dict[str,Any]] = None
    try:
        async with neo_driver.session() as session: # type: ignore
            modifications_dict = action_request.modifications.model_dump() if action_request.modifications else None
            original_candidate_dict = original_candidate_data.model_dump() # Pass original details for reference

            updated_pkg_trait_details_dict = await update_pkg_trait_status_and_properties(
                session=session,
                user_id=user_id,
                trait_id_in_pkg=candidate_id,
                user_decision=action_request.userDecision,
                modifications=modifications_dict,
                original_trait_details=original_candidate_dict
            )
        if not updated_pkg_trait_details_dict:
            # Log error but don't necessarily fail the whole operation if PG part succeeded.
            # This depends on desired overall transactional integrity. For now, we proceed.
            logger.error(f"PKG update failed for trait {candidate_id}, user {user_id}, but PG operations succeeded.")
            # Potentially queue a retry for PKG update or flag for admin.
    except PKGServiceClientPTFIError as e:
        logger.error(f"PTFI: PKG Service Client Error for trait {candidate_id}, user {user_id}: {e}", exc_info=True)
        # Similar to above, decide if this is fatal for the API response.
    except Exception as e: # Catch other errors from Neo4j driver like connectivity if not handled in client
        logger.error(f"PTFI: Neo4j driver error for trait {candidate_id}, user {user_id}: {e}", exc_info=True)


    # 4. Return response
    response_message = f"Trait candidate {candidate_id} action '{action_request.userDecision}' processed."
    updated_trait_display: Optional[UpdatedTraitDetailsDisplay] = None
    if updated_pkg_trait_details_dict:
        try:
            updated_trait_display = UpdatedTraitDetailsDisplay.model_validate(updated_pkg_trait_details_dict)
        except Exception as val_err:
            logger.error(f"Failed to validate PKG response into UpdatedTraitDetailsDisplay: {val_err}", exc_info=True)


    return TraitActionResponseModel(
        message=response_message,
        refinementActionID=user_refined_trait_log_entry.refinementActionID if user_refined_trait_log_entry else uuid.uuid4(), # Fallback if log failed
        updatedTraitCandidateStatus=updated_candidate_status_pg,
        updatedTraitInPKG=updated_trait_display
    )

# Placeholder for other API routers (e.g., for adding custom traits)
# app.include_router(trait_router, prefix=settings.API_V1_STR)

if __name__ == "__main__":
    # ... (Uvicorn run command as before) ...
    log_config_uvicorn = uvicorn.config.LOGGING_CONFIG
    log_config_uvicorn["formatters"]["access"]["fmt"] = '%(asctime)s - %(levelname)s - %(client_addr)s - "%(request_line)s" %(status_code)s'
    log_config_uvicorn["formatters"]["default"]["fmt"] = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    for logger_name_uvicorn in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        log_config_uvicorn["loggers"][logger_name_uvicorn]["level"] = settings.LOG_LEVEL.upper()
    logger.info(f"Starting Uvicorn server for {settings.APP_NAME} on http://0.0.0.0:8002 ...")
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True, log_config=log_config_uvicorn)

```
