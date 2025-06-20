import logging
import boto3
import json
from botocore.exceptions import ClientError
from fastapi import HTTPException # To be consistent with s3_service error handling for internal errors

from .config import settings

logger = logging.getLogger(__name__)

# Initialize SQS client once.
# Similar to s3_service.py, in a full application, this might be managed
# via FastAPI lifespan events or dependency injection.
# AWS credentials and region should be configured in the environment.
try:
    sqs_client = boto3.client(
        "sqs",
        # region_name=settings.SQS_AWS_REGION # If SQS_AWS_REGION is added to settings
                                            # Often, region is picked up from AWS_DEFAULT_REGION env var
    )
except Exception as e:
    logger.error(f"Failed to initialize SQS client: {e}")
    sqs_client = None # Ensure it's None if initialization fails


async def send_event_to_maipp_queue(event_payload: dict) -> Optional[str]:
    """
    Sends an event message to the MAIPP SQS notification queue.

    Args:
        event_payload: A dictionary representing the event to send.
                       This will be serialized to JSON for the message body.

    Returns:
        The SQS Message ID if successful, None otherwise.

    Raises:
        HTTPException: If sending the message fails critically and needs to be reported
                       if called directly from an API request context.
                       For background tasks, this might just log and return None.
    """
    if not sqs_client:
        logger.error("SQS client is not initialized. Cannot send event.")
        # Depending on invocation context, raising HTTPException might not always be appropriate.
        # If this is called from a background task, it should handle failure without HTTP response.
        # For now, keeping consistent with potential direct API call usage.
        raise HTTPException(status_code=500, detail="Notification service (SQS) is not available.")

    if not settings.SQS_MAIPP_NOTIFICATION_QUEUE_URL:
        logger.error("SQS_MAIPP_NOTIFICATION_QUEUE_URL is not configured. Cannot send event.")
        raise HTTPException(status_code=500, detail="Notification queue (SQS) is not configured.")

    message_body = json.dumps(event_payload)

    try:
        logger.info(f"Sending message to SQS queue: {settings.SQS_MAIPP_NOTIFICATION_QUEUE_URL}. Body snippet: {message_body[:250]}...")

        # For standard queues. If FIFO, MessageGroupId would be needed.
        # MessageDeduplicationId is for content-based deduplication on FIFO queues.
        response = sqs_client.send_message(
            QueueUrl=settings.SQS_MAIPP_NOTIFICATION_QUEUE_URL,
            MessageBody=message_body,
            # Example MessageAttributes (optional):
            # MessageAttributes={
            #     'dataType': {
            #         'DataType': 'String',
            #         'StringValue': str(event_payload.get('dataType', 'unknown'))
            #     },
            #     'userID': {
            #         'DataType': 'String',
            #         'StringValue': str(event_payload.get('userID', 'unknown'))
            #     }
            # }
        )
        message_id = response.get('MessageId')
        logger.info(f"Message sent to SQS successfully. Message ID: {message_id}")
        return message_id
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        error_message = e.response.get("Error", {}).get("Message", "Unknown SQS client error")
        logger.error(f"SQS SendMessage ClientError to queue {settings.SQS_MAIPP_NOTIFICATION_QUEUE_URL}: [{error_code}] {error_message}", exc_info=True)
        # For consistency with how s3_service raises HTTPException, we do so here.
        # In a real-world scenario, if this is part of a larger background task after user response,
        # this error should be handled to ensure data consistency (e.g. retry, DLQ, mark package as notification_failed)
        # rather than failing an HTTP request that might have already succeeded from user's POV.
        raise HTTPException(status_code=500, detail=f"Could not send notification event via SQS.")
    except Exception as e:
        logger.error(f"Unexpected error sending message to SQS queue {settings.SQS_MAIPP_NOTIFICATION_QUEUE_URL}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred while sending notification event.")

```
