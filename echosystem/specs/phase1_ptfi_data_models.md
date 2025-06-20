# Phase 1: Persona Trait Finalization Interface (PTFI) - Data Models

This document specifies the data models primarily relevant to the Persona Trait Finalization Interface (PTFI) module in EchoSphere's Phase 1. PTFI allows users to review, refine, and manage the trait candidates identified by MAIPP, and to define their own traits. The core data (traits themselves) will reside in the Persona Knowledge Graph (PKG) and the `ExtractedTraitCandidate` table. This document focuses on any specific data structures PTFI might need to manage the *refinement process* itself or user interactions, beyond what's already defined for MAIPP.

## 1. `UserRefinedTrait` Data Model (Reiteration & Refinement)

**Objective:** This model, previously conceptualized, captures the user's explicit feedback, modifications, and final decision on an `ExtractedTraitCandidate`, or a new trait defined directly by the user. While the PKG's `Trait` node will store the final confirmed state, this structure can serve as a detailed log of the refinement action or as a temporary holding structure before PKG update.

**Storage Consideration:** This could be stored in a **Relational Database (e.g., PostgreSQL)**, potentially in the same database as `ExtractedTraitCandidate` for easy joining and history tracking. It acts as an audit or detailed event log of user refinement actions.

| Attribute                   | Data Type (PostgreSQL)     | Constraints                                                                                                                                                              | Description                                                                                                                                                                                                                                                                                                                                                       | Indexing Suggestion                       |
|-----------------------------|----------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------|
| `refinementActionID`        | UUID                       | NOT NULL, PRIMARY KEY, DEFAULT gen_random_uuid()                                                                                                                         | Unique identifier for this specific refinement action/event.                                                                                                                                                                                                                                                                                                                      | Yes (Primary Key)                         |
| `userID`                    | UUID                       | NOT NULL, REFERENCES User(`userID`)                                                                                                                                      | Identifier of the user performing the refinement.                                                                                                                                                                                                                                                                                                                 | Yes (Foreign Key)                         |
| `traitID_in_pkg`            | UUID                       | NOT NULL                                                                                                                                                                 | The ID of the corresponding `Trait` node in the Persona Knowledge Graph. If it's a refinement of an `ExtractedTraitCandidate`, this would match `ExtractedTraitCandidate.candidateID` (which then becomes the `Trait.traitID` in PKG upon confirmation). For a new user-defined trait, this will be the ID assigned to the new `Trait` node in the PKG. | Yes (for linking to PKG)                  |
| `originalCandidateID`       | UUID                       | NULLABLE, REFERENCES ExtractedTraitCandidate(`candidateID`)                                                                                                              | If this refinement action pertains to an AI-suggested `ExtractedTraitCandidate`, this field links to it. NULL if it's a new trait defined purely by the user.                                                                                                                                                                                                   | Yes (Foreign Key)                         |
| `userDecision`              | VARCHAR(50)                | NOT NULL, CHECK (`userDecision` IN ('confirmed_asis', 'confirmed_modified', 'rejected', 'user_added_confirmed', 'superseded'))                                          | The user's final decision on this trait. 'confirmed_asis' (AI trait accepted as is), 'confirmed_modified' (AI trait accepted with changes), 'rejected' (AI trait rejected), 'user_added_confirmed' (new trait created by user). 'superseded' if a later refinement replaces this one. | Yes (for filtering actions)               |
| `refinedTraitName`          | VARCHAR(255)               | NULLABLE                                                                                                                                                                 | The user-modified name for the trait. If `userDecision` is 'confirmed_asis' or 'rejected', this might be NULL or store the original name. For 'user_added', this is the user's name for the trait.                                                                                                                                        |                                           |
| `refinedTraitDescription`   | TEXT                       | NULLABLE                                                                                                                                                                 | User's own description or modification of the AI-generated description. For 'user_added', this is the user's description.                                                                                                                                                                                                                                    |                                           |
| `refinedTraitCategory`      | VARCHAR(100)               | NULLABLE, CHECK (`refinedTraitCategory` IN ('LinguisticStyle', 'EmotionalResponsePattern', 'KnowledgeDomain', 'PhilosophicalStance', 'CommunicationStyle', 'BehavioralPattern', 'Interest', 'Skill', 'Other')) | User-modified category for the trait. For 'user_added', this is the user's chosen category.                                                                                                                                                                                                                                     |                                           |
| `userConfidenceRating`      | INTEGER                    | NULLABLE, CHECK (`userConfidenceRating` >= 1 AND `userConfidenceRating` <= 5)                                                                                            | User's subjective confidence in this trait's representation of them (e.g., on a 1-5 scale).                                                                                                                                                                                                                                                                       |                                           |
| `customizationNotes`        | TEXT                       | NULLABLE                                                                                                                                                                 | Any qualitative feedback, rationale, or specific contexts provided by the user for their decision or modification.                                                                                                                                                                                                                                               |                                           |
| `linkedEvidenceOverride`    | JSONB                      | NULLABLE                                                                                                                                                                 | If the user specifically validated, invalidated, or added new evidence snippets different from what AI suggested. Structure similar to `ExtractedTraitCandidate.supportingEvidenceSnippets`.                                                   |                                           |
| `actionTimestamp`           | TIMESTAMP WITH TIME ZONE   | NOT NULL, DEFAULT CURRENT_TIMESTAMP                                                                                                                                      | Timestamp of when this refinement action was recorded.                                                                                                                                                                                                                                                                                                            | Yes                                       |

**Conceptual JSON Representation of `UserRefinedTrait` (as an action log entry):**
```json
{
  "refinementActionID": "refineact_uuid_placeholder_001",
  "userID": "user_uuid_placeholder_123",
  "traitID_in_pkg": "trait_uuid_from_pkg_or_candidate_001", // This ID now refers to the Trait node in PKG
  "originalCandidateID": "traitcand_uuid_placeholder_001", // Link to the AI suggestion
  "userDecision": "confirmed_modified",
  "refinedTraitName": "Direct & Honest Communication", // User changed from AI's "Blunt Speech"
  "refinedTraitDescription": "User prefers to be seen as direct and honest, rather than simply blunt. Values clarity.",
  "refinedTraitCategory": "CommunicationStyle", // User might re-categorize
  "userConfidenceRating": 5,
  "customizationNotes": "AI suggestion was okay, but 'blunt' has negative connotations. This is more accurate.",
  "linkedEvidenceOverride": null, // User did not change the AI-linked evidence for this example
  "actionTimestamp": "2024-03-16T09:15:00Z"
}
```
**Note on Relationship to PKG:** The `UserRefinedTrait` table acts more like a log or event stream of user decisions. The actual, canonical state of a trait (its name, description, category, status as 'active' or 'rejected') is stored and updated directly in the **Persona Knowledge Graph's `Trait` nodes**. When a user refines a trait via PTFI:
1.  A `UserRefinedTrait` record can be created to log this specific interaction.
2.  The PTFI backend logic then issues commands to update the corresponding `Trait` node (and its relationships) in the PKG. For example, if `userDecision` is 'rejected', the `Trait` node's `status` in PKG might be set to 'rejected_by_user' or the `(User)-[:HAS_TRAIT]->(Trait)` relationship might be removed or flagged. If 'confirmed_modified', the `Trait` node's properties (`name`, `description`, `category`) in PKG are updated.

## 2. `UserInterfaceState` Data Model (Conceptual - for PTFI backend)

**Objective:** To potentially store user-specific UI preferences or temporary state related to the PTFI, such as filters applied, last viewed trait category, or pagination state for long lists of traits. This is optional and depends on UI complexity.

**Storage Consideration:** This is suitable for a **Key-Value Store (e.g., Redis)** for fast access and ephemeral data, or in the user's profile within a Document DB or Relational DB if persistence across sessions is highly important. For simplicity, not detailed with full SQL schema unless deemed critical.

**Attributes (Conceptual):**
*   `userID` (PK)
*   `ptfi_last_filter_category`: STRING
*   `ptfi_last_sort_order`: STRING
*   `ptfi_pending_review_trait_ids_order`: ARRAY<UUID> (Order in which user wants to see their pending traits)
*   `ptfi_ui_theme_preference`: STRING

**This model is highly dependent on specific UI features and may not require a rigid predefined schema initially.**

## 3. Data Models Already Defined (Leveraged by PTFI)

PTFI primarily interacts with and presents data from models defined for MAIPP:

*   **`ExtractedTraitCandidate` (from `phase1_maipp_data_models.md`):**
    *   PTFI reads records with `status: 'candidate'` or `'awaiting_refinement'` for a given `userID`.
    *   PTFI displays `traitName`, `traitDescription`, `traitCategory`, `supportingEvidenceSnippets`, and `confidenceScore` to the user.
    *   User actions via PTFI will lead to updating the `status` of these records (e.g., to 'refined_by_user', 'confirmed_by_user', 'rejected_by_user') or directly influencing the creation/update of `Trait` nodes in the PKG.

*   **Persona Knowledge Graph (PKG) (from `phase1_maipp_data_models.md`):**
    *   PTFI's core function is to enable user curation of the PKG.
    *   When a user confirms/modifies an AI trait, the PTFI backend updates the corresponding `Trait` node in the PKG (e.g., sets its `status` to 'active', updates `name`, `description`, `category` based on user input, adjusts `confidence` based on user rating).
    *   When a user rejects an AI trait, the `Trait` node in PKG might be marked with a 'rejected_by_user' status or the `(User)-[:HAS_TRAIT]->(Trait)` relationship might be removed/invalidated.
    *   When a user adds a new trait, PTFI backend creates a new `Trait` node in the PKG with `origin: 'user_defined'` and `status: 'active'`, along with user-provided properties.
    *   PTFI might also allow users to view and manage relationships between their `Trait` nodes and `Concept` nodes or `SourceDataReferenceNode`s.

## 4. Consent Linkage for PTFI

*   **User's access to PTFI implies consent to view their own persona data (candidates, PKG).** This is inherent in using the EchoSphere application.
*   **No new data is ingested by PTFI.** It operates on data already collected under consents managed by UDIM and processed by MAIPP under consents verified by MAIPP.
*   If PTFI were to introduce features that share trait information *externally* (e.g., "share my confirmed 'AI Expert' trait on my public Echo profile"), then that specific sharing action would require a new granular consent record managed by the Universal Consent Management Service (UCMS - Phase 4). PTFI would then call the Consent Verification API before performing such an action. For Phase 1, PTFI is focused on internal refinement.

## 5. Overall Storage Considerations for PTFI-specific Data

*   **`UserRefinedTrait` (Action Log):** PostgreSQL is appropriate due to its relational nature (linking to User, ExtractedTraitCandidate) and the need for reliable logging of user decisions. JSONB can handle flexible fields like `refinedTraitName` or `customizationNotes` which might be NULL if not changed by user.
*   **PKG Interaction:** All canonical trait information is stored and managed within the chosen Graph Database (Neo4j, Neptune) as part of the PKG. PTFI backend services are clients to this graph database.
*   **`UserInterfaceState` (if implemented):** Redis for ephemeral state, or extend User Profile table in PostgreSQL/MongoDB for persistent UI preferences.
```
