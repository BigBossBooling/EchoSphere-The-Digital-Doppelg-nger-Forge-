# echosystem/phase2_feedback_engine/app/api/endpoints/feedback_endpoint.py
from fastapi import APIRouter, HTTPException, Body, Depends, FastAPI, Request
import logging
import uuid
import boto3
import json
from botocore.exceptions import ClientError

# Adjusted import paths to be relative to the `app` directory,
# assuming `phase2_feedback_engine` is the root for execution context (e.g., uvicorn app.main:app)
from app.config import settings
from app.models.feedback_models import FeedbackInput, FeedbackResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Dependency to get SQS client from app state
def get_sqs_client(request: Request) -> boto3.client:
    if not hasattr(request.app.state, 'sqs_client') or request.app.state.sqs_client is None:
        logger.error("SQS client not found in app.state or not initialized.")
        raise HTTPException(status_code=503, detail="SQS client not available.")
    return request.app.state.sqs_client

@router.post("/", response_model=FeedbackResponse, status_code=202) # Path relative to router prefix
async def submit_feedback_event(
    request: Request, # Added Request to access app.state
    feedback_data: FeedbackInput = Body(...)
    # sqs_client: boto3.client = Depends(get_sqs_client) # This is the cleaner way
):
    feedback_event_id = uuid.uuid4()
    logger.info(f"Received feedback (event_id: {feedback_event_id}) for persona: {feedback_data.persona_id}")

    sqs_client = get_sqs_client(request) # Directly call the dependency function for clarity here

    if not settings.FEEDBACK_EVENT_SQS_QUEUE_URL:
        logger.warning("FEEDBACK_EVENT_SQS_QUEUE_URL not configured. Feedback logged but not queued.")
        # This case should ideally be caught by health checks or SQS client initialization failing loudly.
        # If SQS is essential, a 503 might be more appropriate if the queue URL isn't set in prod.
        return FeedbackResponse(
            feedback_event_id=feedback_event_id,
            message="Feedback received (processing queue not configured).",
            received_feedback=feedback_data
        )

    payload_dict = feedback_data.model_dump()
    payload_dict["feedback_event_id"] = str(feedback_event_id)
    # Ensure all UUIDs in the payload are strings for JSON serialization
    for key, value in payload_dict.items():
        if isinstance(value, uuid.UUID):
            payload_dict[key] = str(value)
    message_body_with_id = json.dumps(payload_dict)

    try:
        # If SQS queue is FIFO, MessageGroupId is required.
        # Using persona_id as MessageGroupId ensures messages for the same persona are processed in order.
        # If not a FIFO queue, MessageGroupId can be omitted.
        # For this example, assuming it *could* be FIFO, so adding it.
        message_attributes = {}
        if settings.FEEDBACK_EVENT_SQS_QUEUE_URL.endswith(".fifo"):
            sqs_client.send_message(
                QueueUrl=settings.FEEDBACK_EVENT_SQS_QUEUE_URL,
                MessageBody=message_body_with_id,
                MessageGroupId=str(feedback_data.persona_id)
            )
        else:
            sqs_client.send_message(
                QueueUrl=settings.FEEDBACK_EVENT_SQS_QUEUE_URL,
                MessageBody=message_body_with_id
            )
        logger.info(f"Feedback event {feedback_event_id} successfully queued to SQS (PersonaID: {feedback_data.persona_id}).")
        msg = "Feedback received and queued for processing."
    except ClientError as e:
        logger.error(f"Failed to queue feedback event {feedback_event_id} to SQS: {e}", exc_info=True)
        error_message = "SQS error"
        if hasattr(e, 'response') and e.response and 'Error' in e.response and 'Message' in e.response['Error']:
            error_message = e.response['Error']['Message']
        raise HTTPException(status_code=500, detail=f"Failed to queue feedback. Error: {error_message}")
    except Exception as e: # Catch any other unexpected errors during SQS interaction
        logger.error(f"Unexpected error queuing feedback event {feedback_event_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unexpected error when trying to queue feedback.")

    return FeedbackResponse(
        feedback_event_id=feedback_event_id,
        message=msg,
        received_feedback=feedback_data
    )
