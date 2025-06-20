import pytest
from unittest.mock import AsyncMock, MagicMock, call # Ensure 'call' is imported if used for multiple calls
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

# Adjust import path
try:
    from ptfi import pkg_service_client_ptfi # Assuming PTFI is in PYTHONPATH or tests run from echosystem/
    from ptfi.models import ExtractedTraitCandidateModel, EvidenceSnippet # If these models are used as input
    from ptfi.pkg_service_client_ptfi import PKGServiceClientPTFIError
    from neo4j import AsyncSession, ManagedTransaction # For type hinting
    from neo4j.exceptions import Neo4jError # For simulating DB errors
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from ptfi import pkg_service_client_ptfi
    from ptfi.models import ExtractedTraitCandidateModel, EvidenceSnippet
    from ptfi.pkg_service_client_ptfi import PKGServiceClientPTFIError
    from neo4j import AsyncSession, ManagedTransaction
    from neo4j.exceptions import Neo4jError


@pytest.fixture
def mock_neo4j_session():
    session_mock = AsyncMock(spec=AsyncSession)

    # Configure execute_write to simulate typical behavior
    # It should accept a function (our transaction function) and args/kwargs
    async def mock_execute_write_logic(tx_fn, *args, **kwargs):
        # Create a mock transaction object to pass to tx_fn
        mock_tx = AsyncMock(spec=ManagedTransaction)
        mock_tx.run = AsyncMock() # Mock the run method on the transaction

        # Default mock for result of tx.run().data()
        mock_run_result = MagicMock()
        mock_run_result.data = AsyncMock(return_value=[]) # Default to returning an empty list of records
        mock_run_result.consume = AsyncMock(return_value=MagicMock()) # For summary
        mock_tx.run.return_value = mock_run_result

        # Call the transaction function with the mocked transaction
        return await tx_fn(mock_tx, *args, **kwargs)

    session_mock.execute_write = MagicMock(side_effect=mock_execute_write_logic)
    return session_mock

@pytest.fixture
def sample_user_id() -> uuid.UUID:
    return uuid.uuid4()

@pytest.fixture
def sample_trait_id() -> uuid.UUID:
    return uuid.uuid4()

# --- Tests for _execute_write_tx_ptfi ---
@pytest.mark.asyncio
async def test_execute_write_tx_ptfi_success(mock_neo4j_session): # mock_neo4j_session not directly used here
    mock_tx = AsyncMock(spec=ManagedTransaction)
    mock_result = AsyncMock()
    mock_result.consume = AsyncMock(return_value=MagicMock(counters={"nodes_created":1}))
    mock_tx.run.return_value = mock_result

    query = "CREATE (n:TestNode) RETURN n"
    params = {"prop": "value"}

    summary = await pkg_service_client_ptfi._execute_write_tx_ptfi(mock_tx, query, params)

    mock_tx.run.assert_called_once_with(query, params)
    mock_result.consume.assert_called_once() # Check if consume was called
    assert summary is not None # Check if summary is returned (it's consume's result)

@pytest.mark.asyncio
async def test_execute_write_tx_ptfi_failure(mock_neo4j_session):
    mock_tx = AsyncMock(spec=ManagedTransaction)
    mock_tx.run.side_effect = Neo4jError("Simulated DB error")

    with pytest.raises(PKGServiceClientPTFIError, match="Transaction failed for query: CREATE... Error: Simulated DB error"):
        await pkg_service_client_ptfi._execute_write_tx_ptfi(mock_tx, "CREATE (n)", {})


# --- Tests for ensure_user_node_exists (already in MAIPP tests, but can be contextually tested for PTFI) ---
# For brevity, assuming MAIPP's version of this test is sufficient if the function is identical
# or that it's implicitly tested via other functions here.

# --- Tests for update_pkg_trait_status_and_properties ---
@pytest.mark.asyncio
async def test_update_pkg_trait_confirmed_asis(mock_neo4j_session, sample_user_id, sample_trait_id):
    original_details = {"traitName": "AI Name", "traitDescription": "AI Desc", "traitCategory": "KnowledgeDomain", "origin": "ai_maipp"}

    # Mock the return value of the final RETURN clause of the Cypher query
    mock_tx_run_result = mock_neo4j_session.execute_write.call_args_list[0][0][0].run.return_value if mock_neo4j_session.execute_write.call_args_list else AsyncMock()
    # ^ This is complex. A simpler way is to configure the mock_tx directly if the session_mock passes it.
    # Let's refine the session mock to allow configuring the transaction mock's run result

    async def mock_tx_run_for_update(*args, **kwargs):
        # Based on the query, return appropriate data
        query_str = args[0] if args else ""
        if "RETURN t.traitID AS traitID_in_pkg" in query_str: # This is the trait update query
            return AsyncMock(data=AsyncMock(return_value=[{
                "traitID_in_pkg": str(sample_trait_id), "name": original_details["traitName"],
                "description": original_details["traitDescription"], "category": original_details["traitCategory"],
                "status_in_pkg": "active_user_confirmed", "origin": "ai_confirmed_user",
                "userConfidence": None, "lastRefinedTimestamp": datetime.now(timezone.utc).isoformat()
            }]))
        return AsyncMock(consume=AsyncMock(return_value=MagicMock())) # For other MERGE/DELETE

    # Re-configure the session mock's transaction behavior
    async def mock_execute_write_with_tx_config(tx_fn_arg, query_arg, params_arg):
        mock_tx = AsyncMock(spec=ManagedTransaction)
        mock_tx.run = AsyncMock(side_effect=mock_tx_run_for_update) # Use the side effect
        return await tx_fn_arg(mock_tx, query_arg, params_arg)
    mock_neo4j_session.execute_write = MagicMock(side_effect=mock_execute_write_with_tx_config)


    updated_props = await pkg_service_client_ptfi.update_pkg_trait_status_and_properties(
        mock_neo4j_session, sample_user_id, sample_trait_id, "confirmed_asis",
        original_trait_details=original_details
    )

    assert updated_props is not None
    assert updated_props["status_in_pkg"] == "active_user_confirmed"
    assert updated_props["origin"] == "ai_confirmed_user"
    assert mock_neo4j_session.execute_write.call_count >= 3 # User MERGE, Trait SET, Relationship MERGE/DELETE

@pytest.mark.asyncio
async def test_update_pkg_trait_confirmed_modified(mock_neo4j_session, sample_user_id, sample_trait_id):
    modifications = {"refinedTraitName": "User Modified Name", "userConfidenceRating": 4}
    original_details = {"traitName": "AI Name", "traitDescription": "AI Desc", "traitCategory": "Other"}

    async def mock_tx_run_for_modified(*args, **kwargs):
        query_str = args[0] if args else ""
        if "RETURN t.traitID AS traitID_in_pkg" in query_str:
             return AsyncMock(data=AsyncMock(return_value=[{
                "traitID_in_pkg": str(sample_trait_id), "name": modifications["refinedTraitName"],
                "description": original_details["traitDescription"], "category": original_details["traitCategory"],
                "status_in_pkg": "active_user_modified", "origin": "ai_refined_user",
                "userConfidence": modifications["userConfidenceRating"], "lastRefinedTimestamp": datetime.now(timezone.utc).isoformat()
            }]))
        return AsyncMock(consume=AsyncMock(return_value=MagicMock()))

    async def mock_execute_write_mod(tx_fn_arg, query_arg, params_arg):
        mock_tx = AsyncMock(spec=ManagedTransaction); mock_tx.run = AsyncMock(side_effect=mock_tx_run_for_modified)
        return await tx_fn_arg(mock_tx, query_arg, params_arg)
    mock_neo4j_session.execute_write = MagicMock(side_effect=mock_execute_write_mod)

    updated_props = await pkg_service_client_ptfi.update_pkg_trait_status_and_properties(
        mock_neo4j_session, sample_user_id, sample_trait_id, "confirmed_modified",
        modifications=modifications, original_trait_details=original_details
    )
    assert updated_props is not None
    assert updated_props["name"] == "User Modified Name"
    assert updated_props["status_in_pkg"] == "active_user_modified"
    assert updated_props["origin"] == "ai_refined_user"
    assert updated_props["userConfidence"] == 4

@pytest.mark.asyncio
async def test_update_pkg_trait_rejected(mock_neo4j_session, sample_user_id, sample_trait_id):
    original_details = {"traitName": "AI Name To Reject", "traitDescription": "Desc", "traitCategory": "Other"}

    async def mock_tx_run_for_rejected(*args, **kwargs):
        query_str = args[0] if args else ""
        if "RETURN t.traitID AS traitID_in_pkg" in query_str: # Trait update query
            return AsyncMock(data=AsyncMock(return_value=[{
                "traitID_in_pkg": str(sample_trait_id), "name": original_details["traitName"],
                "status_in_pkg": "rejected_by_user", # Other fields might be null or original
            }]))
        return AsyncMock(consume=AsyncMock(return_value=MagicMock())) # For relationship update

    async def mock_execute_write_rej(tx_fn_arg, query_arg, params_arg):
        mock_tx = AsyncMock(spec=ManagedTransaction); mock_tx.run = AsyncMock(side_effect=mock_tx_run_for_rejected)
        return await tx_fn_arg(mock_tx, query_arg, params_arg)
    mock_neo4j_session.execute_write = MagicMock(side_effect=mock_execute_write_rej)

    updated_props = await pkg_service_client_ptfi.update_pkg_trait_status_and_properties(
        mock_neo4j_session, sample_user_id, sample_trait_id, "rejected",
        original_trait_details=original_details
    )
    assert updated_props is not None
    assert updated_props["status_in_pkg"] == "rejected_by_user"
    # Check that relationship query was also called to set isActive=false
    assert mock_neo4j_session.execute_write.call_count >= 3 # User, Trait, Relationship


# --- Tests for add_custom_trait_to_pkg ---
@pytest.mark.asyncio
async def test_add_custom_trait_to_pkg_success(mock_neo4j_session, sample_user_id):
    trait_name = "User Custom Trait"
    trait_category = "Skill"
    trait_desc = "A skill defined by the user."

    # Mock the return of the CREATE query
    async def mock_tx_run_for_create(*args, **kwargs):
        query_str = args[0] if args else ""
        if "CREATE (t:Trait" in query_str:
            return AsyncMock(data=AsyncMock(return_value=[{ # Ensure .data() is awaitable
                "traitID_in_pkg": str(uuid.uuid4()), "name": trait_name, "description": trait_desc,
                "category": trait_category, "status_in_pkg": "active", "origin": "user_defined"
            }]))
        return AsyncMock(consume=AsyncMock(return_value=MagicMock()))

    async def mock_execute_write_create(tx_fn_arg, query_arg, params_arg):
        mock_tx = AsyncMock(spec=ManagedTransaction); mock_tx.run = AsyncMock(side_effect=mock_tx_run_for_create)
        return await tx_fn_arg(mock_tx, query_arg, params_arg)
    mock_neo4j_session.execute_write = MagicMock(side_effect=mock_execute_write_create)


    new_trait_props = await pkg_service_client_ptfi.add_custom_trait_to_pkg(
        mock_neo4j_session, sample_user_id, trait_name, trait_category, trait_desc, user_confidence=5
    )
    assert new_trait_props is not None
    assert new_trait_props["name"] == trait_name
    assert new_trait_props["origin"] == "user_defined"
    assert new_trait_props["status_in_pkg"] == "active"
    assert mock_neo4j_session.execute_write.call_count >= 3 # User MERGE, Trait CREATE, User-Trait MERGE

@pytest.mark.asyncio
async def test_add_custom_trait_with_evidence(mock_neo4j_session, sample_user_id):
    evidence_texts = ["User stated this explicitly.", "Another supporting point."]

    # Count expected execute_write calls: User, Trait, User-Trait rel,
    # then for each evidence: Evidence Node, Trait-Evidence rel
    expected_writes = 3 + (len(evidence_texts) * 2)

    # Simplified mock for this test, focusing on call count for evidence
    async def mock_tx_run_for_evidence(*args, **kwargs):
        query_str = args[0] if args else ""
        if "CREATE (t:Trait" in query_str: # For the main trait creation
             return AsyncMock(data=AsyncMock(return_value=[{"traitID_in_pkg": str(uuid.uuid4())}]))
        return AsyncMock(consume=AsyncMock(return_value=MagicMock())) # For other MERGE/CREATE

    async def mock_execute_write_ev(tx_fn_arg, query_arg, params_arg):
        mock_tx = AsyncMock(spec=ManagedTransaction); mock_tx.run = AsyncMock(side_effect=mock_tx_run_for_evidence)
        return await tx_fn_arg(mock_tx, query_arg, params_arg)
    mock_neo4j_session.execute_write = MagicMock(side_effect=mock_execute_write_ev)


    await pkg_service_client_ptfi.add_custom_trait_to_pkg(
        mock_neo4j_session, sample_user_id, "Evidenced Trait", "Other", user_provided_evidence_texts=evidence_texts
    )
    assert mock_neo4j_session.execute_write.call_count == expected_writes


# --- Tests for update_communication_style_in_pkg ---
@pytest.mark.asyncio
async def test_update_communication_style_success(mock_neo4j_session, sample_user_id):
    style_dim = "FormalityLevel"
    new_val = "Informal"

    # Mock the return of the relationship update query
    async def mock_tx_run_for_comm_style(*args, **kwargs):
        query_str = args[0] if args else ""
        if "MERGE (u)-[r:ADOPTS_COMMUNICATION_STYLE]->(cse)" in query_str:
            return AsyncMock(data=AsyncMock(return_value=[{
                "styleName": style_dim, "styleValue": new_val, "lastUpdated": datetime.now(timezone.utc).isoformat()
            }]))
        return AsyncMock(consume=AsyncMock(return_value=MagicMock()))

    async def mock_execute_write_comm(tx_fn_arg, query_arg, params_arg):
        mock_tx = AsyncMock(spec=ManagedTransaction); mock_tx.run = AsyncMock(side_effect=mock_tx_run_for_comm_style)
        return await tx_fn_arg(mock_tx, query_arg, params_arg)
    mock_neo4j_session.execute_write = MagicMock(side_effect=mock_execute_write_comm)

    updated_style = await pkg_service_client_ptfi.update_communication_style_in_pkg(
        mock_neo4j_session, sample_user_id, style_dim, new_val
    )
    assert updated_style is not None
    assert updated_style["styleName"] == style_dim
    assert updated_style["styleValue"] == new_val
    # Expect User MERGE, CSE MERGE, User-CSE Relationship MERGE
    assert mock_neo4j_session.execute_write.call_count == 3

```
