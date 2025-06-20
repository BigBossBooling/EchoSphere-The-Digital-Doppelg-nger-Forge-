# echosystem/ptfi/pkg_service_client_ptfi.py
import logging
import uuid
from typing import Dict, Any, Optional, List # Added List
from neo4j import AsyncSession, ManagedTransaction # Assuming driver/session is passed
from datetime import datetime, timezone # For timestamps

# Assuming models.py is in the same directory or package structure allows this import
# from .models import TraitModifications # TraitModifications is for request, not directly stored in PKG this way

logger = logging.getLogger(__name__)

class PKGServiceClientPTFIError(Exception):
    """Custom exception for PTFI's PKG Service Client errors."""
    pass

# Re-define helper if not shared from a common place, or import if it is.
# This helper executes a Cypher query within a managed transaction.
async def _execute_write_tx_ptfi(
    tx: ManagedTransaction,
    query: str,
    params: Dict[str, Any] = None # params should default to None if not always provided
):
    if params is None:
        params = {}
    log_query = query.replace('\n', ' ').replace('\r', ' ') # Make query more log-friendly
    logger.debug(f"PTFI PKG Write Query: '{log_query[:150]}...' with params keys: {list(params.keys())}")
    try:
        result = await tx.run(query, params)
        summary = await result.consume()
        # consume() is important to ensure the query is fully processed and to get summary information
        logger.debug(f"PTFI PKG Write Query successful. Summary counters: {summary.counters if summary else 'N/A'}")
        return summary # Return summary for potential inspection by caller
    except Exception as e:
        logger.error(f"Error executing PTFI PKG write tx query '{log_query[:150]}...': {e}", exc_info=True)
        # Re-raise to ensure the transaction is rolled back by Neo4j driver's session.execute_write
        raise PKGServiceClientPTFIError(f"Transaction failed for query: {log_query[:100]}... Error: {str(e)}") from e


async def update_pkg_trait_status_and_properties(
    session: AsyncSession, # Neo4j AsyncSession
    user_id: uuid.UUID,
    trait_id_in_pkg: uuid.UUID, # This is the ExtractedTraitCandidate.candidateID, used as Trait node's traitID
    user_decision: str, # 'confirmed_asis', 'confirmed_modified', 'rejected'
    modifications: Optional[Dict[str, Any]] = None, # Comes from TraitModifications Pydantic model .model_dump()
    original_trait_details: Optional[Dict[str, Any]] = None # e.g., from ExtractedTraitCandidate
) -> Optional[Dict[str, Any]]: # Returns properties of the updated/created PKG Trait node
    """
    Updates a Trait node in PKG based on user action from PTFI.
    Assumes the Trait node was initially created by MAIPP with status 'candidate_from_maipp'.
    Returns a dictionary representing the updated Trait node's key properties from PKG.
    """
    log_prefix = f"[User:{user_id}][Trait:{trait_id_in_pkg}] PKG Update - "
    logger.info(f"{log_prefix}Action: {user_decision}, Modifications: {modifications}")

    # 1. Ensure User node exists (idempotent)
    user_node_query = "MERGE (u:User {userID: $userID}) ON CREATE SET u.createdAt = datetime() RETURN u.userID"
    try:
        await session.execute_write(_execute_write_tx_ptfi, user_node_query, {"userID": str(user_id)})
    except PKGServiceClientPTFIError as e:
        logger.error(f"{log_prefix}Failed to ensure User node exists. Error: {e}")
        return None # Cannot proceed without user node

    new_pkg_status = ""
    origin_type = ""
    set_clauses = []
    params = { # Common params
        "traitID": str(trait_id_in_pkg),
        "userID": str(user_id),
        "lastRefinedTimestamp": datetime.now(timezone.utc).isoformat()
    }

    if user_decision == "confirmed_asis":
        new_pkg_status = "active_user_confirmed"
        origin_type = "ai_confirmed_user" # Keep MAIPP origin but mark user confirmation
        # Use original details from ExtractedTraitCandidate if they were passed
        if original_trait_details:
            params.update({
                "name": original_trait_details.get("traitName"),
                "description": original_trait_details.get("traitDescription"),
                "category": original_trait_details.get("traitCategory"),
                # maipp_confidence is already on the node from MAIPP's initial creation
            })
            set_clauses.extend([
                "t.name = $name", "t.description = $description", "t.category = $category"
            ])
        set_clauses.append("t.origin = $origin_type")
        params["origin_type"] = origin_type

    elif user_decision == "confirmed_modified":
        new_pkg_status = "active_user_modified"
        origin_type = "ai_refined_user"
        if not modifications: # Should be validated by API layer, but double check
            logger.error(f"{log_prefix}Modifications missing for 'confirmed_modified' decision.")
            return None

        # Apply modifications
        if modifications.get("refinedTraitName"):
            set_clauses.append("t.name = $name")
            params["name"] = modifications["refinedTraitName"]
        elif original_trait_details and original_trait_details.get("traitName"): # Keep original if not modified
             set_clauses.append("t.name = $name")
             params["name"] = original_trait_details.get("traitName")

        if modifications.get("refinedTraitDescription") is not None: # Allow empty string for description
            set_clauses.append("t.description = $description")
            params["description"] = modifications["refinedTraitDescription"]
        elif original_trait_details and original_trait_details.get("traitDescription"):
             set_clauses.append("t.description = $description")
             params["description"] = original_trait_details.get("traitDescription")

        if modifications.get("refinedTraitCategory"):
            set_clauses.append("t.category = $category")
            params["category"] = modifications["refinedTraitCategory"]
        elif original_trait_details and original_trait_details.get("traitCategory"):
             set_clauses.append("t.category = $category")
             params["category"] = original_trait_details.get("traitCategory")

        if modifications.get("userConfidenceRating") is not None:
            set_clauses.append("t.userConfidence = $userConfidence")
            params["userConfidence"] = modifications["userConfidenceRating"]

        set_clauses.append("t.origin = $origin_type")
        params["origin_type"] = origin_type

    elif user_decision == "rejected":
        new_pkg_status = "rejected_by_user"
        # No need to update name/desc/category from modifications for rejection
    else:
        logger.error(f"{log_prefix}Unknown user_decision: {user_decision}")
        return None

    set_clauses.append("t.status_in_pkg = $new_pkg_status")
    params["new_pkg_status"] = new_pkg_status

    # Update the Trait node itself
    # MAIPP should have created the Trait node with status 'candidate_from_maipp'
    # If PTFI is the first to create this Trait node (e.g. if MAIPP only creates ExtractedTraitCandidate in PG table)
    # then MERGE would be appropriate here. Assuming MAIPP created it:
    trait_update_query = f"""
    MATCH (t:Trait {{traitID: $traitID}})
    SET {", t.".join(set_clauses)}
    RETURN t.traitID AS traitID_in_pkg, t.name AS name, t.description AS description,
           t.category AS category, t.status_in_pkg AS status_in_pkg, t.origin AS origin,
           t.userConfidence AS userConfidence, t.lastRefinedTimestamp AS lastRefinedTimestamp
    """
    # Remove t. from SET clauses as params are distinct
    trait_update_query = trait_update_query.replace("t.", "", len(set_clauses)) # Quick fix for this format
    # A better way for SET: build "t.property = $value" strings
    final_set_clauses_str = ", ".join([f"t.{clause.split(' ')[0]} = ${clause.split(' ')[0]}" for clause in set_clauses])
    trait_update_query = f"""
    MATCH (t:Trait {{traitID: $traitID}})
    SET {final_set_clauses_str}
    RETURN t.traitID AS traitID_in_pkg, t.name AS name, t.description AS description,
           t.category AS category, t.status_in_pkg AS status_in_pkg, t.origin AS origin,
           t.userConfidence AS userConfidence, t.lastRefinedTimestamp AS lastRefinedTimestamp
    """

    updated_trait_props: Optional[Dict[str, Any]] = None
    try:
        update_summary = await session.execute_write(_execute_write_tx_ptfi, trait_update_query, params)
        # To get the returned properties, we need to process the result of the query
        # The _execute_write_tx_fn needs to be adapted to return records, not just summary.
        # For now, let's assume we can refetch or the PKG service returns it.
        # Conceptual: if update_summary contains records or if we refetch:
        # updated_trait_props = ... (fetch logic)

        # For now, construct what we expect PKG to have based on inputs
        # This is not ideal, PKG service should be source of truth.
        # This will be refined when PKG service API is fully defined.
        updated_trait_props = {
            "traitID_in_pkg": trait_id_in_pkg,
            "name": params.get("name", original_trait_details.get("traitName") if original_trait_details else "Unknown"),
            "description": params.get("description", original_trait_details.get("traitDescription") if original_trait_details else None),
            "category": params.get("category", original_trait_details.get("traitCategory") if original_trait_details else "Other"),
            "status_in_pkg": new_pkg_status,
            "origin": params.get("origin_type", original_trait_details.get("origin") if original_trait_details else None),
            "userConfidence": params.get("userConfidence"),
            "lastRefinedTimestamp": params.get("lastRefinedTimestamp")
        }


        # Update User-Trait relationship
        if user_decision in ["confirmed_asis", "confirmed_modified"]:
            rel_query = """
            MATCH (u:User {userID: $userID}), (t:Trait {traitID: $traitID})
            MERGE (u)-[r:HAS_TRAIT]->(t)  // Changed from HAS_CANDIDATE_TRAIT
            ON CREATE SET r.source = $origin_type, r.isActive = true, r.addedTimestamp = datetime(), r.lastConfirmedTimestamp = datetime()
            ON MATCH SET r.source = $origin_type, r.isActive = true, r.lastConfirmedTimestamp = datetime()
            // Optionally remove old :HAS_CANDIDATE_TRAIT if it exists and is different
            WITH u, t
            OPTIONAL MATCH (u)-[old_r:HAS_CANDIDATE_TRAIT]->(t)
            DELETE old_r
            """
            await session.execute_write(_execute_write_tx_ptfi, rel_query, {"userID": str(user_id), "traitID": str(trait_id_in_pkg), "origin_type": origin_type})
        elif user_decision == "rejected":
            rel_reject_query = """
            MATCH (u:User {userID: $userID})-[r:HAS_TRAIT|HAS_CANDIDATE_TRAIT]->(t:Trait {traitID: $traitID})
            SET r.isActive = false, r.rejectionTimestamp = datetime()
            """ # Mark any relationship as inactive
            await session.execute_write(_execute_write_tx_ptfi, rel_reject_query, {"userID": str(user_id), "traitID": str(trait_id_in_pkg)})

        logger.info(f"{log_prefix}Trait {trait_id_in_pkg} status and properties updated in PKG. New status: {new_pkg_status}")
        return updated_trait_props

    except PKGServiceClientPTFIError as e: # Catch custom error from _execute_write_tx_ptfi
        logger.error(f"{log_prefix}PKG transaction error during trait update: {e}")
    except Exception as e:
        logger.error(f"{log_prefix}Unexpected error during PKG trait update: {e}", exc_info=True)

    return None # Return None if any PKG update fails

# Function for adding a completely new user-defined trait will also be needed here.
# async def add_new_user_defined_trait_to_pkg(...)
```
