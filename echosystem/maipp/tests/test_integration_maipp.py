# echosystem/maipp/tests/test_integration_maipp.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import uuid
import json
from datetime import datetime, timezone
import asyncio
from typing import Optional, List, Dict, Any # For type hints

# Third-party libraries for mocking or type hinting if necessary
import asyncpg
import httpx
# from neo4j import AsyncGraphDatabase, AsyncSession # For type hinting mocks
# from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection # For type hinting mocks


# Adjust import paths as necessary
try:
    from maipp import main_orchestrator
    from maipp.config import Settings
    from maipp.models import RawAnalysisFeatureSet, ExtractedTraitCandidateModel, EvidenceSnippet
    from maipp import data_handler_service, consent_client_service
    from maipp.ai_adapters import google_gemini_adapter # For specific adapter mock
    from maipp.ai_adapters.base_adapter import AIAdapterError # For raising adapter errors
    from maipp import feature_store_service, candidate_store_service, pkg_service_client

except ImportError:
    import sys
    import os
    # Add 'echosystem' directory to sys.path
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from maipp import main_orchestrator
    from maipp.config import Settings
    from maipp.models import RawAnalysisFeatureSet, ExtractedTraitCandidateModel, EvidenceSnippet
    from maipp import data_handler_service, consent_client_service
    from maipp.ai_adapters import google_gemini_adapter
    from maipp.ai_adapters.base_adapter import AIAdapterError
    from maipp import feature_store_service, candidate_store_service, pkg_service_client


@pytest.fixture(scope="function")
async def test_maipp_setup(monkeypatch):
    # 1. Override Settings for testing
    settings_override = Settings(
        MONGO_DB_URL="mongodb://localhost:27017/test_maipp_features_it",
        MONGO_MAIPP_DATABASE_NAME="test_maipp_features_it", # Ensure this is used by feature_store
        POSTGRES_DSN_MAIPP_CANDIDATES="postgresql+asyncpg://test:test@localhost:5432/test_maipp_candidates_it",
        POSTGRES_DSN_UDIM_METADATA="postgresql+asyncpg://test:test@localhost:5432/test_udim_metadata_it",
        NEO4J_URI="bolt://localhost:7687",
        NEO4J_USER="neo4j",
        NEO4J_PASSWORD="testpassword",
        GOOGLE_GEMINI_API_KEY="fake_gemini_key_for_test",
        CONSENT_API_URL="http://mock-consent-service/internal/consent/v1",
        UDIM_NOTIFICATION_QUEUE_URL="test-maipp-queue",
        AWS_REGION="us-east-1",
        LOG_LEVEL="DEBUG" # Use DEBUG for more verbose test output if needed
    )
    # Patch the global settings object(s) where they are imported.
    # It's crucial that all modules use 'from .config import settings'.
    modules_to_patch_settings = [
        "maipp.config", "maipp.main_orchestrator", "maipp.data_handler_service",
        "maipp.consent_client_service", "maipp.ai_adapters.google_gemini_adapter",
        "maipp.feature_store_service", "maipp.candidate_store_service", "maipp.pkg_service_client"
    ]
    for module_path in modules_to_patch_settings:
        monkeypatch.setattr(f"{module_path}.settings", settings_override, raising=False)


    # 2. Mock external dependencies at a high level
    mock_boto_sqs = MagicMock()
    mock_boto_s3 = MagicMock()
    mock_boto_kms = MagicMock() # Not directly used by MAIPP if S3 handles SSE-KMS

    # Patch boto3.client calls within the modules where they are used.
    monkeypatch.setattr("maipp.main_orchestrator.boto3.client", lambda service_name, **kwargs: {
        "sqs": mock_boto_sqs, "s3": mock_boto_s3, "kms": mock_boto_kms
    }.get(service_name))
    # If data_handler_service also makes direct boto3 calls, patch there too.
    monkeypatch.setattr("maipp.data_handler_service.boto3.client", lambda service_name, **kwargs: {
         "s3": mock_boto_s3, "kms": mock_boto_kms # data_handler likely only needs s3/kms
    }.get(service_name))


    mock_pg_pool_udim = AsyncMock(spec=asyncpg.Pool)
    mock_pg_conn_udim = AsyncMock(spec=asyncpg.Connection)
    mock_pg_pool_udim.acquire.return_value.__aenter__.return_value = mock_pg_conn_udim
    monkeypatch.setattr(main_orchestrator, "pg_pool_udim", mock_pg_pool_udim)

    mock_pg_pool_maipp_cand = AsyncMock(spec=asyncpg.Pool)
    mock_pg_conn_maipp_cand = AsyncMock(spec=asyncpg.Connection)
    mock_pg_pool_maipp_cand.acquire.return_value.__aenter__.return_value = mock_pg_conn_maipp_cand
    # Mock the transaction context manager for the candidate pool connection
    mock_pg_transaction_cand = AsyncMock(spec=asyncpg.transaction.Transaction)
    mock_pg_conn_maipp_cand.transaction.return_value = mock_pg_transaction_cand
    monkeypatch.setattr(main_orchestrator, "pg_pool_maipp_candidates", mock_pg_pool_maipp_cand)


    # Motor Client & DB & Collection Mocks
    # Correctly mock the AsyncIOMotorClient, its database selection, and collection selection
    mock_mongo_motor_client = AsyncMock(spec=main_orchestrator.AsyncIOMotorClient)
    mock_maipp_motor_db = AsyncMock(spec=main_orchestrator.AsyncIOMotorDatabase)
    mock_mongo_motor_collection = AsyncMock(spec=main_orchestrator.AsyncIOMotorCollection)

    mock_mongo_motor_client.__getitem__.return_value = mock_maipp_motor_db # client[db_name]
    mock_maipp_motor_db.__getitem__.return_value = mock_mongo_motor_collection # db[collection_name]
    mock_maipp_motor_db.command = AsyncMock(return_value={'ok': 1}) # For ping

    monkeypatch.setattr(main_orchestrator, "mongo_client", mock_mongo_motor_client)
    monkeypatch.setattr(main_orchestrator, "maipp_db", mock_maipp_motor_db)


    # Neo4j Driver & Session Mocks
    mock_neo4j_driver_instance = AsyncMock() # spec=neo4j.AsyncGraphDatabase.driver - causes issues if neo4j not fully importable
    mock_neo4j_session_instance = AsyncMock() # spec=neo4j.AsyncSession
    mock_neo4j_driver_instance.session.return_value = mock_neo4j_session_instance # When driver.session() is called
    mock_neo4j_session_instance.__aenter__.return_value = mock_neo4j_session_instance # For 'async with driver.session() as session:'
    # Mock execute_write to avoid needing a real transaction object for this integration test level
    mock_neo4j_session_instance.execute_write = AsyncMock()
    # Patch the global driver in pkg_service_client, as it's initialized and used there
    monkeypatch.setattr(pkg_service_client, "neo4j_driver", mock_neo4j_driver_instance)


    mock_httpx_client = AsyncMock(spec=httpx.AsyncClient)
    monkeypatch.setattr(main_orchestrator, "http_client", mock_httpx_client)

    mock_gemini_adapter_instance = AsyncMock(spec=google_gemini_adapter.GoogleGeminiAdapter)
    # Ensure get_model_identifier returns a string
    mock_gemini_adapter_instance.get_model_identifier = MagicMock(return_value="MockedGeminiAdapter_topics_IT")
    monkeypatch.setattr(main_orchestrator, "gemini_topic_adapter", mock_gemini_adapter_instance)

    # Re-run initialize_maipp_dependencies with all the mocks in place
    # This ensures global client variables in main_orchestrator are set to our mocks
    # and logging is configured with test settings.
    await main_orchestrator.initialize_maipp_dependencies(settings_override)

    # Return a dictionary of key mocks for tests to use and configure further
    return {
        "sqs": mock_boto_sqs, "s3": mock_boto_s3, "kms": mock_boto_kms,
        "pg_conn_udim": mock_pg_conn_udim, # The connection mock from the pool
        "pg_conn_maipp_cand": mock_pg_conn_maipp_cand,
        "mongo_collection": mock_mongo_motor_collection, # The collection mock
        "neo4j_session": mock_neo4j_session_instance, # The session mock
        "httpx_client": mock_httpx_client,
        "gemini_adapter": mock_gemini_adapter_instance,
        "settings": settings_override
    }

@pytest.mark.asyncio
async def test_maipp_successful_text_processing_flow(test_maipp_setup):
    mocks = await test_maipp_setup # Await the fixture
    package_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    consent_token_id = str(uuid.uuid4())
    s3_data_ref = f"s3://{mocks['settings'].S3_BUCKET_NAME}/users/{user_id}/packages/{package_id}/test_doc_it.txt.enc"

    # --- Define Mock Behaviors specific to this test ---
    # 1. UDIM DB (fetch_user_data_package_metadata)
    # Construct a dict that asyncpg.Record would produce
    mock_pg_udim_record_dict = {
        "package_id": package_id, "user_id": user_id, "raw_data_reference": s3_data_ref,
        "encryption_key_id": "test-kms-key-it", "data_type": "text/plain",
        "consent_token_id": consent_token_id, "source_description": "Test IT doc",
        "metadata": {"originalFilename": "test_doc_it.txt"}
    }
    mocks["pg_conn_udim"].fetchrow.return_value = mock_pg_udim_record_dict

    # 2. S3 (retrieve_and_decrypt_s3_object)
    decrypted_text_content = "Integration test: AI Ethics and the future of Stoic Philosophy in modern tech."
    mock_s3_response_body = MagicMock()
    mock_s3_response_body.read.return_value = decrypted_text_content.encode('utf-8')
    mocks["s3"].get_object.return_value = {"Body": mock_s3_response_body}

    # 3. Consent API (verify_consent_for_action) - Allow all relevant actions
    async def mock_consent_verify_integration(*args, **kwargs):
        scope_requested = args[2] # required_scope is the 3rd positional argument
        logger.debug(f"Mock Consent API called for scope: {scope_requested}")
        return consent_client_service.ConsentVerificationResponse(is_valid=True, granted_scope={"scope": scope_requested})
    mocks["httpx_client"].get.side_effect = mock_consent_verify_integration

    # 4. AI Adapter (Gemini for topic extraction)
    mock_gemini_output = {
        "model_output_text": "Key Topics: AI Ethics, Stoic Philosophy, Future Tech",
        "prompt_hash": "dummy_hash", "model_name_used": "gemini-pro",
        "parameters_used": {"temp": 0.7}, "finish_reason": "STOP", "usage_metadata": {"tokens": 100}
    }
    mocks["gemini_adapter"].analyze_text.return_value = mock_gemini_output

    # 5. MongoDB (save_batch_raw_analysis_features)
    mocks["mongo_collection"].insert_many.return_value = MagicMock(inserted_ids=[uuid.uuid4()])

    # 6. PostgreSQL for Candidates (save_batch_extracted_trait_candidates)
    # The mock pg_conn_maipp_cand.executemany is already an AsyncMock, no specific return needed for "INSERT N" status
    # We will check it was called with the right number of items.

    # 7. Neo4j for PKG (ensure_user_node_exists, etc.)
    # The mock_neo4j_session.execute_write is already an AsyncMock.

    # --- Act ---
    sqs_message_payload = {
        "packageID": package_id, "userID": user_id, "consentTokenID": consent_token_id,
        "rawDataReference": s3_data_ref, "dataType": "text/plain",
        "sourceDescription": "Integration test data", "metadata": {"originalFilename": "test_doc_it.txt"},
        "sqsMessageId": "sqs-it-msg-001" # Added for logging consistency
    }

    result_status = await main_orchestrator.process_data_package(sqs_message_payload, mocks["settings"])

    # --- Assert ---
    assert result_status == "SUCCESS"

    mocks["pg_conn_udim"].fetchrow.assert_called_once()
    mocks["s3"].get_object.assert_called_once_with(Bucket=mocks["settings"].S3_BUCKET_NAME, Key=s3_data_ref.split(f"s3://{mocks['settings'].S3_BUCKET_NAME}/")[1])

    assert mocks["httpx_client"].get.call_count >= 2 # Text extraction + Topic analysis

    mocks["gemini_adapter"].analyze_text.assert_called_once()
    mocks["mongo_collection"].insert_many.assert_called_once()

    # Assert RawAnalysisFeatures content based on Gemini output
    args_mongo_batch, _ = mocks["mongo_collection"].insert_many.call_args
    assert len(args_mongo_batch[0]) == 1 # One feature set from Gemini
    feature_set_doc = args_mongo_batch[0][0]
    assert feature_set_doc["modelNameOrType"] == "MockedGeminiAdapter_topics_IT"
    assert feature_set_doc["extractedFeatures"] == mock_gemini_output

    # Assert ExtractedTraitCandidate saving was called
    # The number of candidates depends on rules in trait_derivation_service.py
    # Current rules: "Interest in AI Ethics", "Interest in Stoic Philosophy"
    mocks["pg_conn_maipp_cand"].executemany.assert_called_once()
    args_pg_cand_batch, _ = mocks["pg_conn_maipp_cand"].executemany.call_args
    assert len(args_pg_cand_batch[0]) == 2 # Expecting two candidates

    # Assert PKG interactions
    assert mocks["neo4j_session"].execute_write.call_count >= 1 # At least user node ensure
    # More detailed checks on queries sent to Neo4j would require inspecting execute_write call_args

# TODO: More integration tests for:
# - Different data types (audio - would require mocking STT, audio emotion adapters)
# - Consent denial scenarios (ensure specific AI calls are skipped, no related features/traits stored)
# - Failures in saving to Mongo, PostgreSQL, or Neo4j (ensure error is handled, maybe status becomes RETRY_LATER or specific error)
# - AI Adapter raising AIAdapterError (ensure this is caught and handled, feature set marked as failure)
```
