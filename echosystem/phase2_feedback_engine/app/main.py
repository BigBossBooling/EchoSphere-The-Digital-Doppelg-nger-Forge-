# echosystem/phase2_feedback_engine/app/main.py
import asyncio # For asyncio.create_task and CancelledError
import logging
import uvicorn
from contextlib import asynccontextmanager
from typing import Optional # For Optional type hint

import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
import asyncpg # For PostgreSQL pool

from fastapi import FastAPI, Request

from app.config import settings
from app.api.api_v1_router import api_router
from app.services import feedback_processor_service # Import the service

logger = logging.getLogger(__name__)

# Global variable for the SQS consumer task, to manage its lifecycle
sqs_consumer_task: Optional[asyncio.Task] = None

async def run_sqs_feedback_consumer(app: FastAPI):
    """Continuously polls SQS for feedback messages and processes them."""
    if not app.state.sqs_client:
        logger.warning("SQS client not available, SQS consumer will not start.")
        return
    if not app.state.pg_pool_feedback:
        logger.warning("Feedback DB pool not available, SQS consumer will not start.")
        return
    if not settings.FEEDBACK_EVENT_SQS_QUEUE_URL: # Should be caught by SQS client init, but double check
        logger.warning("SQS Queue URL not configured, SQS consumer will not start.")
        return

    logger.info(f"Starting SQS consumer for queue: {settings.FEEDBACK_EVENT_SQS_QUEUE_URL}")
    while True:
        try:
            messages = await asyncio.to_thread( # Run blocking SQS call in a separate thread
                app.state.sqs_client.receive_message,
                QueueUrl=settings.FEEDBACK_EVENT_SQS_QUEUE_URL,
                MaxNumberOfMessages=settings.SQS_MAX_MESSAGES,
                WaitTimeSeconds=settings.SQS_POLL_WAIT_TIME,
                VisibilityTimeout=settings.SQS_VISIBILITY_TIMEOUT,
                AttributeNames=['All'], # Or specify needed attributes
                MessageAttributeNames=['All']
            )

            if 'Messages' in messages:
                logger.info(f"Received {len(messages['Messages'])} messages from SQS.")
                for msg in messages['Messages']:
                    receipt_handle = msg['ReceiptHandle']
                    message_id = msg['MessageId']
                    logger.debug(f"Processing message ID: {message_id}, Body: {msg['Body'][:200]}...")

                    # Process the message using the feedback_processor_service
                    # Pass the pg_pool from app.state
                    processed_successfully = await feedback_processor_service.process_sqs_feedback_message(
                        msg['Body'],
                        app.state.pg_pool_feedback
                    )

                    if processed_successfully:
                        logger.info(f"Message {message_id} processed successfully. Deleting from SQS.")
                        try:
                            await asyncio.to_thread(
                                app.state.sqs_client.delete_message,
                                QueueUrl=settings.FEEDBACK_EVENT_SQS_QUEUE_URL,
                                ReceiptHandle=receipt_handle
                            )
                        except ClientError as e:
                            logger.error(f"Failed to delete message {message_id} from SQS: {e}", exc_info=True)
                    else:
                        # If not processed successfully, the message remains in SQS
                        # and will become visible again after VisibilityTimeout.
                        # This implies that process_sqs_feedback_message should return False
                        # for errors that might be transient or require the message to be retried.
                        # For malformed messages or data errors that are non-retryable,
                        # process_sqs_feedback_message should ideally log and return True to delete.
                        logger.warning(f"Message {message_id} not processed successfully. Will be retried by SQS.")
            else:
                logger.debug("No messages received from SQS poll.")

        except asyncio.CancelledError:
            logger.info("SQS consumer task cancelled. Shutting down...")
            break
        except ClientError as e: # Errors from SQS receive_message itself
            logger.error(f"SQS ClientError in consumer loop: {e}", exc_info=True)
            await asyncio.sleep(settings.SQS_POLL_WAIT_TIME) # Wait before retrying connection/poll
        except Exception as e: # Generic catch-all for other unexpected errors in the loop
            logger.error(f"Unexpected error in SQS consumer loop: {e}", exc_info=True)
            await asyncio.sleep(10) # Wait a bit before trying to continue

@asynccontextmanager
async def lifespan(app: FastAPI):
    log_level = settings.LOG_LEVEL.upper()
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger.info(f"Logging configured at level: {log_level}")
    logger.info(f"Starting up {settings.APP_NAME} (Feedback Engine)... Environment: {settings.APP_ENV}")

    # Initialize SQS client
    app.state.sqs_client = None
    if settings.FEEDBACK_EVENT_SQS_QUEUE_URL:
        try:
            sqs_params = {"region_name": settings.AWS_REGION} if settings.AWS_REGION else {}
            if settings.AWS_ENDPOINT_URL: # For LocalStack
                sqs_params["endpoint_url"] = settings.AWS_ENDPOINT_URL
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY: # For explicit credentials
                sqs_params["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                sqs_params["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

            sqs_client = boto3.client("sqs", **sqs_params)
            sqs_client.get_queue_attributes(QueueUrl=settings.FEEDBACK_EVENT_SQS_QUEUE_URL, AttributeNames=['QueueArn'])
            app.state.sqs_client = sqs_client
            logger.info(f"Successfully connected to SQS queue: {settings.FEEDBACK_EVENT_SQS_QUEUE_URL}")
        except Exception as e:
            logger.error(f"Failed to initialize/connect to SQS queue {settings.FEEDBACK_EVENT_SQS_QUEUE_URL}: {e}", exc_info=True)
            if settings.APP_ENV == "production": raise RuntimeError("SQS connection failed on startup.") from e
    else:
        logger.warning("FEEDBACK_EVENT_SQS_QUEUE_URL not configured. SQS functionality disabled.")

    # Initialize PostgreSQL pool for Feedback DB
    app.state.pg_pool_feedback = None
    if settings.POSTGRES_DSN_FEEDBACK_DB:
        try:
            app.state.pg_pool_feedback = await asyncpg.create_pool(
                dsn=settings.POSTGRES_DSN_FEEDBACK_DB,
                min_size=settings.DB_POOL_MIN_SIZE,
                max_size=settings.DB_POOL_MAX_SIZE
            )
            # Optionally, test connection by acquiring and releasing a connection or running a simple query
            async with app.state.pg_pool_feedback.acquire() as conn:
                await conn.fetchval("SELECT 1")
            logger.info("Feedback PostgreSQL pool successfully initialized and tested.")
        except Exception as e:
            logger.error(f"Failed to initialize Feedback PostgreSQL pool: {e}", exc_info=True)
            if settings.APP_ENV == "production": raise RuntimeError("Feedback DB connection failed on startup.") from e
    else:
        logger.warning("POSTGRES_DSN_FEEDBACK_DB not configured. Feedback DB functionality disabled.")

    # Start SQS consumer if SQS and DB are available
    global sqs_consumer_task
    if app.state.sqs_client and app.state.pg_pool_feedback:
        sqs_consumer_task = asyncio.create_task(run_sqs_feedback_consumer(app))
        logger.info("SQS feedback consumer task started.")
    else:
        logger.warning("SQS consumer not started due to missing SQS client or DB pool.")

    yield # Application runs here

    logger.info(f"Shutting down {settings.APP_NAME} (Feedback Engine)...")
    if sqs_consumer_task and not sqs_consumer_task.done():
        logger.info("Cancelling SQS consumer task...")
        sqs_consumer_task.cancel()
        try:
            await sqs_consumer_task
        except asyncio.CancelledError:
            logger.info("SQS consumer task successfully cancelled.")
        except Exception as e: # Should not happen if task handles CancelledError
            logger.error(f"Error during SQS consumer task shutdown: {e}", exc_info=True)

    if app.state.pg_pool_feedback:
        logger.info("Closing Feedback PostgreSQL pool...")
        await app.state.pg_pool_feedback.close()
        logger.info("Feedback PostgreSQL pool closed.")
    if app.state.sqs_client:
        logger.info("SQS client present on shutdown (conceptual cleanup).")

app = FastAPI(
    title=settings.APP_NAME,
    version="0.2.1", # Incremented version for new features
    description="Feedback Engine for EchoSphere Personas (with SQS processing and DB storage)",
    lifespan=lifespan
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get(settings.API_V1_STR + "/health", tags=["Health Check"])
async def health_check(request: Request):
    sqs_client_active = hasattr(request.app.state, 'sqs_client') and request.app.state.sqs_client is not None
    pg_pool_active = hasattr(request.app.state, 'pg_pool_feedback') and request.app.state.pg_pool_feedback is not None
    consumer_task_running = sqs_consumer_task and not sqs_consumer_task.done() if sqs_consumer_task else False

    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "sqs_queue_configured": bool(settings.FEEDBACK_EVENT_SQS_QUEUE_URL),
        "sqs_client_active": sqs_client_active,
        "feedback_db_configured": bool(settings.POSTGRES_DSN_FEEDBACK_DB),
        "feedback_db_pool_active": pg_pool_active,
        "sqs_consumer_running": consumer_task_running
    }

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8003,
        reload=True,
        log_level=settings.LOG_LEVEL.lower()
    )
