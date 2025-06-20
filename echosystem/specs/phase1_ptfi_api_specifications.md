# Phase 1: Persona Trait Finalization Interface (PTFI) - API & Interaction Specifications

This document details the Application Programming Interfaces (APIs) for the backend service of the Persona Trait Finalization Interface (PTFI) module in EchoSphere's Phase 1. These APIs are primarily consumed by the PTFI frontend UI, enabling users to review, refine, and manage their persona traits.

**General API Design Principles (Consistent with UDIM):**

*   **Statelessness:** APIs are stateless.
*   **Clear Error Messages:** Consistent JSON error structure: `{"error": {"code": ..., "message": ..., "details": ...}}`.
*   **Security:** HTTPS for all communication. Robust authentication and authorization.
*   **Versioning:** All API endpoints are versioned (e.g., `/v1/`).
*   **Authentication:** All user-facing PTFI APIs MUST be protected by OAuth 2.0 Bearer Tokens, ensuring only the authenticated user can access and manage their own persona traits. The token must have appropriate scopes (e.g., `persona:read_traits`, `persona:manage_traits`).

---

## I. PTFI Backend API Endpoints (User-Facing via UI)

These endpoints are called by the PTFI frontend to interact with the user's persona data, specifically `ExtractedTraitCandidate` records and the Persona Knowledge Graph (PKG).

### 1. Fetch Trait Candidates for Review

*   **Endpoint:** `GET /v1/users/{userID}/persona/traits/candidates`
*   **Description:** Retrieves a list of AI-identified `ExtractedTraitCandidate` records for the specified user that are pending review or refinement.
*   **Authentication:** OAuth 2.0 Bearer Token. The `userID` in the path MUST match the `userID` claim in the token.
*   **Path Parameters:**
    *   `userID` (UUID, required): The ID of the user whose trait candidates are to be fetched.
*   **Query Parameters (Optional):**
    *   `status` (String, optional): Filter by candidate status (e.g., `'candidate'`, `'awaiting_refinement'`). Default: `'candidate','awaiting_refinement'`.
    *   `category` (String, optional): Filter by `traitCategory`.
    *   `sortBy` (String, optional): Field to sort by (e.g., `confidenceScore`, `creationTimestamp`). Default: `creationTimestamp`.
    *   `sortOrder` (String, optional): `asc` or `desc`. Default: `desc`.
    *   `limit` (Integer, optional): Number of items per page. Default: 20.
    *   `offset` (Integer, optional): Offset for pagination. Default: 0.
*   **Response (Success - 200 OK):**
    *   **Body (JSON):** A list of `ExtractedTraitCandidate` objects (as defined in `phase1_maipp_data_models.md`).
        ```json
        {
          "data": [
            {
              "candidateID": "traitcand_uuid_placeholder_001",
              "userID": "user_uuid_placeholder_123",
              "traitName": "Inquisitive Questioning Style",
              "traitDescription": "The user frequently asks clarifying questions...",
              "traitCategory": "LinguisticStyle",
              "supportingEvidenceSnippets": [
                {"type": "text_snippet", "content": "...", "sourcePackageID": "...", "sourceDetail": "..."}
              ],
              "confidenceScore": 0.85,
              "originatingModels": ["Google_Gemini_Pro_TextAnalysis", "..."],
              "associatedRawFeatureSetIDs": ["featureset_uuid_001", "..."],
              "status": "candidate",
              "creationTimestamp": "2024-03-15T14:00:00Z",
              "lastUpdatedTimestamp": "2024-03-15T14:00:00Z"
            }
            // ... more candidates
          ],
          "pagination": {
            "offset": 0,
            "limit": 20,
            "total": 55
          }
        }
        ```
*   **Error Responses:** 400, 401, 403, 500.

### 2. Submit Trait Refinement Action (Confirm, Modify, Reject)

*   **Endpoint:** `POST /v1/users/{userID}/persona/traits/candidates/{candidateID}/actions`
*   **Description:** Allows a user to submit their decision (confirm, modify, reject) on a specific AI-identified `ExtractedTraitCandidate`.
*   **Authentication:** OAuth 2.0 Bearer Token. `userID` must match token.
*   **Path Parameters:**
    *   `userID` (UUID, required): The user ID.
    *   `candidateID` (UUID, required): The ID of the `ExtractedTraitCandidate` being actioned.
*   **Request Body (JSON):**
    *   **Schema:**
        ```yaml
        type: object
        required:
          - userDecision # 'confirmed_asis', 'confirmed_modified', 'rejected'
        properties:
          userDecision:
            type: string
            enum: ['confirmed_asis', 'confirmed_modified', 'rejected']
          modifications: # Required if userDecision is 'confirmed_modified'
            type: object
            properties:
              refinedTraitName:
                type: string
                maxLength: 255
              refinedTraitDescription:
                type: string
              refinedTraitCategory:
                type: string
                # ENUM from ExtractedTraitCandidate.traitCategory
              userConfidenceRating: # User's own confidence (e.g., 1-5)
                type: integer
                minimum: 1
                maximum: 5
              customizationNotes:
                type: string
          rejectionReason: # Optional if userDecision is 'rejected'
            type: string
        ```
    *   **Example for 'confirmed_modified':**
        ```json
        {
          "userDecision": "confirmed_modified",
          "modifications": {
            "refinedTraitName": "Direct & Honest Communication",
            "refinedTraitDescription": "Prefers clear, direct communication. Values honesty over politeness if a choice must be made.",
            "refinedTraitCategory": "CommunicationStyle",
            "userConfidenceRating": 5,
            "customizationNotes": "AI's 'Blunt' was too negative. This is better."
          }
        }
        ```
    *   **Example for 'rejected':**
        ```json
        {
          "userDecision": "rejected",
          "rejectionReason": "This doesn't sound like me at all."
        }
        ```
*   **Response (Success - 200 OK):**
    *   **Body (JSON):** Details of the updated trait as it now exists or is marked in the PKG, and the logged `UserRefinedTrait` action.
        ```json
        {
          "message": "Trait action processed successfully.",
          "traitID_in_pkg": "traitcand_uuid_placeholder_001", // ID of the trait in PKG
          "newStatus_in_pkg": "active", // Or 'rejected_by_user'
          "updatedTraitDetails": { // Reflects the state after user action for confirmed/modified
            "name": "Direct & Honest Communication",
            "description": "Prefers clear, direct communication...",
            "category": "CommunicationStyle",
            // ...
          },
          "refinementActionID": "refineact_uuid_placeholder_xyz" // From UserRefinedTrait log
        }
        ```
*   **Error Responses:** 400 (e.g., invalid `userDecision`, missing `modifications` if needed), 401, 403, 404 (`candidateID` not found for user), 500 (if PKG update fails).

### 3. Add Custom User-Defined Trait

*   **Endpoint:** `POST /v1/users/{userID}/persona/traits/custom`
*   **Description:** Allows a user to define and add a completely new trait to their Persona Knowledge Graph.
*   **Authentication:** OAuth 2.0 Bearer Token. `userID` must match token.
*   **Path Parameters:**
    *   `userID` (UUID, required): The user ID.
*   **Request Body (JSON):**
    *   **Schema:**
        ```yaml
        type: object
        required:
          - traitName
          - traitCategory
        properties:
          traitName:
            type: string
            maxLength: 255
          traitDescription:
            type: string
            nullable: true
          traitCategory:
            type: string
            # ENUM from ExtractedTraitCandidate.traitCategory
          userConfidenceRating: # User's own confidence (e.g., 1-5)
            type: integer
            minimum: 1
            maximum: 5
            nullable: true
          supportingEvidenceSnippets: # Optional, user might provide textual examples
            type: array
            items:
              type: object # Simplified: user provides text, source is 'user_input'
              properties:
                type:
                  type: string
                  enum: ['text_snippet']
                  default: 'text_snippet'
                content:
                  type: string
        ```
    *   **Example:**
        ```json
        {
          "traitName": "Loves Jazz Music",
          "traitDescription": "Deep appreciation for various forms of jazz, attends live concerts.",
          "traitCategory": "Interest",
          "userConfidenceRating": 5,
          "supportingEvidenceSnippets": [
            {"type": "text_snippet", "content": "Regularly listens to Miles Davis and John Coltrane."}
          ]
        }
        ```
*   **Response (Success - 201 Created):**
    *   **Body (JSON):** Details of the newly created trait as it exists in the PKG.
        ```json
        {
          "message": "User-defined trait added successfully.",
          "newTrait": {
            "traitID_in_pkg": "new_trait_uuid_placeholder_789",
            "name": "Loves Jazz Music",
            "description": "Deep appreciation for various forms of jazz, attends live concerts.",
            "category": "Interest",
            "origin": "user_defined",
            "status_in_pkg": "active",
            // ...
          },
          "refinementActionID": "refineact_uuid_placeholder_abc" // From UserRefinedTrait log
        }
        ```
*   **Error Responses:** 400 (e.g., missing `traitName` or `traitCategory`), 401, 403, 500 (if PKG update fails).

### 4. Update Communication Style Preferences (Conceptual)

*   **Endpoint:** `PUT /v1/users/{userID}/persona/communication-styles`
*   **Description:** Allows a user to set or update global or contextual communication style preferences (e.g., formality, humor).
*   **Authentication:** OAuth 2.0 Bearer Token. `userID` must match token.
*   **Path Parameters:**
    *   `userID` (UUID, required): The user ID.
*   **Request Body (JSON):**
    *   **Schema:**
        ```yaml
        type: object
        description: A key-value map where key is the style element name (e.g., "FormalityLevel", "HumorUsage") and value is the user's preference.
        additionalProperties: # Allows for flexible style elements
          type: # Can be string, number, or a structured object depending on the style element
            oneOf:
              - type: string
              - type: number
              - type: object
        # Example:
        # properties:
        #   FormalityLevel:
        #     type: string
        #     enum: ['very_informal', 'informal', 'neutral', 'formal', 'very_formal']
        #   HumorUsage:
        #     type: string
        #     enum: ['none', 'low', 'medium', 'high']
        #   EmojiPreference:
        #     type: number
        #     minimum: 0.0
        #     maximum: 1.0 # Represents a scale
        ```
    *   **Example:**
        ```json
        {
          "FormalityLevel": "informal",
          "HumorUsage": "medium",
          "EmojiPreference": 0.7,
          "Pacing": "moderate"
        }
        ```
*   **Response (Success - 200 OK):**
    *   **Body (JSON):** Confirmation message and the updated style preferences.
        ```json
        {
          "message": "Communication style preferences updated successfully.",
          "updatedStyles": {
            "FormalityLevel": "informal",
            "HumorUsage": "medium",
            "EmojiPreference": 0.7,
            "Pacing": "moderate"
          }
        }
        ```
*   **Error Responses:** 400 (invalid style element names or values), 401, 403, 500.

## II. Internal Service Interactions (PTFI initiated)

PTFI's backend primarily interacts with data stores (PostgreSQL for candidates/logs, Graph DB for PKG). It does not typically initiate calls to other services like UDIM or MAIPP in Phase 1. Its role is to apply user decisions to the data artifacts produced by MAIPP.

*   **PostgreSQL (for `ExtractedTraitCandidate` and `UserRefinedTrait`):**
    *   **Interaction Type:** Direct database calls using an ORM (SQLAlchemy async) or async database driver (`asyncpg`).
    *   **Operations:**
        *   `SELECT` from `ExtractedTraitCandidate` based on `userID`, `status`, etc.
        *   `UPDATE` `ExtractedTraitCandidate` status.
        *   `INSERT` into `UserRefinedTrait` log table.
*   **Graph Database (Neo4j/Neptune for PKG):**
    *   **Interaction Type:** Direct database calls using graph DB driver (`neo4j`, `gremlinpython`).
    *   **Operations (Conceptual Cypher/Gremlin equivalents):**
        *   `MERGE` or `CREATE` `Trait` nodes and link to `User` node.
        *   `SET` properties on `Trait` nodes (name, description, category, status, origin, confidence).
        *   `REMOVE` properties or `DETACH DELETE` relationships/nodes if a trait is fully rejected and to be removed (or more likely, update a `status` property on the `Trait` node).
        *   `MERGE` or `CREATE` `CommunicationStyleElement` nodes and link to `User` node, setting values.
        *   `MERGE` or `CREATE` `SourceDataReferenceNode` and link to `Trait` nodes.
*   **No explicit internal HTTP APIs are defined *for other services to call PTFI* in Phase 1, as PTFI is primarily user-driven via its own API.**

This specification outlines the primary APIs for the PTFI backend. The frontend UI will consume these to provide the user with the interface for persona refinement.
```
