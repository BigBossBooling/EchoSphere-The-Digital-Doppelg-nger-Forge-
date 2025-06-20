import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import uuid
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import asyncio

# Adjust import path
try:
    from maipp import main_orchestrator
    from maipp.config import Settings
    from maipp.data_handler_service import UserDataPackageInfo
    from maipp.consent_client_service import ConsentVerificationResponse
    from maipp.models import RawAnalysisFeatureSet, ExtractedTraitCandidateModel
    from maipp.ai_adapters.base_adapter import AIAdapterError
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from maipp import main_orchestrator
    from maipp.config import Settings
    from maipp.data_handler_service import UserDataPackageInfo
    from maipp.consent_client_service import ConsentVerificationResponse
    from maipp.models import RawAnalysisFeatureSet, ExtractedTraitCandidateModel
    from maipp.ai_adapters.base_adapter import AIAdapterError


@pytest.fixture(scope="function") # Function scope to reset mocks for each test
def mock_maipp_settings(monkeypatch):
    # This fixture provides fresh settings for each test and patches them into relevant modules
    # Note: It's crucial that all modules consistently import 'settings' from 'maipp.config'
    # for monkeypatching to work effectively.
    settings_obj = Settings(
        UDIM_NOTIFICATION_QUEUE_URL="test-queue-url",
        POSTGRES_DSN_UDIM_METADATA="postgresql+asyncpg://test_udim_user:pass@localhost:5432/test_udim_db",
        MONGO_DB_URL="mongodb://localhost:27017",
        MONGO_MAIPP_DATABASE_NAME="test_maipp_db",
        POSTGRES_DSN_MAIPP_CANDIDATES="postgresql+asyncpg://test_maipp_user:pass@localhost:5432/test_maipp_cand_db",
        NEO4J_URI="bolt://localhost:7687",
        NEO4J_USER="testneo",
        NEO4J_PASSWORD="testpassword",
        CONSENT_API_URL="http://test-consent-api/v1",
        GOOGLE_GEMINI_API_KEY="test-gemini-key" # To enable gemini_topic_adapter initialization conceptually
    )
    monkeypatch.setattr(main_orchestrator, "settings", settings_obj)
    # Patch settings in other modules if they import it directly and it's not already covered
    # by patching main_orchestrator.settings (depends on import styles)
    for module_name in ["data_handler_service", "consent_client_service",
                        "ai_adapters.google_gemini_adapter", "feature_store_service",
                        "trait_derivation_service", "candidate_store_service", "pkg_service_client"]:
        if hasattr(main_orchestrator, module_name): # Check if module is imported
            module_obj = getattr(main_orchestrator, module_name)
            if hasattr(module_obj, "settings"):
                 monkeypatch.setattr(f"maipp.{module_name}.settings", settings_obj)
        elif module_name in sys.modules: # If module directly imported by test (e.g. from maipp import X)
             monkeypatch.setattr(f"maipp.{module_name}.settings", settings_obj, raising=False)


    # Patch global client variables in main_orchestrator
    monkeypatch.setattr(main_orchestrator, "sqs_client", MagicMock())
    monkeypatch.setattr(main_orchestrator, "s3_client", MagicMock())
    monkeypatch.setattr(main_orchestrator, "kms_client", MagicMock())
    monkeypatch.setattr(main_orchestrator, "pg_pool_udim", AsyncMock(spec=asyncpg.Pool))
    monkeypatch.setattr(main_orchestrator, "http_client", AsyncMock(spec=httpx.AsyncClient))
    monkeypatch.setattr(main_orchestrator, "mongo_client", AsyncMock(spec=main_orchestrator.AsyncIOMotorClient))
    monkeypatch.setattr(main_orchestrator, "maipp_db", AsyncMock(spec=main_orchestrator.AsyncIOMotorDatabase))
    monkeypatch.setattr(main_orchestrator, "pg_pool_maipp_candidates", AsyncMock(spec=asyncpg.Pool))

    # Mock the Neo4j driver initialization within pkg_service_client as that's where it's set
    mock_neo_driver = AsyncMock()
    monkeypatch.setattr("maipp.pkg_service_client.neo4j_driver", mock_neo_driver)

    # Mock the Gemini adapter instance
    mock_gemini_adapter_instance = AsyncMock()
    mock_gemini_adapter_instance.get_model_identifier.return_value = "MockedGeminiAdapter_test_model"
    monkeypatch.setattr(main_orchestrator, "gemini_topic_adapter", mock_gemini_adapter_instance)

    return settings_obj


@pytest.fixture
def sample_sqs_message_payload():
    return {
        "packageID": str(uuid.uuid4()),
        "userID": str(uuid.uuid4()),
        "consentTokenID": str(uuid.uuid4()),
        "rawDataReference": "s3://test-bucket/path/to/data.enc",
        "dataType": "text/plain",
        "sourceDescription": "Test data for orchestrator.",
        "metadata": {"originalFilename": "orchestrator_test.txt"},
        "sqsMessageId": "sqs-msg-id-orchestrator"
    }

@pytest.fixture
def mock_package_info(sample_sqs_message_payload) -> UserDataPackageInfo:
    return UserDataPackageInfo(
        package_id=sample_sqs_message_payload["packageID"],
        user_id=sample_sqs_message_payload["userID"],
        consent_token_id=sample_sqs_message_payload["consentTokenID"],
        raw_data_reference=sample_sqs_message_payload["rawDataReference"],
        encryption_key_id="test-kms-key", # This would come from DB in real flow
        data_type=sample_sqs_message_payload["dataType"],
        metadata=sample_sqs_message_payload["metadata"]
    )

# --- Tests for initialize_maipp_dependencies ---
@pytest.mark.asyncio
@patch("maipp.main_orchestrator.boto3.client")
@patch("maipp.main_orchestrator.asyncpg.create_pool")
@patch("maipp.main_orchestrator.httpx.AsyncClient")
@patch("maipp.main_orchestrator.AsyncIOMotorClient") # motor.motor_asyncio.AsyncIOMotorClient
@patch("maipp.main_orchestrator.GoogleGeminiAdapter") # ai_adapters.google_gemini_adapter.GoogleGeminiAdapter
@patch("maipp.pkg_service_client.init_neo4j_driver") # Patch Neo4j init from its module
async def test_initialize_maipp_dependencies_success(
    mock_init_neo_driver, mock_gemini_adapter_class, mock_motor_client_class,
    mock_httpx_client_class, mock_asyncpg_pool, mock_boto_client,
    mock_maipp_settings # Use the fixture to patch settings
):
    # Configure mocks
    mock_boto_client.return_value = MagicMock() # SQS, S3, KMS clients
    mock_asyncpg_pool.return_value = AsyncMock(spec=asyncpg.Pool) # Both PG pools
    mock_httpx_client_class.return_value = AsyncMock(spec=httpx.AsyncClient)

    mock_mongo_db_instance = AsyncMock(spec=main_orchestrator.AsyncIOMotorDatabase)
    mock_mongo_db_instance.command = AsyncMock(return_value={"ok": 1}) # For ping
    mock_motor_client_instance = AsyncMock()
    mock_motor_client_instance.__getitem__.return_value = mock_mongo_db_instance
    mock_motor_client_class.return_value = mock_motor_client_instance

    mock_gemini_adapter_instance = AsyncMock()
    mock_gemini_adapter_instance.client = True # Simulate successful client init within adapter
    mock_gemini_adapter_instance.model_name = "mocked-gemini"
    mock_gemini_adapter_class.return_value = mock_gemini_adapter_instance

    mock_init_neo_driver.return_value = None # Neo4j init is via its own service now

    await main_orchestrator.initialize_maipp_dependencies(mock_maipp_settings)

    assert mock_boto_client.call_count == 3 # SQS, S3, KMS
    assert mock_asyncpg_pool.call_count == 2 # UDIM pool and MAIPP Candidates pool
    mock_httpx_client_class.assert_called_once()
    mock_motor_client_class.assert_called_once_with(mock_maipp_settings.MONGO_DB_URL)
    mock_gemini_adapter_class.assert_called_once()
    # Neo4j driver init is now in pkg_service_client, not directly here.
    # We would test that pkg_service_client.init_neo4j_driver is called if we were to mock it.
    # For this test, we assume the global 'neo4j_driver' in pkg_service_client would be set.


# --- Tests for process_data_package ---
# These will be complex due to the number of mocked dependencies.
# Focus on testing the orchestration logic, not the details of sub-services (already unit-tested).

@pytest.mark.asyncio
@patch("maipp.main_orchestrator.fetch_user_data_package_metadata")
@patch("maipp.main_orchestrator.retrieve_and_decrypt_s3_object")
@patch("maipp.main_orchestrator.extract_text_from_decrypted_data")
@patch("maipp.main_orchestrator.verify_consent_for_action")
# Assuming gemini_topic_adapter is a global that was set during initialize_maipp_dependencies
# We can access it via main_orchestrator.gemini_topic_adapter
@patch.object(main_orchestrator, 'gemini_topic_adapter', new_callable=AsyncMock) # Patch the global adapter instance
@patch("maipp.main_orchestrator.save_batch_raw_analysis_features")
@patch("maipp.main_orchestrator.derive_traits_from_features")
@patch("maipp.main_orchestrator.save_batch_extracted_trait_candidates")
@patch("maipp.pkg_service_client.ensure_user_node_exists") # Patching where it's called from
@patch("maipp.pkg_service_client.add_trait_candidate_to_pkg")
@patch("maipp.pkg_service_client.add_mentioned_concepts_to_pkg")
@patch("maipp.main_orchestrator.securely_dispose_of_decrypted_data")
async def test_process_data_package_successful_text_flow(
    mock_dispose, mock_add_concepts, mock_add_trait_cand_pkg, mock_ensure_user,
    mock_save_trait_cands_pg, mock_derive_traits, mock_save_raw_features_mongo,
    mock_gemini_adapter_analyze_text, # This is the .analyze_text method of the patched global adapter
    mock_verify_consent, mock_extract_text, mock_retrieve_decrypt, mock_fetch_metadata,
    mock_maipp_settings, # Uses the settings patched by this fixture
    sample_sqs_message_payload, mock_package_info
):
    # --- Arrange Mocks ---
    mock_fetch_metadata.return_value = mock_package_info
    mock_retrieve_decrypt.return_value = b"Decrypted text data"
    mock_extract_text.return_value = "This is the extracted text."

    # Consent: Grant all necessary consents
    mock_verify_consent.return_value = ConsentVerificationResponse(is_valid=True)

    # AI Adapter (Gemini for topics)
    gemini_output_features = {"model_output_text": "Topics: AI, Ethics", "finish_reason": "STOP"}
    # The global main_orchestrator.gemini_topic_adapter is already an AsyncMock from mock_maipp_settings
    # We need to configure its 'analyze_text' method.
    main_orchestrator.gemini_topic_adapter.analyze_text = AsyncMock(return_value=gemini_output_features)
    main_orchestrator.gemini_topic_adapter.get_model_identifier.return_value = "MockedGemini_Topics_v1"


    # Feature Store (MongoDB)
    mock_save_raw_features_mongo.return_value = ["mongo_id_1"] # Simulate list of inserted IDs

    # Trait Derivation
    mock_derived_trait = ExtractedTraitCandidateModel(
        userID=uuid.UUID(mock_package_info.user_id), traitName="Test Trait", traitDescription="Derived",
        traitCategory="KnowledgeDomain", confidenceScore=0.7,
        sourcePackageID=uuid.UUID(mock_package_info.package_id) # Need to ensure this is passed if EvidenceSnippet uses it
    )
    mock_derive_traits.return_value = [mock_derived_trait]

    # Candidate Store (PostgreSQL)
    mock_save_trait_cands_pg.return_value = 1 # Number of candidates attempted/saved

    # PKG Service Client
    mock_ensure_user.return_value = True
    mock_add_trait_cand_pkg.return_value = True
    mock_add_concepts.return_value = True

    # --- Act ---
    result_status = await main_orchestrator.process_data_package(sample_sqs_message_payload, mock_maipp_settings)

    # --- Assert ---
    assert result_status == "SUCCESS"
    mock_fetch_metadata.assert_called_once_with(sample_sqs_message_payload["packageID"], main_orchestrator.pg_pool_udim)
    mock_retrieve_decrypt.assert_called_once()
    mock_extract_text.assert_called_once()

    # Assert consent checks (example for text extraction and topic modeling)
    expected_consent_calls = [
        call(mock_package_info.user_id, mock_package_info.consent_token_id, f"action:extract_text,resource_package_id:{mock_package_info.package_id}", main_orchestrator.http_client, mock_package_info.package_id),
        call(mock_package_info.user_id, mock_package_info.consent_token_id, f"action:analyze_text_topics,resource_package_id:{mock_package_info.package_id},model:gemini", main_orchestrator.http_client, mock_package_info.package_id),
    ]
    mock_verify_consent.assert_has_calls(expected_consent_calls, any_order=False) # Assuming order matters here

    main_orchestrator.gemini_topic_adapter.analyze_text.assert_called_once()
    mock_save_raw_features_mongo.assert_called_once()
    # Check that the RawAnalysisFeatureSet passed to save_batch_raw_analysis_features is correct
    saved_features_arg = mock_save_raw_features_mongo.call_args[0][1][0] # Second arg of call, first item in list
    assert saved_features_arg.extractedFeatures == gemini_output_features

    mock_derive_traits.assert_called_once()
    mock_save_trait_cands_pg.assert_called_once_with(main_orchestrator.pg_pool_maipp_candidates, [mock_derived_trait])

    # PKG calls
    # Need to ensure user_id passed to PKG is UUID
    user_uuid_for_pkg = uuid.UUID(mock_package_info.user_id)
    mock_ensure_user.assert_called_once_with(user_uuid_for_pkg) # Assuming direct call from orchestrator
    mock_add_trait_cand_pkg.assert_called_once_with(user_uuid_for_pkg, mock_derived_trait)
    # mock_add_concepts.assert_called_once() # This part is more conceptual in process_data_package for now

    mock_dispose.assert_called_once()


@pytest.mark.asyncio
@patch("maipp.main_orchestrator.fetch_user_data_package_metadata", new_callable=AsyncMock)
async def test_process_data_package_no_metadata(mock_fetch_metadata, mock_maipp_settings, sample_sqs_message_payload):
    mock_fetch_metadata.return_value = None
    result = await main_orchestrator.process_data_package(sample_sqs_message_payload, mock_maipp_settings)
    assert result == "DELETE_NO_METADATA"

@pytest.mark.asyncio
@patch("maipp.main_orchestrator.fetch_user_data_package_metadata", new_callable=AsyncMock)
@patch("maipp.main_orchestrator.retrieve_and_decrypt_s3_object", new_callable=AsyncMock)
@patch("maipp.main_orchestrator.securely_dispose_of_decrypted_data", new_callable=MagicMock) # Sync mock for finally
async def test_process_data_package_decryption_fails(
    mock_dispose, mock_retrieve_decrypt, mock_fetch_metadata,
    mock_maipp_settings, sample_sqs_message_payload, mock_package_info
):
    mock_fetch_metadata.return_value = mock_package_info
    mock_retrieve_decrypt.return_value = None # Simulate decryption failure

    result = await main_orchestrator.process_data_package(sample_sqs_message_payload, mock_maipp_settings)
    assert result == "RETRY_LATER"
    mock_dispose.assert_not_called() # No data to dispose if decryption failed to return it


@pytest.mark.asyncio
@patch("maipp.main_orchestrator.fetch_user_data_package_metadata", new_callable=AsyncMock)
@patch("maipp.main_orchestrator.retrieve_and_decrypt_s3_object", new_callable=AsyncMock)
@patch("maipp.main_orchestrator.extract_text_from_decrypted_data", new_callable=AsyncMock)
@patch("maipp.main_orchestrator.verify_consent_for_action", new_callable=AsyncMock)
@patch("maipp.main_orchestrator.securely_dispose_of_decrypted_data", new_callable=MagicMock)
async def test_process_data_package_consent_denied_for_extraction(
    mock_dispose, mock_verify_consent, mock_extract_text, mock_retrieve_decrypt, mock_fetch_metadata,
    mock_maipp_settings, sample_sqs_message_payload, mock_package_info
):
    mock_fetch_metadata.return_value = mock_package_info
    mock_retrieve_decrypt.return_value = b"decrypted data"
    # Deny consent for text extraction
    mock_verify_consent.return_value = ConsentVerificationResponse(is_valid=False, reason="Test Deny")

    # Mock gemini adapter as it might be checked globally
    monkeypatch = pytest.MonkeyPatch() # Get monkeypatch fixture if not already argument
    mock_gemini_adapter_instance = AsyncMock()
    monkeypatch.setattr(main_orchestrator, "gemini_topic_adapter", mock_gemini_adapter_instance)


    result = await main_orchestrator.process_data_package(sample_sqs_message_payload, mock_maipp_settings)

    assert result == "SUCCESS" # Still success, but text specific parts skipped
    mock_extract_text.assert_not_called() # Text extraction should not have happened
    main_orchestrator.gemini_topic_adapter.analyze_text.assert_not_called() # Gemini should not be called
    mock_dispose.assert_called_once_with(b"decrypted data", package_id=mock_package_info.package_id)


# SQS Consumer Loop tests are more complex due to the infinite loop and boto3 client.
# Often, the core logic of message processing (like a simplified process_data_package)
# is tested, and the loop itself is assumed to be managed by a framework or tested
# in broader E2E/component tests with a real SQS or local mock like ElasticMQ.
# For a unit test of the loop's structure, one might test a single iteration.
```
