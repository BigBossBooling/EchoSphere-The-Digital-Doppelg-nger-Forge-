# echosystem/maipp/candidate_store_service.py
import logging
import uuid
import json # For serializing JSONB fields
import asyncpg
from typing import List, Optional, Tuple # Changed from uuid.UUID | None to Optional[uuid.UUID] for return type hint consistency
from datetime import datetime # For timestamps

from .models import ExtractedTraitCandidateModel, EvidenceSnippet # Assuming models.py is in the same directory

logger = logging.getLogger(__name__)

# Conceptual table name, ensure this matches your actual DB schema
EXTRACTED_TRAIT_CANDIDATES_TABLE = "extracted_trait_candidates"

async def save_extracted_trait_candidate(
    db_pool: asyncpg.pool.Pool,
    candidate_data: ExtractedTraitCandidateModel
) -> Optional[uuid.UUID]:
    """
    Saves a single ExtractedTraitCandidateModel instance to the PostgreSQL database.
    Returns the candidate_id if successful, None otherwise.
    """
    if not db_pool:
        logger.error(f"[{candidate_data.candidateID}] PostgreSQL connection pool not available. Cannot save trait candidate.")
        return None

    query = f"""
        INSERT INTO {EXTRACTED_TRAIT_CANDIDATES_TABLE} (
            candidate_id, user_id, trait_name, trait_description, trait_category,
            supporting_evidence_snippets, confidence_score, originating_models,
            associated_feature_set_ids, status, creation_timestamp, last_updated_timestamp
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
        )
        ON CONFLICT (candidate_id) DO UPDATE SET
            trait_name = EXCLUDED.trait_name,
            trait_description = EXCLUDED.trait_description,
            trait_category = EXCLUDED.trait_category,
            supporting_evidence_snippets = EXCLUDED.supporting_evidence_snippets,
            confidence_score = EXCLUDED.confidence_score,
            originating_models = EXCLUDED.originating_models,
            associated_feature_set_ids = EXCLUDED.associated_feature_set_ids,
            status = EXCLUDED.status,
            last_updated_timestamp = EXCLUDED.last_updated_timestamp
        RETURNING candidate_id;
    """
    try:
        # Pydantic model_dump ensures correct types for JSONB (like lists of dicts for snippets)
        # Convert UUIDs to string for associatedFeatureSetIDs if they are stored as text[] or jsonb in pg
        # For now, assuming direct mapping or that Pydantic's json_encoders handle it for JSONB.

        # Convert supportingEvidenceSnippets to JSON string for PostgreSQL JSONB type
        evidence_json = json.dumps([snippet.model_dump(mode='json') for snippet in candidate_data.supportingEvidenceSnippets])

        # Convert lists of strings/UUIDs to JSON strings for PostgreSQL JSONB type
        originating_models_json = json.dumps(candidate_data.originatingModels)
        associated_feature_set_ids_json = json.dumps([str(fid) for fid in candidate_data.associatedFeatureSetIDs])


        logger.debug(f"Saving ExtractedTraitCandidate to PostgreSQL: {candidate_data.candidateID}")
        result = await db_pool.fetchval( # fetchval to get the RETURNING candidate_id
            query,
            candidate_data.candidateID, # Already a UUID object from Pydantic default_factory
            candidate_data.userID,
            candidate_data.traitName,
            candidate_data.traitDescription,
            candidate_data.traitCategory,
            evidence_json, # Pass as JSON string
            candidate_data.confidenceScore,
            originating_models_json, # Pass as JSON string
            associated_feature_set_ids_json, # Pass as JSON string
            candidate_data.status,
            candidate_data.creationTimestamp, # Pydantic ensures these are datetime objects
            candidate_data.lastUpdatedTimestamp
        )

        if result:
            logger.info(f"Successfully saved/updated ExtractedTraitCandidate: {result}")
            return result # result is the candidate_id (UUID)
        else:
            # This case might not be reached if ON CONFLICT ... RETURNING is used,
            # as it should always return the ID on successful insert or update.
            # However, keeping for robustness.
            logger.error(f"Failed to get candidate_id back after insert/update for {candidate_data.candidateID}")
            return None

    except asyncpg.UniqueViolationError as e:
        logger.error(f"Database unique violation for ExtractedTraitCandidate {candidate_data.candidateID}: {e}", exc_info=True)
        # This shouldn't happen with ON CONFLICT DO UPDATE, but good to be aware of.
    except asyncpg.PostgresError as e:
        logger.error(f"PostgreSQL error saving ExtractedTraitCandidate {candidate_data.candidateID}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error saving ExtractedTraitCandidate {candidate_data.candidateID}: {e}", exc_info=True)
    return None


async def save_batch_extracted_trait_candidates(
    db_pool: asyncpg.pool.Pool,
    candidates_data: List[ExtractedTraitCandidateModel]
) -> int: # Returns number of candidates attempted to save (not necessarily successfully inserted due to ON CONFLICT DO NOTHING)
    """
    Saves a list of ExtractedTraitCandidateModel instances to PostgreSQL using executemany.
    Uses ON CONFLICT (candidate_id) DO NOTHING to avoid errors if a candidate with the same ID already exists.
    Returns the number of candidates attempted in the batch.
    """
    if not db_pool:
        logger.error("PostgreSQL connection pool not available. Cannot save batch trait candidates.")
        return 0
    if not candidates_data:
        logger.info("No trait candidates provided in batch to save.")
        return 0

    query = f"""
        INSERT INTO {EXTRACTED_TRAIT_CANDIDATES_TABLE} (
            candidate_id, user_id, trait_name, trait_description, trait_category,
            supporting_evidence_snippets, confidence_score, originating_models,
            associated_feature_set_ids, status, creation_timestamp, last_updated_timestamp
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
        )
        ON CONFLICT (candidate_id) DO NOTHING;
    """
    # ON CONFLICT DO NOTHING: Silently skips insertion if candidate_id already exists.
    # This means it won't update existing records. If update is desired, use ON CONFLICT DO UPDATE as in single save.
    # For batch, DO NOTHING is often simpler to manage if primary goal is initial insert.

    # Convert list of Pydantic models to list of tuples for executemany
    records_to_insert: List[Tuple] = []
    for cand in candidates_data:
        records_to_insert.append((
            cand.candidateID, cand.userID, cand.traitName, cand.traitDescription, cand.traitCategory,
            json.dumps([snippet.model_dump(mode='json') for snippet in cand.supportingEvidenceSnippets]),
            cand.confidenceScore,
            json.dumps(cand.originatingModels),
            json.dumps([str(fid) for fid in cand.associatedFeatureSetIDs]),
            cand.status, cand.creationTimestamp, cand.lastUpdatedTimestamp
        ))

    conn: Optional[asyncpg.Connection] = None
    try:
        conn = await db_pool.acquire()
        # For executemany, typically used within a transaction
        async with conn.transaction():
            # The return value of executemany is usually just a status string like "INSERT 0 10"
            # It doesn't return the IDs of inserted rows directly or a simple count of affected rows.
            # We are returning the number of records *attempted*.
            await conn.executemany(query, records_to_insert)

        logger.info(f"Attempted to save batch of {len(records_to_insert)} ExtractedTraitCandidates with ON CONFLICT DO NOTHING.")
        return len(records_to_insert) # Number of records processed in the batch command

    except asyncpg.PostgresError as e:
        logger.error(f"PostgreSQL error during batch save of ExtractedTraitCandidates: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error during batch save of ExtractedTraitCandidates: {e}", exc_info=True)
    finally:
        if conn:
            await db_pool.release(conn)
    return 0 # Indicates 0 successfully processed in case of error
```
