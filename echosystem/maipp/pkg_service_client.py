# echosystem/maipp/pkg_service_client.py
import logging
from typing import List, Dict, Any, Optional
import uuid
from neo4j import AsyncGraphDatabase, AsyncSession, ManagedTransaction, exceptions as neo4j_exceptions
from datetime import datetime # Ensure datetime is imported

# Assuming models.py is in the same directory or package structure allows this import
from .models import ExtractedTraitCandidateModel, EvidenceSnippet

logger = logging.getLogger(__name__)

# Global Neo4j driver instance - to be initialized by main_orchestrator
neo4j_driver: Optional[AsyncGraphDatabase.driver] = None

class PKGServiceClientError(Exception):
    """Custom exception for PKG Service Client errors."""
    pass

async def init_neo4j_driver(uri, auth_user, auth_password):
    """Initializes the global Neo4j driver."""
    global neo4j_driver
    if not uri or not auth_user or not auth_password:
        logger.error("Neo4j URI, user, or password not configured. PKG client cannot be initialized.")
        neo4j_driver = None # Ensure it's None if config is missing
        return
    try:
        neo4j_driver = AsyncGraphDatabase.driver(uri, auth=(auth_user, auth_password))
        await neo4j_driver.verify_connectivity() # Check connection
        logger.info(f"Neo4j driver initialized successfully for URI: {uri}")
    except neo4j_exceptions.ServiceUnavailable:
        logger.error(f"Neo4j Service Unavailable at URI: {uri}. Check DB status and credentials.", exc_info=True)
        neo4j_driver = None
    except neo4j_exceptions.AuthError:
        logger.error(f"Neo4j Authentication Error for URI: {uri}. Check credentials.", exc_info=True)
        neo4j_driver = None
    except Exception as e:
        logger.error(f"Failed to initialize Neo4j driver for URI {uri}: {e}", exc_info=True)
        neo4j_driver = None


async def close_neo4j_driver():
    """Closes the global Neo4j driver."""
    global neo4j_driver
    if neo4j_driver:
        try:
            await neo4j_driver.close()
            logger.info("Neo4j driver closed.")
        except Exception as e:
            logger.error(f"Error closing Neo4j driver: {e}", exc_info=True)
        finally:
            neo4j_driver = None


async def _execute_write_tx_fn(tx: ManagedTransaction, query: str, params: Dict[str, Any]):
    """Internal function to be passed to session.execute_write."""
    log_query = query.replace('\n', ' ').replace('\r', ' ') # Make query more log-friendly
    logger.debug(f"PKG Write Query: '{log_query[:150]}...' with params keys: {list(params.keys()) if params else '{}'}")
    try:
        result = await tx.run(query, params)
        summary = await result.consume() # Consume the result to ensure the transaction is fully processed
        logger.debug(f"PKG Write Query successful. Summary counters: {summary.counters if summary else 'N/A'}")
    except Exception as e:
        logger.error(f"Error executing PKG write tx query '{log_query[:150]}...': {e}", exc_info=True)
        # Re-raise to ensure the transaction is rolled back by Neo4j driver
        raise PKGServiceClientError(f"Transaction failed for query: {log_query[:100]}... Error: {str(e)}") from e


async def ensure_user_node_exists(user_id: uuid.UUID) -> bool:
    """Ensures a User node exists in PKG. Uses the global driver."""
    if not neo4j_driver:
        logger.error("Neo4j driver not initialized. Cannot ensure user node.")
        return False

    query = "MERGE (u:User {userID: $userID}) ON CREATE SET u.createdAt = datetime() RETURN u.userID"
    params = {"userID": str(user_id)}
    try:
        async with neo4j_driver.session() as session:
            await session.execute_write(_execute_write_tx_fn, query, params)
        logger.info(f"Ensured User node exists in PKG for userID: {user_id}")
        return True
    except Exception as e: # Catches PKGServiceClientError from _execute_write_tx_fn or session errors
        logger.error(f"Failed to ensure User node for userID {user_id}: {e}", exc_info=True)
        return False


async def add_trait_candidate_to_pkg(user_id: uuid.UUID, candidate: ExtractedTraitCandidateModel) -> bool:
    """Adds or updates a Trait candidate and its relationship to the User in PKG."""
    if not neo4j_driver:
        logger.error("Neo4j driver not initialized. Cannot add trait candidate.")
        return False

    # MERGE Trait node
    trait_query = """
    MERGE (t:Trait {traitID: $traitID})
    ON CREATE SET
        t.name = $name,
        t.description = $description,
        t.category = $category,
        t.status_in_pkg = 'candidate_from_maipp',
        t.maipp_confidence = $maipp_confidence,
        t.origin = $origin,
        t.originModels = $originModels,
        t.associatedFeatureSetIDs = $associatedFeatureSetIDs,
        t.creationTimestamp = datetime($creationTimestamp),
        t.lastUpdatedTimestamp = datetime($lastUpdatedTimestamp)
    ON MATCH SET
        t.name = $name, // MAIPP might have a better name/desc based on more data later
        t.description = $description,
        t.category = $category,
        t.maipp_confidence = $maipp_confidence, // Update confidence if re-processed
        t.originModels = $originModels,
        t.associatedFeatureSetIDs = $associatedFeatureSetIDs,
        t.lastUpdatedTimestamp = datetime($lastUpdatedTimestamp),
        t.status_in_pkg = CASE WHEN t.status_in_pkg STARTS WITH 'user_' THEN t.status_in_pkg ELSE 'candidate_from_maipp' END
    """
    trait_params = {
        "traitID": str(candidate.candidateID), "name": candidate.traitName,
        "description": candidate.traitDescription, "category": candidate.traitCategory,
        "maipp_confidence": candidate.confidenceScore, "origin": "ai_maipp", # General origin
        "originModels": candidate.originatingModels,
        "associatedFeatureSetIDs": [str(fid) for fid in candidate.associatedFeatureSetIDs],
        "creationTimestamp": candidate.creationTimestamp.isoformat(),
        "lastUpdatedTimestamp": candidate.lastUpdatedTimestamp.isoformat()
    }

    # MERGE User-Trait relationship
    user_trait_rel_query = """
    MATCH (u:User {userID: $userID})
    MATCH (t:Trait {traitID: $traitID})
    MERGE (u)-[r:HAS_CANDIDATE_TRAIT]->(t)
    ON CREATE SET
        r.confidenceScore = $maipp_confidence,
        r.addedByMAIPPTimestamp = datetime(),
        r.isActiveSuggestion = true
    ON MATCH SET
        r.confidenceScore = $maipp_confidence, // Update if MAIPP's confidence changes
        r.isActiveSuggestion = true, // Re-activate if it was perhaps deactivated
        r.lastObservedByMAIPPTimestamp = datetime()
    """
    user_trait_rel_params = {
        "userID": str(user_id), "traitID": str(candidate.candidateID),
        "maipp_confidence": candidate.confidenceScore
    }

    async with neo4j_driver.session() as session:
        try:
            await session.execute_write(_execute_write_tx_fn, trait_query, trait_params)
            await session.execute_write(_execute_write_tx_fn, user_trait_rel_query, user_trait_rel_params)

            # Link evidence snippets
            for evidence in candidate.supportingEvidenceSnippets:
                # Using a simple hash of content+detail for uniqueness of an evidence instance from a package.
                # In a real system, a more robust unique ID generation for evidence might be needed if content can be very large.
                evidence_content_key = f"{evidence.sourcePackageID}_{evidence.type}_{evidence.content[:50]}_{evidence.sourceDetail[:50]}"
                evidence_unique_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, evidence_content_key))

                evidence_node_query = """
                MERGE (sdr:SourceDataReferenceNode {referenceID: $referenceID})
                ON CREATE SET
                    sdr.sourceUserDataPackageID = $sourcePackageID,
                    sdr.snippet = $snippet,
                    sdr.mediaOffset = $mediaOffset, // Assuming this will be a JSON string or map
                    sdr.sourceDescription = $sourceDescription,
                    sdr.type = $type,
                    sdr.creationTimestamp = datetime()
                """
                evidence_params = {
                    "referenceID": evidence_unique_id,
                    "sourcePackageID": str(evidence.sourcePackageID),
                    "snippet": evidence.content,
                    "mediaOffset": None, # Placeholder for Phase 1; model has no mediaOffset field yet
                    "sourceDescription": evidence.sourceDetail,
                    "type": evidence.type
                }
                await session.execute_write(_execute_write_tx_fn, evidence_node_query, evidence_params)

                link_evidence_query = """
                MATCH (t:Trait {traitID: $traitID})
                MATCH (sdr:SourceDataReferenceNode {referenceID: $referenceID})
                MERGE (t)-[r:EVIDENCED_BY]->(sdr)
                ON CREATE SET
                    r.addedByMAIPPTimestamp = datetime(),
                    r.relevanceScore = $relevanceScore
                ON MATCH SET
                    r.relevanceScore = $relevanceScore // Update relevance if re-processed
                """
                link_evidence_params = {
                    "traitID": str(candidate.candidateID),
                    "referenceID": evidence_unique_id,
                    "relevanceScore": evidence.relevance_score
                }
                await session.execute_write(_execute_write_tx_fn, link_evidence_query, link_evidence_params)

            logger.info(f"Added/Updated Trait candidate {candidate.candidateID} and linked evidence for user {user_id} in PKG.")
            return True
        except Exception as e: # Catches PKGServiceClientError or session errors
            logger.error(f"Failed to add/update Trait candidate {candidate.candidateID} for user {user_id} in PKG: {e}", exc_info=True)
            return False

async def add_mentioned_concepts_to_pkg(user_id: uuid.UUID, concepts_info: List[Dict[str, Any]], source_package_id: uuid.UUID) -> bool:
    """Adds or updates Concept nodes and links them to the User."""
    if not neo4j_driver:
        logger.error("Neo4j driver not initialized. Cannot add concepts.")
        return False
    if not concepts_info: return True # No concepts to add

    success_count = 0
    async with neo4j_driver.session() as session:
        for concept_data in concepts_info: # concept_data e.g. {"name": "AI Ethics", "frequency": 2, "sentiment_avg": 0.7}
            concept_name_raw = concept_data.get("name")
            if not concept_name_raw or not isinstance(concept_name_raw, str): continue

            normalized_concept_name = concept_name_raw.strip().lower()
            if not normalized_concept_name: continue

            concept_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, normalized_concept_name)) # Consistent ID based on name

            concept_query = """
            MERGE (c:Concept {conceptID: $conceptID})
            ON CREATE SET
                c.name = $originalName,
                c.normalized_name = $normalizedName,
                c.creationTimestamp = datetime()
            ON MATCH SET
                c.name = $originalName // Update name if casing was different but normalized is same
            """
            concept_params = {
                "conceptID": concept_id,
                "originalName": concept_name_raw.strip(), # Store original casing for display
                "normalizedName": normalized_concept_name
            }

            user_concept_rel_query = """
            MATCH (u:User {userID: $userID})
            MATCH (c:Concept {conceptID: $conceptID})
            MERGE (u)-[r:MENTIONED_CONCEPT]->(c)
            ON CREATE SET
                r.frequency = $frequency,
                r.avgSentiment = $avgSentiment,
                r.firstMentionedTimestamp = datetime(),
                r.lastMentionedTimestamp = datetime(),
                r.sourcePackageIDs = [$sourcePackageID]
            ON MATCH SET
                r.frequency = COALESCE(r.frequency, 0) + $frequency,
                r.avgSentiment = CASE WHEN COALESCE(r.frequency, 0) + $frequency = 0 THEN $avgSentiment ELSE ($avgSentiment * $frequency + COALESCE(r.avgSentiment,0) * COALESCE(r.frequency, 0)) / (COALESCE(r.frequency, 0) + $frequency) END,
                r.lastMentionedTimestamp = datetime(),
                r.sourcePackageIDs = CASE WHEN $sourcePackageID IN COALESCE(r.sourcePackageIDs, []) THEN r.sourcePackageIDs ELSE COALESCE(r.sourcePackageIDs, []) + $sourcePackageID END
            """
            # Note: avgSentiment update is a weighted average. COALESCE handles cases where properties might be initially null.
            user_concept_rel_params = {
                "userID": str(user_id), "conceptID": concept_id,
                "frequency": concept_data.get("frequency", 1),
                "avgSentiment": concept_data.get("sentiment_avg"), # Can be null
                "sourcePackageID": str(source_package_id)
            }
            try:
                await session.execute_write(_execute_write_tx_fn, concept_query, concept_params)
                await session.execute_write(_execute_write_tx_fn, user_concept_rel_query, user_concept_rel_params)
                success_count +=1
            except Exception as e:
                logger.error(f"Failed to add concept '{concept_name_raw}' for user {user_id} to PKG: {e}", exc_info=True)

    logger.info(f"PKG: Processed {success_count}/{len(concepts_info)} concepts for user {user_id}, package {source_package_id}.")
    return success_count == len(concepts_info)

```
