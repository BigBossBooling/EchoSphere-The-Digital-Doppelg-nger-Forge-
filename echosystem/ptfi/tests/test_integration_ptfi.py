# echosystem/ptfi/tests/test_integration_ptfi.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any # For type hints

# Third-party library imports for type hinting mocks if needed
import asyncpg
import httpx # Not directly used by PTFI main logic but good for consistency if other tests use it
# Assuming neo4j types are available for type hinting the mocks
from neo4j import AsyncDriver as Neo4jAsyncDriver, AsyncSession as Neo4jAsyncSession


# Adjust import paths as necessary
try:
    from ptfi.main import app # PTFI FastAPI app
    from ptfi.config import Settings # To access API_V1_STR
    # Import models for request/response validation and constructing mock data
    from ptfi.models import (
        TraitCandidateDisplayModel, PaginatedTraitCandidateResponseModel,
        TraitActionRequestModel, TraitModifications, TraitActionResponseModel,
        CustomTraitRequestModel, CustomTraitResponseModel, UpdatedTraitDetailsDisplay,
        EvidenceSnippet, UserRefinedTraitActionModel
    )
    from ptfi import db_clients # To patch its global variables
    from ptfi.pkg_service_client_ptfi import PKGServiceClientPTFIError
except ImportError:
    import sys
    import os
    # This assumes the tests are run from a context where 'echosystem' is in PYTHONPATH
    # or the CWD is 'echosystem'. If running tests from within 'ptfi/tests',
    # this path adjustment is needed.
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from ptfi.main import app
    from ptfi.config import Settings
    from ptfi.models import (
        TraitCandidateDisplayModel, PaginatedTraitCandidateResponseModel,
        TraitActionRequestModel, TraitModifications, TraitActionResponseModel,
        CustomTraitRequestModel, CustomTraitResponseModel, UpdatedTraitDetailsDisplay,
        EvidenceSnippet, UserRefinedTraitActionModel
    )
    from ptfi import db_clients
    from ptfi.pkg_service_client_ptfi import PKGServiceClientPTFIError


@pytest.fixture(scope="module")
def client_ptfi():
    # This TestClient will use the app instance from ptfi.main
    # Settings and global db clients will be patched by mock_ptfi_dependencies fixture
    return TestClient(app)

@pytest.fixture(scope="function") # Function scope to reset mocks for each test
async def mock_ptfi_dependencies(monkeypatch, event_loop): # event_loop for async fixtures if needed
    # 1. Override Settings for testing
    # Create a *new* Settings instance for each test function to avoid state leakage
    settings_override = Settings(
        POSTGRES_DSN_PTFI="postgresql+asyncpg://test_ptfi_user:test_pass@testhost:5432/test_ptfi_db",
        NEO4J_URI="bolt://test-neo4j-host:7687",
        NEO4J_USER="testneo_ptfi",
        NEO4J_PASSWORD="testpassword_ptfi",
        API_V1_STR="/api/v1/ptfi", # Ensure this matches what endpoints use
        APP_ENV="test_integration_ptfi",
        LOG_LEVEL="DEBUG"
    )
    # Patch the settings object where it's imported in the modules under test
    monkeypatch.setattr("ptfi.config.settings", settings_override)
    monkeypatch.setattr("ptfi.main.settings", settings_override) # If main directly imports settings
    monkeypatch.setattr("ptfi.db_clients.settings", settings_override)
    monkeypatch.setattr("ptfi.pkg_service_client_ptfi.settings", settings_override, raising=False)


    # 2. Mock database clients at the db_clients module level
    mock_pg_pool_ptfi = AsyncMock(spec=asyncpg.pool.Pool)
    mock_pg_conn_ptfi = AsyncMock(spec=asyncpg.connection.Connection)
    # Configure acquire to return a context manager that yields the connection
    acquire_cm_pg = AsyncMock()
    acquire_cm_pg.__aenter__.return_value = mock_pg_conn_ptfi
    mock_pg_pool_ptfi.acquire.return_value = acquire_cm_pg
    # Mock transaction on connection
    mock_pg_transaction = AsyncMock(spec=asyncpg.transaction.Transaction)
    mock_pg_conn_ptfi.transaction.return_value = mock_pg_transaction # For 'async with conn.transaction():'
    monkeypatch.setattr(db_clients, "pg_pool_ptfi", mock_pg_pool_ptfi)

    mock_neo_driver_ptfi = AsyncMock(spec=Neo4jAsyncDriver)
    mock_neo_session_ptfi = AsyncMock(spec=Neo4jAsyncSession)
    # Configure session to be an async context manager
    acquire_cm_neo = AsyncMock()
    acquire_cm_neo.__aenter__.return_value = mock_neo_session_ptfi
    mock_neo_driver_ptfi.session.return_value = acquire_cm_neo # For 'async with driver.session() as s:'

    # Mock execute_write on the session mock. It should allow side_effects for different queries.
    mock_neo_session_ptfi.execute_write = AsyncMock()
    monkeypatch.setattr(db_clients, "neo4j_driver_ptfi", mock_neo_driver_ptfi)

    # It's important that the app's lifespan manager uses these patched objects.
    # Since lifespan calls init_postgres_pool and init_neo4j_driver from db_clients,
    # and those functions set the global variables in db_clients, this patching should work.
    # We are essentially pre-setting the globals that the init functions would normally set.
    # To be absolutely sure, one could also patch the init functions themselves if they do more complex setup.
    # For now, directly patching the globals in db_clients is simpler for this test structure.

    # Yield a dictionary of key mocks for tests to use and configure further
    yield {
        "pg_conn": mock_pg_conn_ptfi,
        "neo_session": mock_neo_session_ptfi,
        "settings": settings_override
    }
    # No explicit teardown needed for mocks here as monkeypatch handles it.


@pytest.mark.asyncio
async def test_ptfi_get_trait_candidates_flow(client_ptfi, mock_ptfi_dependencies):
    mock_pg_conn = mock_ptfi_dependencies["pg_conn"]
    test_settings = mock_ptfi_dependencies["settings"]
    user_id = uuid.uuid4()
    candidate_id = uuid.uuid4()

    mock_pg_conn.fetchval.return_value = 1 # Total count
    mock_pg_conn.fetch.return_value = [
        { # Data as it would come from asyncpg.Record (dictionary-like)
            "candidate_id": candidate_id, "user_id": user_id, "trait_name": "Sample Candidate",
            "trait_description": "A candidate trait for testing.", "trait_category": "LinguisticStyle",
            "supporting_evidence_snippets": json.dumps([{"type": "text", "content": "evidence", "sourcePackageID": str(uuid.uuid4()), "sourceDetail":"detail"}]),
            "confidence_score": 0.75, "originating_models": json.dumps(["model_A"]),
            "associated_feature_set_ids": json.dumps([str(uuid.uuid4())]), "status": "candidate",
            "creation_timestamp": datetime.now(timezone.utc), "last_updated_timestamp": datetime.now(timezone.utc)
        }
    ]

    response = client_ptfi.get(f"{test_settings.API_V1_STR}/users/{user_id}/persona/traits/candidates?status=candidate")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["data"]) == 1
    assert data["data"][0]["candidateID"] == str(candidate_id) # Pydantic model will stringify UUID
    mock_pg_conn.fetchval.assert_called_once()
    mock_pg_conn.fetch.assert_called_once()

@pytest.mark.asyncio
async def test_ptfi_trait_action_confirm_asis_flow(client_ptfi, mock_ptfi_dependencies):
    mock_pg_conn = mock_ptfi_dependencies["pg_conn"]
    mock_neo_session = mock_ptfi_dependencies["neo_session"]
    test_settings = mock_ptfi_dependencies["settings"]

    user_id = uuid.uuid4()
    candidate_id = uuid.uuid4()

    # 1. Mock PG fetchrow for getting the ExtractedTraitCandidate
    mock_pg_conn.fetchrow.return_value = {
        "candidate_id": candidate_id, "user_id": user_id, "status": "candidate",
        "trait_name": "Original Name", "trait_description": "Original Desc",
        "trait_category": "LinguisticStyle", "confidence_score": 0.8, "creation_timestamp": datetime.now(timezone.utc), "last_updated_timestamp": datetime.now(timezone.utc),
        "originating_models": json.dumps(["MAIPP_Model_X"]), "associated_feature_set_ids": json.dumps([str(uuid.uuid4())]),
        "supporting_evidence_snippets": json.dumps([])
    }
    # 2. Mock PG execute for status update & fetchval for log insert RETURNING
    mock_pg_conn.execute.return_value = "UPDATE 1"
    mock_pg_conn.fetchval.return_value = uuid.uuid4() # refinementActionID for log

    # 3. Mock Neo4j response from update_pkg_trait_status_and_properties
    # This mock should reflect the data returned by the Cypher query within the pkg_service_client
    async def mock_neo_execute_write_confirm(*args, **kwargs): # tx_fn, query, params
        query = args[1] # The Cypher query string
        if "RETURN t.traitID AS traitID_in_pkg" in query: # Trait update query
            # Must return a mock that has an async data() method
            mock_result_cursor = AsyncMock()
            mock_result_cursor.data.return_value = [{
                "traitID_in_pkg": str(candidate_id), "name": "Original Name", "description": "Original Desc",
                "category": "LinguisticStyle", "status_in_pkg": "active_user_confirmed", "origin": "ai_confirmed_user",
                "userConfidence": None, "lastRefinedTimestamp": datetime.now(timezone.utc).isoformat()
            }]
            return mock_result_cursor
        # For relationship queries, consume is enough if no data returned
        mock_summary_result = AsyncMock()
        mock_summary_result.consume = AsyncMock(return_value=MagicMock(counters={"relationships_created":1}))
        return mock_summary_result

    mock_neo_session.execute_write.side_effect = mock_neo_execute_write_confirm

    action_payload = {"userDecision": "confirmed_asis"}
    response = client_ptfi.post(
        f"{test_settings.API_V1_STR}/users/{user_id}/persona/traits/candidates/{candidate_id}/action",
        json=action_payload
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Trait candidate action 'confirmed_asis' processed."
    assert data["updatedTraitCandidateStatus"] == "confirmed_by_user"
    assert data["updatedTraitInPKG"]["status_in_pkg"] == "active_user_confirmed"

    assert mock_pg_conn.fetchrow.call_count == 1
    assert mock_pg_conn.execute.call_count == 1    # For UPDATE extracted_trait_candidates
    assert mock_pg_conn.fetchval.call_count == 1   # For INSERT user_refined_trait_actions

    assert mock_neo_session.execute_write.call_count >= 3 # User MERGE, Trait SET, Relationship MERGE/DELETE

@pytest.mark.asyncio
async def test_ptfi_add_custom_trait_flow(client_ptfi, mock_ptfi_dependencies):
    mock_pg_conn = mock_ptfi_dependencies["pg_conn"]
    mock_neo_session = mock_ptfi_dependencies["neo_session"]
    test_settings = mock_ptfi_dependencies["settings"]
    user_id = uuid.uuid4()
    new_trait_id_generated_in_pkg_client = uuid.uuid4()

    mock_pg_conn.fetchval.return_value = uuid.uuid4() # For refinementActionID log

    async def mock_neo_execute_write_custom(*args, **kwargs):
        query = args[1]
        if "CREATE (t:Trait" in query: # Trait creation query
            mock_result_cursor = AsyncMock()
            mock_result_cursor.data.return_value = [{
                "traitID_in_pkg": str(new_trait_id_generated_in_pkg_client), "name": "User Custom Trait",
                "description": "A very custom trait.", "category": "Skill",
                "status_in_pkg": "active", "origin": "user_defined",
                "userConfidence": 5, "lastRefinedTimestamp": datetime.now(timezone.utc).isoformat()
            }]
            return mock_result_cursor
        # For other MERGE queries (User, relationships, evidence)
        mock_summary_result = AsyncMock()
        mock_summary_result.consume = AsyncMock(return_value=MagicMock(counters={"nodes_created":1, "relationships_created":1}))
        return mock_summary_result

    mock_neo_session.execute_write.side_effect = mock_neo_execute_write_custom

    custom_trait_payload = {
        "traitName": "User Custom Trait", "traitDescription": "A very custom trait.",
        "traitCategory": "Skill", "userConfidenceRating": 5,
        "supportingEvidence_userText": ["User says so."]
    }
    response = client_ptfi.post(
        f"{test_settings.API_V1_STR}/users/{user_id}/persona/traits/custom",
        json=custom_trait_payload
    )

    assert response.status_code == 201
    data = response.json()
    assert data["message"] == "Custom trait 'User Custom Trait' added successfully."
    assert data["newTrait"]["name"] == "User Custom Trait"
    assert data["newTrait"]["traitID_in_pkg"] == str(new_trait_id_generated_in_pkg_client)

    mock_pg_conn.fetchval.assert_called_once() # For log insert
    # Neo4j: User MERGE, Trait CREATE, User-Trait MERGE, Evidence MERGE, Trait-Evidence MERGE
    assert mock_neo_session.execute_write.call_count >= (1 + 1 + 1 + (1*2)) # 1 user, 1 trait, 1 user-trait, 1 evidence node+rel
```
