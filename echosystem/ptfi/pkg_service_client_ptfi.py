# echosystem/ptfi/pkg_service_client_ptfi.py
import logging
import uuid
from typing import Dict, Any, Optional, List
from neo4j import AsyncSession, ManagedTransaction, AsyncDriver
from datetime import datetime, timezone

from .models import EvidenceSnippet

logger = logging.getLogger(__name__)

neo4j_driver_ptfi: Optional[AsyncDriver] = None # Initialized in db_clients.py by main_orchestrator

class PKGServiceClientPTFIError(Exception):
    pass

async def _execute_read_tx_ptfi(tx: ManagedTransaction, query: str, params: Dict[str, Any] = None):
    if params is None: params = {}
    log_query = query.replace('\n', ' ').replace('\r', ' ')
    logger.debug(f"PTFI PKG Read Query: '{log_query[:150]}...' with params keys: {list(params.keys())}")
    try:
        result = await tx.run(query, params)
        return await result.data() # Return list of records (dictionaries)
    except Exception as e:
        logger.error(f"Error executing PTFI PKG read tx query '{log_query[:150]}...': {e}", exc_info=True)
        raise PKGServiceClientPTFIError(f"Read transaction failed: {str(e)}") from e

async def _execute_write_tx_ptfi(tx: ManagedTransaction, query: str, params: Dict[str, Any] = None):
    if params is None: params = {}
    log_query = query.replace('\n', ' ').replace('\r', ' ')
    logger.debug(f"PTFI PKG Write Query: '{log_query[:150]}...' with params keys: {list(params.keys())}")
    try:
        result = await tx.run(query, params)
        summary = await result.consume()
        logger.debug(f"PTFI PKG Write Query successful. Summary: {summary.counters if summary else 'N/A'}")
        # For queries that RETURN data (like MERGE ... RETURN), we need the data.
        # The result object itself can be used to fetch data if needed, but consume() is for summaries.
        # To get data from a write that returns, use: `records = await result.data()` before `consume()`
        # For simplicity, if a write needs to return data, it will be handled in the specific function.
        return summary
    except Exception as e:
        logger.error(f"Error executing PTFI PKG write tx query '{log_query[:150]}...': {e}", exc_info=True)
        raise PKGServiceClientPTFIError(f"Write transaction failed: {str(e)}") from e


async def update_pkg_trait_status_and_properties(
    session: AsyncSession,
    user_id: uuid.UUID,
    trait_id_in_pkg: uuid.UUID,
    user_decision: str,
    modifications: Optional[Dict[str, Any]] = None,
    original_trait_details: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    log_prefix = f"[User:{user_id}][Trait:{trait_id_in_pkg}] PKG Update - "
    logger.info(f"{log_prefix}Action: {user_decision}, Modifications: {modifications}")

    # 1. Ensure User node exists (idempotent)
    user_node_query = "MERGE (u:User {userID: $userID}) ON CREATE SET u.createdAt = datetime() RETURN u.userID"
    try:
        await session.execute_write(_execute_write_tx_ptfi, user_node_query, {"userID": str(user_id)})
    except PKGServiceClientPTFIError as e:
        logger.error(f"{log_prefix}Failed to ensure User node exists. Error: {e}")
        return None

    new_pkg_status = ""
    origin_type = ""
    set_properties_cypher = ["t.lastRefinedTimestamp = datetime($lastRefinedTimestamp)"]
    params = {
        "traitID": str(trait_id_in_pkg),
        "userID": str(user_id),
        "lastRefinedTimestamp": datetime.now(timezone.utc).isoformat()
    }

    # Determine base properties from original or modifications
    current_name = (modifications.get("refinedTraitName")
                    if modifications and modifications.get("refinedTraitName") is not None
                    else original_trait_details.get("traitName"))
    current_description = (modifications.get("refinedTraitDescription")
                           if modifications and modifications.get("refinedTraitDescription") is not None
                           else original_trait_details.get("traitDescription"))
    current_category = (modifications.get("refinedTraitCategory")
                        if modifications and modifications.get("refinedTraitCategory") is not None
                        else original_trait_details.get("traitCategory"))

    params.update({
        "name": current_name,
        "description": current_description,
        "category": current_category
    })
    set_properties_cypher.extend(["t.name = $name", "t.description = $description", "t.category = $category"])


    if user_decision == "confirmed_asis":
        new_pkg_status = "active_user_confirmed"
        origin_type = "ai_confirmed_user"
        # User confidence might still be set even if 'as_is'
        if modifications and modifications.get("userConfidenceRating") is not None:
            set_properties_cypher.append("t.userConfidence = $userConfidence")
            params["userConfidence"] = modifications["userConfidenceRating"]
        elif original_trait_details and original_trait_details.get("confidenceScore") is not None: # Use MAIPP confidence if user doesn't set
             set_properties_cypher.append("t.maipp_confidence = $maipp_confidence") # Keep original MAIPP confidence
             params["maipp_confidence"] = original_trait_details.get("confidenceScore")


    elif user_decision == "confirmed_modified":
        new_pkg_status = "active_user_modified"
        origin_type = "ai_refined_user"
        if not modifications: return None # Should be caught by API validation

        if modifications.get("userConfidenceRating") is not None:
            set_properties_cypher.append("t.userConfidence = $userConfidence")
            params["userConfidence"] = modifications["userConfidenceRating"]

    elif user_decision == "rejected":
        new_pkg_status = "rejected_by_user"
        # No origin_type change needed, trait properties (name, desc, cat) remain as MAIPP suggested.
    else:
        logger.error(f"{log_prefix}Unknown user_decision: {user_decision}")
        return None

    set_properties_cypher.append("t.status_in_pkg = $new_pkg_status")
    params["new_pkg_status"] = new_pkg_status
    if origin_type: # Only set origin if it's determined (i.e., not for rejection)
        set_properties_cypher.append("t.origin = $origin_type")
        params["origin_type"] = origin_type

    final_set_clause_str = ", ".join(set_properties_cypher)
    # MERGE Trait node: MAIPP should have created it. If not, this creates a shell.
    # This assumes MAIPP creates a :Trait node with status 'candidate_from_maipp'.
    trait_update_query = f"""
    MERGE (t:Trait {{traitID: $traitID}})
    ON CREATE SET t.creationTimestamp = datetime(), {final_set_clause_str}
    ON MATCH SET {final_set_clause_str}
    RETURN t.traitID AS traitID_in_pkg, t.name AS name, t.description AS description,
           t.category AS category, t.status_in_pkg AS status_in_pkg, t.origin AS origin,
           t.userConfidence AS userConfidence, t.lastRefinedTimestamp AS lastRefinedTimestamp
    """

    updated_trait_props_list: List[Dict[str,Any]] = []
    try:
        # Using a single transaction for all PKG updates for this action
        async def transaction_work(tx: ManagedTransaction):
            result_cursor = await _execute_write_tx_ptfi(tx, trait_update_query, params)
            nonlocal updated_trait_props_list
            updated_trait_props_list = await result_cursor.data()

            if user_decision in ["confirmed_asis", "confirmed_modified"]:
                rel_query = """
                MATCH (u:User {userID: $userID}), (t:Trait {traitID: $traitID})
                OPTIONAL MATCH (u)-[old_cand_r:HAS_CANDIDATE_TRAIT]->(t) DELETE old_cand_r
                MERGE (u)-[r:HAS_TRAIT]->(t)
                ON CREATE SET r.source = $origin, r.isActive = true, r.addedTimestamp = $lastRefinedTimestamp, r.lastConfirmedTimestamp = $lastRefinedTimestamp
                ON MATCH SET r.source = $origin, r.isActive = true, r.lastConfirmedTimestamp = $lastRefinedTimestamp
                """
                await _execute_write_tx_ptfi(tx, rel_query, {
                    "userID": str(user_id), "traitID": str(trait_id_in_pkg),
                    "origin": origin_type, "lastRefinedTimestamp": params["lastRefinedTimestamp"]
                })
            elif user_decision == "rejected":
                # Mark :HAS_TRAIT as inactive if it exists, or :HAS_CANDIDATE_TRAIT
                rel_reject_query = """
                MATCH (u:User {userID: $userID})-[r:HAS_TRAIT|HAS_CANDIDATE_TRAIT]->(t:Trait {traitID: $traitID})
                SET r.isActive = false, r.rejectionTimestamp = $lastRefinedTimestamp
                """
                await _execute_write_tx_ptfi(tx, rel_reject_query, {
                    "userID": str(user_id), "traitID": str(trait_id_in_pkg),
                    "lastRefinedTimestamp": params["lastRefinedTimestamp"]
                })

        await session.execute_write(transaction_work) # Neo4j driver handles actual tx commit/rollback

        logger.info(f"{log_prefix}Trait {trait_id_in_pkg} status/properties updated in PKG. New status: {new_pkg_status}")
        return updated_trait_props_list[0] if updated_trait_props_list else None

    except PKGServiceClientPTFIError as e:
        logger.error(f"{log_prefix}PKG transaction error during trait update: {e}")
    except Exception as e:
        logger.error(f"{log_prefix}Unexpected error during PKG trait update: {e}", exc_info=True)
    return None


async def add_custom_trait_to_pkg(
    session: AsyncSession, user_id: uuid.UUID, trait_name: str, trait_category: str,
    trait_description: Optional[str] = None, user_confidence: Optional[int] = None,
    user_provided_evidence_texts: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    new_trait_id = uuid.uuid4()
    log_prefix = f"[User:{user_id}][CustomTrait:{new_trait_id}] PKG Add - "
    logger.info(f"{log_prefix}Adding custom trait '{trait_name}'.")

    async def transaction_work(tx: ManagedTransaction):
        # Ensure User node exists
        user_node_query = "MERGE (u:User {userID: $userID}) ON CREATE SET u.createdAt = datetime() RETURN u.userID"
        await _execute_write_tx_ptfi(tx, user_node_query, {"userID": str(user_id)})

        current_iso_timestamp = datetime.now(timezone.utc).isoformat()
        create_trait_query = """
        CREATE (t:Trait {
            traitID: $traitID, name: $name, description: $description, category: $category,
            status_in_pkg: 'active', origin: 'user_defined', userConfidence: $userConfidence,
            creationTimestamp: datetime($creationTimestamp), lastRefinedTimestamp: datetime($lastRefinedTimestamp)
        })
        RETURN t.traitID AS traitID_in_pkg, t.name AS name, t.description AS description,
               t.category AS category, t.status_in_pkg AS status_in_pkg, t.origin AS origin,
               t.userConfidence AS userConfidence, t.lastRefinedTimestamp AS lastRefinedTimestamp
        """
        trait_params = {
            "traitID": str(new_trait_id), "name": trait_name, "description": trait_description,
            "category": trait_category, "userConfidence": user_confidence,
            "creationTimestamp": current_iso_timestamp, "lastRefinedTimestamp": current_iso_timestamp
        }
        result_cursor = await _execute_write_tx_ptfi(tx, create_trait_query, trait_params)
        new_trait_props_list = await result_cursor.data()

        link_trait_to_user_query = """
        MATCH (u:User {userID: $userID}), (t:Trait {traitID: $traitID})
        MERGE (u)-[r:HAS_TRAIT]->(t)
        SET r.source = 'user_defined', r.isActive = true,
            r.addedTimestamp = datetime($lastRefinedTimestamp),
            r.strength = $userConfidenceNormalized,
            r.lastConfirmedTimestamp = datetime($lastRefinedTimestamp)
        """
        link_params = {
            "userID": str(user_id), "traitID": str(new_trait_id),
            "userConfidenceNormalized": (user_confidence / 5.0) if user_confidence is not None else None,
            "lastRefinedTimestamp": current_iso_timestamp
        }
        await _execute_write_tx_ptfi(tx, link_trait_to_user_query, link_params)

        if user_provided_evidence_texts:
            user_input_source_package_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"user_input_{user_id}")
            for text_evidence in user_provided_evidence_texts:
                if not text_evidence or not text_evidence.strip(): continue
                evidence_content_key = f"{user_input_source_package_id}_user_text_{text_evidence[:50]}"
                evidence_node_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, evidence_content_key))
                evidence_node_query = """
                MERGE (sdr:SourceDataReferenceNode {referenceID: $referenceID})
                ON CREATE SET
                    sdr.sourceUserDataPackageID = $sourcePackageID, sdr.snippet = $snippet,
                    sdr.type = 'user_provided_text', sdr.sourceDescription = $sourceDescription,
                    sdr.creationTimestamp = datetime()
                """
                evidence_params = {
                    "referenceID": evidence_node_id, "sourcePackageID": str(user_input_source_package_id),
                    "snippet": text_evidence.strip(), "sourceDescription": f"User-provided text for trait: {trait_name}"
                }
                await _execute_write_tx_ptfi(tx, evidence_node_query, evidence_params)
                link_evidence_query = """
                MATCH (t:Trait {traitID: $traitID}), (sdr:SourceDataReferenceNode {referenceID: $referenceID})
                MERGE (t)-[r:EVIDENCED_BY]->(sdr) SET r.addedByPTFITimestamp = datetime()
                """
                await _execute_write_tx_ptfi(tx, link_evidence_query, {"traitID": str(new_trait_id), "referenceID": evidence_node_id})

        return new_trait_props_list[0] if new_trait_props_list else None

    try:
        return await session.execute_write(transaction_work)
    except PKGServiceClientPTFIError as e:
        logger.error(f"{log_prefix}PKG transaction error creating custom trait '{trait_name}': {e}")
    except Exception as e:
        logger.error(f"{log_prefix}Unexpected error creating custom PKG trait '{trait_name}': {e}", exc_info=True)
    return None


async def update_communication_style_in_pkg(
    session: AsyncSession,
    user_id: uuid.UUID,
    style_dimension_name: str, # e.g., "FormalityLevel", "HumorUsage"
    new_value: Any # e.g., "formal", "high", 0.8
) -> Optional[Dict[str, Any]]:
    """Updates or creates a communication style element and links it to the user."""
    log_prefix = f"[User:{user_id}][CommStyle:{style_dimension_name}] PKG Update - "
    logger.info(f"{log_prefix}Setting value to '{new_value}'.")

    # Ensure User node exists
    user_node_query = "MERGE (u:User {userID: $userID}) ON CREATE SET u.createdAt = datetime() RETURN u.userID"
    try:
        await session.execute_write(_execute_write_tx_ptfi, user_node_query, {"userID": str(user_id)})
    except PKGServiceClientPTFIError as e:
        logger.error(f"{log_prefix}Failed to ensure User node exists. Error: {e}")
        return None

    # MERGE CommunicationStyleElement node, then MERGE relationship and set/update value on relationship
    # This approach keeps the :CommunicationStyleElement nodes generic (e.g., "Formality")
    # and the user-specific value on the relationship.
    style_element_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, style_dimension_name)) # Consistent ID

    async def transaction_work(tx: ManagedTransaction):
        # Merge the element node
        query_cse_node = """
        MERGE (cse:CommunicationStyleElement {styleElementID: $styleElementID})
        ON CREATE SET cse.name = $name, cse.creationTimestamp = datetime()
        RETURN cse.name
        """
        await _execute_write_tx_ptfi(tx, query_cse_node, {"styleElementID": style_element_id, "name": style_dimension_name})

        # Merge the relationship and set/update its value property
        query_rel = """
        MATCH (u:User {userID: $userID})
        MATCH (cse:CommunicationStyleElement {styleElementID: $styleElementID})
        MERGE (u)-[r:ADOPTS_COMMUNICATION_STYLE]->(cse)
        SET r.value = $value, r.lastUpdated = datetime()
        RETURN cse.name AS styleName, r.value AS styleValue, r.lastUpdated AS lastUpdated
        """
        params = {
            "userID": str(user_id),
            "styleElementID": style_element_id,
            "value": new_value # This can be string, number, or even JSON string for complex values
        }
        result_cursor = await _execute_write_tx_ptfi(tx, query_rel, params)
        records = await result_cursor.data()
        return records[0] if records else None

    try:
        updated_style = await session.execute_write(transaction_work)
        if updated_style:
            logger.info(f"{log_prefix}Communication style '{style_dimension_name}' updated to '{new_value}'.")
            return updated_style
        else:
            logger.error(f"{log_prefix}Failed to update communication style '{style_dimension_name}'.")
            return None
    except PKGServiceClientPTFIError as e:
        logger.error(f"{log_prefix}PKG transaction error updating communication style '{style_dimension_name}': {e}")
    except Exception as e:
        logger.error(f"{log_prefix}Unexpected error updating communication style '{style_dimension_name}': {e}", exc_info=True)
    return None

```
