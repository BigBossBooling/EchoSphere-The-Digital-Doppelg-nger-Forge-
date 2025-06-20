import pytest
from unittest.mock import AsyncMock, MagicMock, call # Import call for checking multiple calls
import uuid
import json
from datetime import datetime, timezone
from typing import List

# Adjust import path
try:
    from maipp import candidate_store_service
    from maipp.models import ExtractedTraitCandidateModel, EvidenceSnippet
    # Assuming asyncpg might be used directly for specific error types
    from asyncpg.exceptions import UniqueViolationError, PostgresError
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from maipp import candidate_store_service
    from maipp.models import ExtractedTraitCandidateModel, EvidenceSnippet
    from asyncpg.exceptions import UniqueViolationError, PostgresError


@pytest.fixture
def mock_asyncpg_pool():
    pool = AsyncMock(spec=asyncpg.pool.Pool)
    # Mock acquire to return a connection context manager
    conn_mock = AsyncMock(spec=asyncpg.Connection)
    pool.acquire.return_value = conn_mock
    conn_mock.__aenter__.return_value = conn_mock # for 'async with pool.acquire() as conn:'
    conn_mock.fetchval.return_value = None # Default for fetchval
    conn_mock.executemany.return_value = None # Default for executemany

    # Mock transaction context manager
    transaction_mock = AsyncMock(spec=asyncpg.transaction.Transaction)
    conn_mock.transaction.return_value = transaction_mock
    transaction_mock.__aenter__.return_value = transaction_mock # For 'async with conn.transaction():'

    return pool

@pytest.fixture
def sample_candidate_data() -> ExtractedTraitCandidateModel:
    user_id_val = uuid.uuid4()
    package_id_val = uuid.uuid4()
    return ExtractedTraitCandidateModel(
        userID=user_id_val,
        traitName="Detail Oriented",
        traitDescription="Pays close attention to details in submitted texts.",
        traitCategory="CognitiveStyle", # Use a valid category if ENUM was defined
        supportingEvidenceSnippets=[
            EvidenceSnippet(
                type="text_snippet",
                content="User mentioned specific color hex codes.",
                sourcePackageID=package_id_val,
                sourceDetail="doc1.txt, line 10"
            )
        ],
        confidenceScore=0.75,
        originatingModels=["NER_Model_v2", "Custom_Pattern_Matcher_v1"],
        associatedFeatureSetIDs=[uuid.uuid4(), uuid.uuid4()],
        status="candidate",
        creationTimestamp=datetime.now(timezone.utc),
        lastUpdatedTimestamp=datetime.now(timezone.utc)
    )

@pytest.fixture
def sample_candidate_data_list(sample_candidate_data) -> List[ExtractedTraitCandidateModel]:
    cand2 = ExtractedTraitCandidateModel(
        userID=sample_candidate_data.userID, # Same user for batch test
        traitName="Proactive Communicator",
        traitDescription="Often initiates discussion and provides updates without prompting.",
        traitCategory="CommunicationStyle",
        supportingEvidenceSnippets=[
            EvidenceSnippet(
                type="text_snippet",
                content="User sent a follow-up email before the deadline.",
                sourcePackageID=uuid.uuid4(), # Different package
                sourceDetail="email_thread_abc"
            )
        ],
        confidenceScore=0.8,
        originatingModels=["Email_Analysis_Agent_v1"],
        associatedFeatureSetIDs=[uuid.uuid4()],
        status="candidate"
    )
    return [sample_candidate_data, cand2]

# --- Tests for save_extracted_trait_candidate ---
@pytest.mark.asyncio
async def test_save_extracted_trait_candidate_success(mock_asyncpg_pool, sample_candidate_data):
    # Configure fetchval to return the candidate_id upon successful insert/update
    mock_asyncpg_pool.acquire.return_value.__aenter__.return_value.fetchval.return_value = sample_candidate_data.candidateID

    returned_id = await candidate_store_service.save_extracted_trait_candidate(mock_asyncpg_pool, sample_candidate_data)

    assert returned_id == sample_candidate_data.candidateID
    # Get the connection mock to assert calls on it
    conn_mock = mock_asyncpg_pool.acquire.return_value.__aenter__.return_value
    conn_mock.fetchval.assert_called_once()

    # Check query and args (simplified check, full query string is complex)
    args_passed = conn_mock.fetchval.call_args[0]
    assert candidate_store_service.EXTRACTED_TRAIT_CANDIDATES_TABLE in args_passed[0] # Query string
    assert args_passed[1] == sample_candidate_data.candidateID # First param ($1)

@pytest.mark.asyncio
async def test_save_extracted_trait_candidate_db_pool_none(sample_candidate_data):
    result = await candidate_store_service.save_extracted_trait_candidate(None, sample_candidate_data)
    assert result is None

@pytest.mark.asyncio
async def test_save_extracted_trait_candidate_unique_violation(mock_asyncpg_pool, sample_candidate_data):
    # Simulate UniqueViolationError from asyncpg
    # The ON CONFLICT DO UPDATE should prevent this, but testing the except block if it somehow occurs
    conn_mock = mock_asyncpg_pool.acquire.return_value.__aenter__.return_value
    conn_mock.fetchval.side_effect = UniqueViolationError("Simulated unique violation")

    result = await candidate_store_service.save_extracted_trait_candidate(mock_asyncpg_pool, sample_candidate_data)
    assert result is None

@pytest.mark.asyncio
async def test_save_extracted_trait_candidate_postgres_error(mock_asyncpg_pool, sample_candidate_data):
    conn_mock = mock_asyncpg_pool.acquire.return_value.__aenter__.return_value
    conn_mock.fetchval.side_effect = PostgresError("Simulated general Postgres error")

    result = await candidate_store_service.save_extracted_trait_candidate(mock_asyncpg_pool, sample_candidate_data)
    assert result is None

# --- Tests for save_batch_extracted_trait_candidates ---
@pytest.mark.asyncio
async def test_save_batch_extracted_trait_candidates_success(mock_asyncpg_pool, sample_candidate_data_list):
    conn_mock = mock_asyncpg_pool.acquire.return_value.__aenter__.return_value
    # executemany doesn't return a useful value for "affected rows" with ON CONFLICT easily,
    # so the service returns the count of attempted records.

    attempted_count = await candidate_store_service.save_batch_extracted_trait_candidates(mock_asyncpg_pool, sample_candidate_data_list)

    assert attempted_count == len(sample_candidate_data_list)
    conn_mock.executemany.assert_called_once()
    # Check the arguments passed to executemany
    args_passed_to_executemany = conn_mock.executemany.call_args[0]
    assert candidate_store_service.EXTRACTED_TRAIT_CANDIDATES_TABLE in args_passed_to_executemany[0] # Query
    assert len(args_passed_to_executemany[1]) == len(sample_candidate_data_list) # List of records
    # Check first record's conversion (example)
    first_record_tuple = args_passed_to_executemany[1][0]
    assert first_record_tuple[0] == sample_candidate_data_list[0].candidateID
    assert first_record_tuple[2] == sample_candidate_data_list[0].traitName
    # Ensure JSONB fields were dumped to JSON strings
    assert isinstance(first_record_tuple[5], str) # supporting_evidence_snippets
    assert isinstance(first_record_tuple[7], str) # originating_models
    assert isinstance(first_record_tuple[8], str) # associated_feature_set_ids

@pytest.mark.asyncio
async def test_save_batch_extracted_trait_candidates_empty_list(mock_asyncpg_pool):
    conn_mock = mock_asyncpg_pool.acquire.return_value.__aenter__.return_value
    attempted_count = await candidate_store_service.save_batch_extracted_trait_candidates(mock_asyncpg_pool, [])
    assert attempted_count == 0
    conn_mock.executemany.assert_not_called()

@pytest.mark.asyncio
async def test_save_batch_extracted_trait_candidates_db_pool_none(sample_candidate_data_list):
    attempted_count = await candidate_store_service.save_batch_extracted_trait_candidates(None, sample_candidate_data_list)
    assert attempted_count == 0

@pytest.mark.asyncio
async def test_save_batch_extracted_trait_candidates_postgres_error(mock_asyncpg_pool, sample_candidate_data_list):
    conn_mock = mock_asyncpg_pool.acquire.return_value.__aenter__.return_value
    conn_mock.executemany.side_effect = PostgresError("Simulated batch insert error")

    attempted_count = await candidate_store_service.save_batch_extracted_trait_candidates(mock_asyncpg_pool, sample_candidate_data_list)
    assert attempted_count == 0 # Service returns 0 on error
```
