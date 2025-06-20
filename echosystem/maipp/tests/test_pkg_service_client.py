import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from typing import List, Dict, Any
from datetime import datetime

# Adjust import path
try:
    from maipp import pkg_service_client
    from maipp.models import ExtractedTraitCandidateModel, EvidenceSnippet
    from maipp.config import Settings
    # For mocking Neo4j exceptions if needed
    from neo4j.exceptions import ServiceUnavailable, AuthError
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from maipp import pkg_service_client
    from maipp.models import ExtractedTraitCandidateModel, EvidenceSnippet
    from maipp.config import Settings
    from neo4j.exceptions import ServiceUnavailable, AuthError


@pytest.fixture
def mock_neo4j_driver_session():
    # This fixture provides a mock for an AsyncSession from the Neo4j driver
    session_mock = AsyncMock(spec=pkg_service_client.AsyncSession)
    # Mock execute_write to directly invoke the passed function for simplicity in testing queries
    async def mock_execute_write(func, query, params):
        # In a real scenario, func is _execute_write_tx_fn which needs a ManagedTransaction mock
        # For this unit test, we can simplify if _execute_write_tx_fn is tested separately
        # or by making func directly callable with query/params if it's simple enough.
        # Let's assume func is our _execute_write_tx_fn and it needs a transaction mock.
        tx_mock = AsyncMock(spec=pkg_service_client.ManagedTransaction)
        tx_mock.run = AsyncMock()
        tx_mock.run.return_value.consume = AsyncMock(return_value=MagicMock()) # Mock consume()
        return await func(tx_mock, query, params)

    session_mock.execute_write = MagicMock(side_effect=mock_execute_write) # Use MagicMock for side_effect on async

    # Mock the session to be an async context manager
    session_mock.__aenter__.return_value = session_mock
    session_mock.__aexit__.return_value = None
    return session_mock

@pytest.fixture(autouse=True) # Apply to all tests in this module to ensure driver is mocked
def mock_neo4j_driver(monkeypatch, mock_neo4j_driver_session):
    # This fixture mocks the global neo4j_driver used by the service client functions
    driver_mock = AsyncMock(spec=pkg_service_client.AsyncGraphDatabase.driver)
    driver_mock.session.return_value = mock_neo4j_driver_session # Return the session mock
    # Patch the global driver instance in pkg_service_client
    monkeypatch.setattr(pkg_service_client, "neo4j_driver", driver_mock)
    return driver_mock


@pytest.fixture
def sample_user_id_uuid() -> uuid.UUID:
    return uuid.uuid4()

@pytest.fixture
def sample_candidate(sample_user_id_uuid) -> ExtractedTraitCandidateModel:
    pkg_id = uuid.uuid4()
    return ExtractedTraitCandidateModel(
        candidateID=uuid.uuid4(),
        userID=sample_user_id_uuid,
        traitName="PKG Test Trait",
        traitDescription="Description for PKG test.",
        traitCategory="KnowledgeDomain",
        supportingEvidenceSnippets=[
            EvidenceSnippet(type="test_evidence", content="evidence_content", sourcePackageID=pkg_id, sourceDetail="detail1", relevance_score=0.8)
        ],
        confidenceScore=0.88,
        originatingModels=["model_X"],
        associatedFeatureSetIDs=[uuid.uuid4()]
    )

# --- Tests for init_neo4j_driver and close_neo4j_driver ---
@pytest.mark.asyncio
@patch("maipp.pkg_service_client.AsyncGraphDatabase.driver")
async def test_init_neo4j_driver_success(mock_async_driver_class, monkeypatch):
    mock_driver_instance = AsyncMock()
    mock_driver_instance.verify_connectivity = AsyncMock()
    mock_async_driver_class.return_value = mock_driver_instance

    # Ensure global driver is None before test
    monkeypatch.setattr(pkg_service_client, "neo4j_driver", None)

    await pkg_service_client.init_neo4j_driver("bolt://testuri", "user", "pass")
    assert pkg_service_client.neo4j_driver == mock_driver_instance
    mock_driver_instance.verify_connectivity.assert_called_once()
    # Reset global driver for other tests
    monkeypatch.setattr(pkg_service_client, "neo4j_driver", None)


@pytest.mark.asyncio
@patch("maipp.pkg_service_client.AsyncGraphDatabase.driver")
async def test_init_neo4j_driver_auth_error(mock_async_driver_class, monkeypatch):
    mock_async_driver_class.side_effect = AuthError("Auth failed")
    monkeypatch.setattr(pkg_service_client, "neo4j_driver", None)
    await pkg_service_client.init_neo4j_driver("bolt://testuri", "user", "wrongpass")
    assert pkg_service_client.neo4j_driver is None
    monkeypatch.setattr(pkg_service_client, "neo4j_driver", None)


@pytest.mark.asyncio
async def test_close_neo4j_driver(mock_neo4j_driver, monkeypatch): # Uses the autouse fixture
    # Set a mock driver to be closed
    # The autouse fixture already sets pkg_service_client.neo4j_driver to mock_neo4j_driver
    await pkg_service_client.close_neo4j_driver()
    mock_neo4j_driver.close.assert_called_once()
    assert pkg_service_client.neo4j_driver is None # Ensure it's reset globally


# --- Tests for _execute_write_tx_fn ---
@pytest.mark.asyncio
async def test_execute_write_tx_fn_success():
    mock_tx = AsyncMock(spec=pkg_service_client.ManagedTransaction)
    mock_result_summary = MagicMock() # Mock for result summary
    mock_result_summary.counters = {"nodes_created": 1}
    mock_tx.run.return_value.consume = AsyncMock(return_value=mock_result_summary)

    query = "CREATE (n) RETURN n"
    params = {}
    await pkg_service_client._execute_write_tx_fn(mock_tx, query, params)
    mock_tx.run.assert_called_once_with(query, params)
    mock_tx.run.return_value.consume.assert_called_once()

@pytest.mark.asyncio
async def test_execute_write_tx_fn_failure():
    mock_tx = AsyncMock(spec=pkg_service_client.ManagedTransaction)
    mock_tx.run.side_effect = Exception("DB Error")

    with pytest.raises(pkg_service_client.PKGServiceClientError, match="Transaction failed for query: CREATE... Error: DB Error"):
        await pkg_service_client._execute_write_tx_fn(mock_tx, "CREATE (n)", {})

# --- Tests for ensure_user_node_exists ---
@pytest.mark.asyncio
async def test_ensure_user_node_exists_success(mock_neo4j_driver_session, sample_user_id_uuid):
    result = await pkg_service_client.ensure_user_node_exists(sample_user_id_uuid)
    assert result is True
    # Check that execute_write was called on the session mock
    # The actual query and params check is a bit complex due to the way execute_write is mocked here
    # We'd need to inspect the arguments passed to the side_effect function of session.execute_write
    assert mock_neo4j_driver_session.execute_write.call_count == 1
    # Example of deeper assertion (might need more refined mocking of execute_write):
    # call_args = mock_neo4j_driver_session.execute_write.call_args[0]
    # assert "MERGE (u:User {userID: $userID})" in call_args[1] # query
    # assert call_args[2]["userID"] == str(sample_user_id_uuid) # params

@pytest.mark.asyncio
async def test_ensure_user_node_exists_failure(mock_neo4j_driver_session, sample_user_id_uuid):
    mock_neo4j_driver_session.execute_write.side_effect = Exception("Simulated PKG error")
    result = await pkg_service_client.ensure_user_node_exists(sample_user_id_uuid)
    assert result is False

# --- Tests for add_trait_candidate_to_pkg ---
@pytest.mark.asyncio
async def test_add_trait_candidate_to_pkg_success(mock_neo4j_driver_session, sample_user_id_uuid, sample_candidate):
    result = await pkg_service_client.add_trait_candidate_to_pkg(sample_user_id_uuid, sample_candidate)
    assert result is True
    # Expect 3 execute_write calls: Trait node, User-Trait rel, Evidence node, Trait-Evidence rel
    # One for trait, one for user-trait rel, and for each evidence: one for evidence node, one for trait-evidence rel
    expected_calls = 2 + (len(sample_candidate.supportingEvidenceSnippets) * 2)
    assert mock_neo4j_driver_session.execute_write.call_count == expected_calls

@pytest.mark.asyncio
async def test_add_trait_candidate_to_pkg_failure(mock_neo4j_driver_session, sample_user_id_uuid, sample_candidate):
    mock_neo4j_driver_session.execute_write.side_effect = Exception("Simulated PKG error during trait add")
    result = await pkg_service_client.add_trait_candidate_to_pkg(sample_user_id_uuid, sample_candidate)
    assert result is False

# --- Tests for add_mentioned_concepts_to_pkg ---
@pytest.mark.asyncio
async def test_add_mentioned_concepts_to_pkg_success(mock_neo4j_driver_session, sample_user_id_uuid, sample_package_id):
    concepts_info = [
        {"name": "AI Ethics", "frequency": 3, "sentiment_avg": 0.75},
        {"name": "Machine Learning", "frequency": 5, "sentiment_avg": 0.6}
    ]
    result = await pkg_service_client.add_mentioned_concepts_to_pkg(sample_user_id_uuid, concepts_info, sample_package_id)
    assert result is True
    # Each concept results in 2 writes (Concept node, User-Concept rel)
    assert mock_neo4j_driver_session.execute_write.call_count == len(concepts_info) * 2

@pytest.mark.asyncio
async def test_add_mentioned_concepts_to_pkg_empty_list(mock_neo4j_driver_session, sample_user_id_uuid, sample_package_id):
    result = await pkg_service_client.add_mentioned_concepts_to_pkg(sample_user_id_uuid, [], sample_package_id)
    assert result is True
    mock_neo4j_driver_session.execute_write.assert_not_called()

@pytest.mark.asyncio
async def test_add_mentioned_concepts_to_pkg_partial_failure(mock_neo4j_driver_session, sample_user_id_uuid, sample_package_id):
    concepts_info = [
        {"name": "AI Ethics", "frequency": 1},
        {"name": "Problematic Concept", "frequency": 1} # This one will fail
    ]
    # Make the second concept's second write (User-Concept rel) fail
    mock_neo4j_driver_session.execute_write.side_effect = [
        None, # Concept "AI Ethics" node
        None, # User-Concept "AI Ethics" rel
        None, # Concept "Problematic Concept" node
        Exception("Simulated PKG error for problematic concept rel") # User-Concept "Problematic" rel fails
    ]
    result = await pkg_service_client.add_mentioned_concepts_to_pkg(sample_user_id_uuid, concepts_info, sample_package_id)
    assert result is False # Should indicate partial failure by returning False
    assert mock_neo4j_driver_session.execute_write.call_count == 4 # All 4 calls attempted
```
