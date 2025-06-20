import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock, call
import uuid
import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

# Adjust import path
try:
    from ptfi.main import app
    from ptfi.config import settings
    from ptfi.models import (
        TraitCandidateDisplayModel, PaginatedTraitCandidateResponseModel,
        TraitActionRequestModel, TraitModifications, TraitActionResponseModel,
        CustomTraitRequestModel, CustomTraitResponseModel, UpdatedTraitDetailsDisplay,
        EvidenceSnippet, UserRefinedTraitActionModel, TraitCategoryEnum, UserDecisionEnum
    )
    from ptfi.pkg_service_client_ptfi import PKGServiceClientPTFIError
    import asyncpg
    # Import neo4j exceptions and driver types for mocking if needed
    from neo4j import AsyncDriver as Neo4jAsyncDriver
    from neo4j import AsyncSession as Neo4jAsyncSession
    from neo4j.exceptions import Neo4jError
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from ptfi.main import app
    from ptfi.config import settings
    from ptfi.models import (
        TraitCandidateDisplayModel, PaginatedTraitCandidateResponseModel,
        TraitActionRequestModel, TraitModifications, TraitActionResponseModel,
        CustomTraitRequestModel, CustomTraitResponseModel, UpdatedTraitDetailsDisplay,
        EvidenceSnippet, UserRefinedTraitActionModel, TraitCategoryEnum, UserDecisionEnum
    )
    from ptfi.pkg_service_client_ptfi import PKGServiceClientPTFIError
    import asyncpg
    from neo4j import AsyncDriver as Neo4jAsyncDriver
    from neo4j import AsyncSession as Neo4jAsyncSession
    from neo4j.exceptions import Neo4jError


USER_ID = uuid.uuid4()
CANDIDATE_ID = uuid.uuid4()
USER_ID_STR = str(USER_ID)
CANDIDATE_ID_STR = str(CANDIDATE_ID)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)

@pytest.fixture(autouse=True)
def mock_dependencies_for_api_tests(monkeypatch):
    # Mock PostgreSQL Pool and Connection
    mock_pg_pool = AsyncMock(spec=asyncpg.pool.Pool)
    mock_pg_conn = AsyncMock(spec=asyncpg.connection.Connection)
    # Configure acquire to return a context manager that yields the connection
    acquire_cm = AsyncMock()
    acquire_cm.__aenter__.return_value = mock_pg_conn
    mock_pg_pool.acquire.return_value = acquire_cm
    # Mock transaction on connection
    mock_pg_transaction = AsyncMock(spec=asyncpg.transaction.Transaction)
    mock_pg_conn.transaction.return_value = mock_pg_transaction
    monkeypatch.setattr("ptfi.db_clients.pg_pool_ptfi", mock_pg_pool)

    # Mock Neo4j Driver & Session
    mock_neo_driver = AsyncMock(spec=Neo4jAsyncDriver)
    mock_neo_session = AsyncMock(spec=Neo4jAsyncSession)
    # Configure session to be an async context manager
    mock_neo_driver.session.return_value = mock_neo_session
    mock_neo_session.__aenter__.return_value = mock_neo_session
    # Mock execute_write to return a mock that has a .data() async method
    async def mock_execute_write_side_effect(tx_fn, *args, **kwargs):
        # This mock needs to simulate the tx_fn being called with a mock transaction
        mock_tx = AsyncMock() # Mock for ManagedTransaction
        mock_tx.run.return_value = AsyncMock(data=AsyncMock(return_value=[]), consume=AsyncMock()) # Default behavior
        return await tx_fn(mock_tx, *args, **kwargs)

    mock_neo_session.execute_write = MagicMock(side_effect=mock_execute_write_side_effect)
    monkeypatch.setattr("ptfi.db_clients.neo4j_driver_ptfi", mock_neo_driver)

    return mock_pg_conn, mock_neo_session


# --- Tests for GET /users/{userID}/persona/traits/candidates ---
def test_get_trait_candidates_success(client, mock_dependencies_for_api_tests):
    mock_pg_conn, _ = mock_dependencies_for_api_tests

    mock_pg_conn.fetchval.return_value = 1 # Total count
    mock_pg_conn.fetch.return_value = [
        {
            "candidate_id": CANDIDATE_ID, "user_id": USER_ID, "trait_name": "Test Trait",
            "trait_description": "Desc", "trait_category": "LinguisticStyle",
            "supporting_evidence_snippets": json.dumps([{"type": "text", "content": "snip", "sourcePackageID": str(uuid.uuid4()), "sourceDetail": "test"}]),
            "confidence_score": 0.8,
            "originating_models": json.dumps(["model1"]), "associated_feature_set_ids": json.dumps([str(uuid.uuid4())]),
            "status": "candidate", "creation_timestamp": datetime.now(timezone.utc),
            "last_updated_timestamp": datetime.now(timezone.utc)
        }
    ]
    response = client.get(f"{settings.API_V1_STR}/users/{USER_ID_STR}/persona/traits/candidates?status=candidate")
    assert response.status_code == 200
    data = response.json(); assert data["total"] == 1; assert len(data["data"]) == 1
    assert data["data"][0]["traitName"] == "Test Trait"
    mock_pg_conn.fetchval.assert_called_once()
    mock_pg_conn.fetch.assert_called_once()

# --- Tests for POST .../action ---
@patch("ptfi.main.update_pkg_trait_status_and_properties", new_callable=AsyncMock)
def test_trait_action_confirm_asis_success(mock_update_pkg, client, mock_dependencies_for_api_tests):
    mock_pg_conn, _ = mock_dependencies_for_api_tests
    mock_pg_conn.fetchrow.return_value = {"candidate_id": CANDIDATE_ID, "user_id": USER_ID, "status": "candidate", "trait_name": "AI Trait", "trait_description": "Desc", "trait_category": "Other", "confidence_score": 0.7} # Added missing fields for model_validate
    mock_pg_conn.fetchval.return_value = uuid.uuid4() # For log_action_id
    mock_update_pkg.return_value = {"traitID_in_pkg": CANDIDATE_ID, "name": "AI Trait", "status_in_pkg": "active_user_confirmed", "category":"Other", "origin":"ai_confirmed_user", "lastRefinedTimestamp": datetime.now(timezone.utc)}

    payload = {"userDecision": "confirmed_asis"}
    response = client.post(f"{settings.API_V1_STR}/users/{USER_ID_STR}/persona/traits/candidates/{CANDIDATE_ID_STR}/action", json=payload)

    assert response.status_code == 200
    data = response.json(); assert "processed" in data["message"]; assert data["updatedTraitCandidateStatus"] == "confirmed_by_user"
    assert data["updatedTraitInPKG"]["status_in_pkg"] == "active_user_confirmed"
    mock_pg_conn.fetchrow.assert_called_once();
    # One execute for candidate status update, one fetchval for log insert.
    assert mock_pg_conn.execute.call_count == 1
    assert mock_pg_conn.fetchval.call_count == 1
    mock_update_pkg.assert_called_once()

# --- Tests for POST .../custom ---
@patch("ptfi.main.add_custom_trait_to_pkg", new_callable=AsyncMock)
def test_add_custom_trait_success(mock_add_pkg, client, mock_dependencies_for_api_tests):
    mock_pg_conn, _ = mock_dependencies_for_api_tests
    new_trait_id = uuid.uuid4()
    mock_add_pkg.return_value = {"traitID_in_pkg": new_trait_id, "name": "User Trait", "status_in_pkg": "active", "category":"Skill", "origin":"user_defined", "lastRefinedTimestamp": datetime.now(timezone.utc)}
    mock_pg_conn.fetchval.return_value = uuid.uuid4() # For log_action_id

    payload = {"traitName": "User Trait", "traitDescription": "User defined.", "traitCategory": "Skill", "supportingEvidence_userText": ["evidence"]}
    response = client.post(f"{settings.API_V1_STR}/users/{USER_ID_STR}/persona/traits/custom", json=payload)

    assert response.status_code == 201
    data = response.json(); assert "added successfully" in data["message"]; assert data["newTrait"]["traitID_in_pkg"] == str(new_trait_id)
    mock_add_pkg.assert_called_once()
    mock_pg_conn.fetchval.assert_called_once()

# --- Tests for PUT .../communication-styles ---
@patch("ptfi.main.update_communication_style_in_pkg", new_callable=AsyncMock)
def test_update_communication_styles_success(mock_update_comm_style_call, client, mock_dependencies_for_api_tests):
    mock_update_comm_style_call.return_value = {"styleName": "FormalityLevel", "styleValue": "Neutral", "lastUpdated": datetime.now(timezone.utc).isoformat()}

    payload = {"FormalityLevel": "Neutral", "HumorUsage": "Low"}
    response = client.put(f"{settings.API_V1_STR}/users/{USER_ID_STR}/persona/communication-styles", json=payload)

    assert response.status_code == 200
    data = response.json(); assert "updated successfully" in data["message"]
    assert data["updated_styles"]["FormalityLevel"] == "Neutral"
    assert mock_update_comm_style_call.call_count == len(payload)

```
