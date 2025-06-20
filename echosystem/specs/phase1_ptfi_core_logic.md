# Phase 1: Persona Trait Finalization Interface (PTFI) - Core Logic

This document outlines the core logical flows for the Persona Trait Finalization Interface (PTFI) module in EchoSphere's Phase 1. PTFI enables users to review, modify, confirm, reject, or add persona traits, effectively curating their Persona Knowledge Graph (PKG). The logic described here primarily pertains to the backend operations triggered by user actions in a UI.

## Overall PTFI User Interaction Flow (Conceptual Backend Logic)

**Trigger:** User interacts with the PTFI section of the EchoSphere application.

**Core Components Involved:**
*   PTFI Backend Service (this logic)
*   `ExtractedTraitCandidate` data store (PostgreSQL)
*   Persona Knowledge Graph (PKG) service (Graph Database, e.g., Neo4j)
*   `UserRefinedTrait` data store (PostgreSQL - for logging refinement actions)

## 1. Fetching AI Trait Candidates for User Review

**Objective:** To retrieve and present AI-identified trait candidates to the user for their review and action.

*   **Input:** `userID` (from authenticated user session).
*   **Logic:**
    ```pseudocode
    FUNCTION GET_TRAIT_CANDIDATES_FOR_REVIEW(userID, filters, sortOptions):
        // 1. Authenticate user and authorize access (assumed done by API gateway/middleware)

        // 2. Query ExtractedTraitCandidate store
        //    Fetches candidates typically with status 'candidate' or 'awaiting_refinement'.
        //    Filters might include traitCategory, confidenceScore range, etc.
        //    SortOptions might be by confidenceScore (desc), creationTimestamp, etc.
        traitCandidatesFromDB = QUERY_EXTRACTED_TRAIT_CANDIDATES(
            userID = userID,
            status_in = ['candidate', 'awaiting_refinement'],
            filters = filters,
            sort = sortOptions
        )

        // 3. Format candidates for presentation
        //    This might involve joining with other data or preparing evidence snippets.
        presentableCandidates = []
        FOR EACH candidate IN traitCandidatesFromDB:
            // Ensure evidence snippets are well-formatted, perhaps fetching actual content if snippets are just references.
            // For Phase 1, snippets are assumed to be directly usable from ExtractedTraitCandidate.supportingEvidenceSnippets.
            presentableCandidates.ADD(FORMAT_CANDIDATE_FOR_UI(candidate))
        END FOR

        RETURN presentableCandidates

    OUTPUT: List of formatted `ExtractedTraitCandidate` objects for UI display.
    ```

## 2. User Confirms an AI Trait (As Is or Modified)

**Objective:** To process a user's decision to confirm an AI-suggested trait, either as it was suggested or with user modifications.

*   **Input:** `userID`, `candidateID` (of the `ExtractedTraitCandidate`), `userDecision` ('confirmed_asis' or 'confirmed_modified'), `modifications` (optional JSON object with fields like `refinedTraitName`, `refinedTraitDescription`, `refinedTraitCategory`, `userConfidenceRating`, `customizationNotes`).
*   **Logic:**
    ```pseudocode
    FUNCTION CONFIRM_AI_TRAIT(userID, candidateID, userDecision, modifications):
        // 1. Fetch the original ExtractedTraitCandidate
        originalCandidate = GET_EXTRACTED_TRAIT_CANDIDATE_BY_ID(candidateID)
        IF originalCandidate IS NULL OR originalCandidate.userID IS NOT userID:
            RETURN HTTP_404_NOT_FOUND("Trait candidate not found or access denied.")
        END IF

        // 2. Determine final trait properties based on userDecision and modifications
        finalTraitProperties = {
            traitID: originalCandidate.candidateID, // Use candidateID as the canonical Trait ID in PKG
            name: originalCandidate.traitName,
            description: originalCandidate.traitDescription,
            category: originalCandidate.traitCategory,
            origin: (userDecision == 'confirmed_asis' ? 'ai_confirmed_user' : 'ai_refined_user'),
            status_in_pkg: 'active', // Mark as active in PKG
            confidence_in_pkg: modifications.userConfidenceRating OR originalCandidate.confidenceScore,
            lastRefinedTimestamp: CURRENT_TIMESTAMP(),
            creationTimestamp: originalCandidate.creationTimestamp // Retain original creation time of candidate idea
        }
        IF userDecision == 'confirmed_modified':
            IF modifications.refinedTraitName IS NOT NULL:
                finalTraitProperties.name = modifications.refinedTraitName
            END IF
            IF modifications.refinedTraitDescription IS NOT NULL:
                finalTraitProperties.description = modifications.refinedTraitDescription
            END IF
            IF modifications.refinedTraitCategory IS NOT NULL:
                finalTraitProperties.category = modifications.refinedTraitCategory
            END IF
        END IF

        // 3. Update/Create Trait Node in Persona Knowledge Graph (PKG)
        //    This operation should be idempotent if possible (e.g., "CREATE OR MERGE").
        pkgResult = PKG_CREATE_OR_UPDATE_TRAIT_NODE(userID, finalTraitProperties)
        IF pkgResult.isError:
            LOG_PKG_ERROR("Failed to update PKG for trait " + finalTraitProperties.traitID + ": " + pkgResult.error)
            RETURN HTTP_500_INTERNAL_SERVER_ERROR("Failed to save trait confirmation to knowledge graph.")
        END IF

        // 4. Link Trait node in PKG to existing evidence (SourceDataReferenceNode)
        //    Evidence was already linked to the candidate concept; now solidify this for the confirmed Trait.
        //    This step might be part of PKG_CREATE_OR_UPDATE_TRAIT_NODE or separate.
        FOR EACH evidence IN originalCandidate.supportingEvidenceSnippets:
            evidenceNode = GET_OR_CREATE_EVIDENCE_NODE_IN_PKG(evidence.sourcePackageID, evidence.content_or_reference)
            PKG_LINK_TRAIT_TO_EVIDENCE(finalTraitProperties.traitID, evidenceNode.referenceID, {relevance: evidence.relevanceScore_if_any})
        END FOR

        // 5. Update status of the ExtractedTraitCandidate
        UPDATE_EXTRACTED_TRAIT_CANDIDATE_STATUS(candidateID, 'confirmed_by_user')

        // 6. Log the refinement action (optional but good for audit)
        CREATE_USER_REFINED_TRAIT_LOG_ENTRY(
            userID = userID,
            traitID_in_pkg = finalTraitProperties.traitID,
            originalCandidateID = candidateID,
            userDecision = userDecision,
            refinedTraitName = finalTraitProperties.name,
            refinedTraitDescription = finalTraitProperties.description,
            refinedTraitCategory = finalTraitProperties.category,
            userConfidenceRating = modifications.userConfidenceRating,
            customizationNotes = modifications.customizationNotes,
            actionTimestamp = CURRENT_TIMESTAMP()
        )

        RETURN HTTP_200_OK({message: "Trait confirmed successfully.", trait: finalTraitProperties})

    OUTPUT: Success message with confirmed trait details OR Error Response.
    ```

## 3. User Rejects an AI Trait

**Objective:** To process a user's decision to reject an AI-suggested trait.

*   **Input:** `userID`, `candidateID` (of the `ExtractedTraitCandidate`), `userDecision` ('rejected'), `rejectionReason` (optional string from user).
*   **Logic:**
    ```pseudocode
    FUNCTION REJECT_AI_TRAIT(userID, candidateID, rejectionReason):
        // 1. Fetch the original ExtractedTraitCandidate
        originalCandidate = GET_EXTRACTED_TRAIT_CANDIDATE_BY_ID(candidateID)
        IF originalCandidate IS NULL OR originalCandidate.userID IS NOT userID:
            RETURN HTTP_404_NOT_FOUND("Trait candidate not found or access denied.")
        END IF

        // 2. Update/Mark Trait Node in Persona Knowledge Graph (PKG) as rejected
        //    Option 1: Change status of existing Trait node (if it was created from candidate).
        //    Option 2: Ensure no active Trait node for this candidateID exists or remove/flag relationship.
        //    For Phase 1, let's assume we mark its status in PKG.
        pkgResult = PKG_UPDATE_TRAIT_STATUS(userID, originalCandidate.candidateID, 'rejected_by_user')
        // This might involve removing the (User)-[:HAS_TRAIT]->(Trait) relationship or flagging it.
        IF pkgResult.isError:
            LOG_PKG_ERROR("Failed to update PKG for rejected trait " + originalCandidate.candidateID + ": " + pkgResult.error)
            // Non-critical failure for rejection, proceed to update candidate status.
        END IF

        // 3. Update status of the ExtractedTraitCandidate
        UPDATE_EXTRACTED_TRAIT_CANDIDATE_STATUS(candidateID, 'rejected_by_user')

        // 4. Log the refinement action
        CREATE_USER_REFINED_TRAIT_LOG_ENTRY(
            userID = userID,
            traitID_in_pkg = originalCandidate.candidateID, // The ID it would have had or has in PKG
            originalCandidateID = candidateID,
            userDecision = 'rejected',
            customizationNotes = rejectionReason,
            actionTimestamp = CURRENT_TIMESTAMP()
        )

        RETURN HTTP_200_OK({message: "Trait rejected successfully."})

    OUTPUT: Success message OR Error Response.
    ```

## 4. User Adds a New Custom Trait

**Objective:** To allow users to define and add entirely new traits not suggested by AI.

*   **Input:** `userID`, `traitDetails` (JSON object with `traitName`, `traitDescription`, `traitCategory`, `userConfidenceRating`, optional `supportingEvidenceSnippets` provided by user).
*   **Logic:**
    ```pseudocode
    FUNCTION ADD_USER_DEFINED_TRAIT(userID, traitDetails):
        // 1. Validate input traitDetails (name, category are required)
        IF traitDetails.traitName IS NULL OR EMPTY OR traitDetails.traitCategory IS NULL OR EMPTY:
            RETURN HTTP_400_BAD_REQUEST("Trait name and category are required for user-defined traits.")
        END IF

        // 2. Construct properties for the new Trait node in PKG
        newTraitID = GENERATE_UUID() // Generate a new unique ID for this trait
        newTraitProperties = {
            traitID: newTraitID,
            name: traitDetails.traitName,
            description: traitDetails.traitDescription,
            category: traitDetails.traitCategory,
            origin: 'user_defined',
            status_in_pkg: 'active', // User-defined traits are active by default
            confidence_in_pkg: traitDetails.userConfidenceRating OR 5.0, // Default to high confidence
            lastRefinedTimestamp: CURRENT_TIMESTAMP(),
            creationTimestamp: CURRENT_TIMESTAMP()
        }

        // 3. Create Trait Node in Persona Knowledge Graph (PKG)
        pkgResult = PKG_CREATE_OR_UPDATE_TRAIT_NODE(userID, newTraitProperties) // This will create a new node and link it to the user
        IF pkgResult.isError:
            LOG_PKG_ERROR("Failed to create user-defined trait in PKG: " + pkgResult.error)
            RETURN HTTP_500_INTERNAL_SERVER_ERROR("Failed to save new trait to knowledge graph.")
        END IF

        // 4. (Optional) Link to user-provided evidence if any
        IF traitDetails.supportingEvidenceSnippets IS NOT EMPTY:
            FOR EACH evidence IN traitDetails.supportingEvidenceSnippets:
                // User needs a way to specify sourcePackageID or it's a free-text evidence
                // For Phase 1, user-provided evidence might just be text stored directly with the trait or linked to a generic "user_input" source.
                evidenceNode = GET_OR_CREATE_EVIDENCE_NODE_IN_PKG(evidence.sourcePackageID_if_known, evidence.content)
                PKG_LINK_TRAIT_TO_EVIDENCE(newTraitID, evidenceNode.referenceID)
            END FOR
        END IF

        // 5. Log the refinement action
        CREATE_USER_REFINED_TRAIT_LOG_ENTRY(
            userID = userID,
            traitID_in_pkg = newTraitID,
            originalCandidateID = NULL,
            userDecision = 'user_added_confirmed',
            refinedTraitName = newTraitProperties.name,
            refinedTraitDescription = newTraitProperties.description,
            refinedTraitCategory = newTraitProperties.category,
            userConfidenceRating = newTraitProperties.confidence_in_pkg,
            customizationNotes = "User directly added this trait.",
            actionTimestamp = CURRENT_TIMESTAMP()
        )

        RETURN HTTP_201_CREATED({message: "User-defined trait added successfully.", trait: newTraitProperties})

    OUTPUT: Success message with new trait details OR Error Response.
    ```

## 5. (Conceptual) User Modifies Communication Style Preferences

**Objective:** To allow users to adjust global or contextual communication style elements (e.g., formality, humor).

*   **Input:** `userID`, `styleElementModifications` (JSON object, e.g., `{"FormalityLevel": "informal", "HumorUsage": "high", "EmojiPreference": 0.8}`).
*   **Logic:**
    ```pseudocode
    FUNCTION UPDATE_COMMUNICATION_STYLE_PREFERENCES(userID, styleElementModifications):
        // 1. For each style element in styleElementModifications:
        FOR EACH elementName, elementValue IN styleElementModifications:
            // 2. Get or Create CommunicationStyleElement node in PKG
            styleNode = PKG_GET_OR_CREATE_COMM_STYLE_NODE(elementName)

            // 3. Update/Create relationship (User)-[:ADOPTS_COMMUNICATION_STYLE]->(CommunicationStyleElement)
            //    The 'value' of the style element is often stored on the node itself, or on the relationship.
            //    For this example, assume value is on the node, and relationship just establishes preference.
            PKG_UPDATE_COMM_STYLE_NODE_VALUE(styleNode.styleElementID, elementValue) // If value is on node

            PKG_CREATE_OR_UPDATE_USER_COMM_STYLE_RELATIONSHIP(
                userID,
                styleNode.styleElementID,
                {preferenceStrength: 1.0} // Default, or user can specify strength
            )
        END FOR

        LOG_INFO("Communication style preferences updated for user " + userID)
        RETURN HTTP_200_OK({message: "Communication style preferences updated."})

    OUTPUT: Success message OR Error Response.
    ```

**Helper Function Signatures (Conceptual - interacting with data stores/PKG):**
*   `QUERY_EXTRACTED_TRAIT_CANDIDATES(userID, status_in, filters, sortOptions)`: Fetches from PostgreSQL.
*   `FORMAT_CANDIDATE_FOR_UI(candidate)`: Prepares data for display.
*   `GET_EXTRACTED_TRAIT_CANDIDATE_BY_ID(candidateID)`: Fetches from PostgreSQL.
*   `PKG_CREATE_OR_UPDATE_TRAIT_NODE(userID, traitProperties)`: Interacts with Graph DB (Neo4j/Neptune). Creates `Trait` node and `(User)-[:HAS_TRAIT]->(Trait)` relationship.
*   `PKG_GET_OR_CREATE_EVIDENCE_NODE_IN_PKG(sourcePackageID, content_or_reference)`: Interacts with Graph DB.
*   `PKG_LINK_TRAIT_TO_EVIDENCE(traitID, evidenceNodeID, properties)`: Interacts with Graph DB.
*   `UPDATE_EXTRACTED_TRAIT_CANDIDATE_STATUS(candidateID, newStatus)`: Updates PostgreSQL.
*   `CREATE_USER_REFINED_TRAIT_LOG_ENTRY(...)`: Saves to `UserRefinedTrait` table in PostgreSQL.
*   `PKG_UPDATE_TRAIT_STATUS(userID, traitID, newStatusInPKG)`: Updates `Trait` node status or relationship in Graph DB.
*   `GENERATE_UUID()`: Generates a new unique identifier.
*   `PKG_GET_OR_CREATE_COMM_STYLE_NODE(elementName)`: Interacts with Graph DB.
*   `PKG_UPDATE_COMM_STYLE_NODE_VALUE(styleElementID, newValue)`: Interacts with Graph DB.
*   `PKG_CREATE_OR_UPDATE_USER_COMM_STYLE_RELATIONSHIP(userID, styleElementID, properties)`: Interacts with Graph DB.
```
