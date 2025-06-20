# echosystem/phase2_feedback_engine/app/services/feedback_processor_service.py
import logging
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Any # Added Any for db_client type hint
import asyncpg

from app.config import settings
from app.models.feedback_models import FeedbackEventModel
# Import services and models for behavioral model updates
from app.services.behavioral_model_updater_service import (
    get_active_behavioral_model,
    apply_feedback_to_behavioral_model,
    save_behavioral_model
)
# Note: The db_client for behavioral models (DynamoDB/MongoDB) is not handled here yet.
# This initial integration will use placeholders for db_client.
# A proper implementation would require initializing and passing these clients.

logger = logging.getLogger(__name__)

async def update_feedback_event_status(
    db_pool: asyncpg.pool.Pool,
    feedback_event_id: uuid.UUID,
    status: str, # Should be Literal from FeedbackEventModel.processing_status
    error_message: Optional[str] = None
):
    """Updates the processing status and error message of a feedback event in the DB."""
    query = """
        UPDATE feedback_events
        SET processing_status = $1,
            processed_timestamp = CASE WHEN $1 = 'processed' THEN $2 ELSE processed_timestamp END,
            error_message = $3
        WHERE feedback_event_id = $4;
    """
    try:
        processed_ts = datetime.now(timezone.utc) if status == "processed" else None
        async with db_pool.acquire() as connection:
            await connection.execute(query, status, processed_ts, error_message, feedback_event_id)
        logger.info(f"Updated status for feedback_event_id {feedback_event_id} to {status}.")
    except Exception as e:
        logger.error(f"Failed to update status for feedback_event_id {feedback_event_id}: {e}", exc_info=True)


async def store_initial_feedback_event( # Renamed to be more specific
    db_pool: asyncpg.pool.Pool,
    feedback_event: FeedbackEventModel # Expects status to be 'pending' initially
) -> bool:
    """Stores the initial FeedbackEventModel (status 'pending') into the PostgreSQL database."""
    if not db_pool:
        logger.error("Feedback PostgreSQL pool not available. Cannot store feedback event.")
        return False

    # Make sure initial status is pending
    feedback_event.processing_status = "pending"
    feedback_event.processed_timestamp = None
    feedback_event.error_message = None

    query = """
        INSERT INTO feedback_events (
            feedback_event_id, persona_id, interaction_id, output_id,
            feedback_type, user_provided_text, user_rating_value, feedback_context,
            received_timestamp, processing_status, processed_timestamp, error_message
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (feedback_event_id) DO NOTHING;
        -- DO NOTHING: if message redelivered and already inserted, don't change it here.
        -- Status updates will handle reprocessing if needed.
    """
    try:
        feedback_context_json = json.dumps(feedback_event.feedback_context) if feedback_event.feedback_context else None
        async with db_pool.acquire() as connection:
            result = await connection.execute(
                query,
                feedback_event.feedback_event_id,
                feedback_event.persona_id,
                feedback_event.interaction_id,
                feedback_event.output_id,
                feedback_event.feedback_type,
                feedback_event.user_provided_text,
                feedback_event.user_rating_value,
                feedback_context_json,
                feedback_event.received_timestamp,
                feedback_event.processing_status, # Should be 'pending'
                feedback_event.processed_timestamp, # Should be None
                feedback_event.error_message # Should be None
            )
            # Check if insert actually happened (1 row affected) or if ON CONFLICT did nothing.
            # For "DO NOTHING", result is "INSERT 0 0" if conflict, "INSERT 0 1" if new.
            if result == "INSERT 0 1":
                 logger.info(f"Successfully stored initial feedback event: {feedback_event.feedback_event_id}")
            else: # Could be "INSERT 0 0" (conflict) or other
                 logger.info(f"Initial feedback event {feedback_event.feedback_event_id} already exists or no insert. Result: {result}")
            return True # Return True even if it already existed, as it's "stored"
    except Exception as e:
        logger.error(f"Error storing initial feedback event {feedback_event.feedback_event_id}: {e}", exc_info=True)
        return False

async def process_sqs_feedback_message(message_body: str, pg_db_pool: asyncpg.pool.Pool, model_db_client: Any = None) -> bool:
    """
    Processes a single feedback message from SQS:
    1. Deserializes and validates into FeedbackEventModel.
    2. Stores it initially in PostgreSQL DB with 'pending' status.
    3. Attempts to apply feedback to the behavioral model.
    4. Updates the FeedbackEventModel in DB with 'processed' or 'error' status.
    Returns True if message processing (including DB ops) is complete (delete from SQS),
    False if a transient error occurred (e.g., DB pool unavailable for initial store - retry message via SQS).
    """
    feedback_event_id_for_logging = "unknown"
    try:
        payload = json.loads(message_body)
        feedback_event_id_for_logging = payload.get("feedback_event_id", "unknown")
        logger.debug(f"Processing SQS feedback payload for event_id: {feedback_event_id_for_logging}")

        feedback_event = FeedbackEventModel(**payload)
        feedback_event_id_for_logging = feedback_event.feedback_event_id # Now it's a UUID

        # 1. Store initial "pending" event
        if not await store_initial_feedback_event(pg_db_pool, feedback_event):
            logger.error(f"Failed to initially store feedback event {feedback_event_id_for_logging}. Message will be retried by SQS.")
            return False # Critical failure to store, SQS should retry

        # 2. Attempt to apply feedback to behavioral model
        try:
            current_behavioral_model = await get_active_behavioral_model(feedback_event.persona_id, model_db_client)

            if not current_behavioral_model:
                logger.warning(f"No active behavioral model found for persona {feedback_event.persona_id}. Feedback {feedback_event_id_for_logging} cannot be applied.")
                await update_feedback_event_status(pg_db_pool, feedback_event.feedback_event_id, "error", "No active behavioral model found")
                return True # Processed (with error), delete from SQS

            updated_model = await apply_feedback_to_behavioral_model(feedback_event, current_behavioral_model)

            if updated_model:
                # Set the new model to active before saving. The save function should handle deactivating the old one.
                updated_model.is_active_model = True
                if await save_behavioral_model(updated_model, model_db_client):
                    logger.info(f"Successfully applied feedback and saved updated behavioral model {updated_model.model_version_id} for feedback {feedback_event_id_for_logging}.")
                    await update_feedback_event_status(pg_db_pool, feedback_event.feedback_event_id, "processed")
                else:
                    logger.error(f"Failed to save updated behavioral model for feedback {feedback_event_id_for_logging}.")
                    await update_feedback_event_status(pg_db_pool, feedback_event.feedback_event_id, "error", "Failed to save updated behavioral model")
            else:
                logger.info(f"Feedback {feedback_event_id_for_logging} did not result in behavioral model changes.")
                await update_feedback_event_status(pg_db_pool, feedback_event.feedback_event_id, "processed", "No model changes applied")

            return True # Processed (successfully or with non-retryable error), delete from SQS

        except Exception as e_model_update: # Catch errors during model update phase
            logger.error(f"Error applying feedback or saving behavioral model for event {feedback_event_id_for_logging}: {e_model_update}", exc_info=True)
            await update_feedback_event_status(pg_db_pool, feedback_event.feedback_event_id, "error", f"Model update failure: {str(e_model_update)[:100]}")
            return True # Processed (with error), delete from SQS

    except json.JSONDecodeError:
        logger.error(f"Malformed SQS message (JSONDecodeError) for event_id: {feedback_event_id_for_logging}. Body: {message_body[:500]}...", exc_info=True)
        return True # Malformed, delete from SQS
    except Exception as e_main: # Catches Pydantic validation errors, other unexpected errors
        logger.error(f"Generic error processing SQS message for event_id: {feedback_event_id_for_logging}: {e_main}", exc_info=True)
        # If feedback_event object exists, try to update its status to error in DB before exiting.
        if 'feedback_event' in locals() and isinstance(locals()['feedback_event'], FeedbackEventModel):
            await update_feedback_event_status(pg_db_pool, locals()['feedback_event'].feedback_event_id, "error", f"Generic processing error: {str(e_main)[:100]}")
        return True # Error in processing, delete from SQS (assume non-retryable by default for data issues)
