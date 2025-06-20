# Phase 1: Persona Trait Finalization Interface (PTFI) - Preliminary Implementation Tasks

This document breaks down the development work for the backend components of the Persona Trait Finalization Interface (PTFI) module in EchoSphere's Phase 1. These tasks are based on its defined Data Models, Core Logic, and Technology Stack. Frontend UI development tasks are separate but will rely on these backend APIs.

## 1. Project Setup & Core Infrastructure (PTFI API Service)

*   **Task 1.1: Initialize PTFI Service Repository (if separate).**
    *   Description: Set up a Git repository for the PTFI backend service. Standard Python project structure. (May be part of a larger Phase 1 monorepo).
*   **Task 1.2: Basic CI/CD Pipeline for PTFI.**
    *   Description: Minimal CI pipeline (linters, unit test placeholders).
*   **Task 1.3: FastAPI Application Skeleton for PTFI.**
    *   Description: Create the main FastAPI application for PTFI APIs. Set up routers for trait management, PKG interaction, etc. Include a health check endpoint.
*   **Task 1.4: Logging & Configuration Management for PTFI.**
    *   Description: Implement structured logging and configuration management (Pydantic `BaseSettings`) for database connections, PKG endpoint, etc.
*   **Task 1.5: Dockerization of PTFI Service.**
    *   Description: Create a `Dockerfile` for the PTFI FastAPI application.

## 2. Database & PKG Connection Setup

*   **Task 2.1: PostgreSQL Client Integration.**
    *   Description: Implement database connection logic (using SQLAlchemy async or `asyncpg`) to connect to the PostgreSQL instance hosting `ExtractedTraitCandidate` and `UserRefinedTrait` tables. Ensure proper session management and connection pooling.
*   **Task 2.2: Graph Database (Neo4j/Neptune) Client Integration.**
    *   Description: Implement client logic (using `neo4j` driver or `gremlinpython`) to connect to the Persona Knowledge Graph database. Handle authentication and session management.
*   **Task 2.3: `UserRefinedTrait` Table Migration.**
    *   Description: Define the `UserRefinedTrait` SQLAlchemy model (if applicable). Create and apply the Alembic migration script to set up this table in PostgreSQL.

## 3. Authentication & Authorization for PTFI APIs

*   **Task 3.1: OAuth 2.0 Bearer Token Validation for PTFI APIs.**
    *   Description: Secure all PTFI API endpoints using the same OAuth 2.0 Bearer Token validation middleware/dependency implemented for UDIM. Ensure only the legitimate user can access their persona refinement interface.
*   **Task 3.2: User Ownership Checks.**
    *   Description: Implement checks in all PTFI service logic to ensure that operations (fetching candidates, confirming/rejecting/adding traits) are performed only for the `userID` authenticated via the token.

## 4. PTFI API Endpoint Development

*   **Task 4.1: Develop `GET /v1/users/{userID}/persona/traits/candidates` Endpoint.**
    *   Description: Implement the API to fetch `ExtractedTraitCandidate` records from PostgreSQL for the given `userID` with status 'candidate' or 'awaiting_refinement'. Include filtering and sorting options. Format data for UI presentation.
*   **Task 4.2: Develop `POST /v1/users/{userID}/persona/traits/confirm` Endpoint (or similar for trait actions).**
    *   Description: Implement the API to handle user decisions:
        *   'confirmed_asis': Update PKG `Trait` node, update `ExtractedTraitCandidate` status.
        *   'confirmed_modified': Update PKG `Trait` node with user's modifications, update `ExtractedTraitCandidate` status.
        *   This endpoint will take `candidateID` and modification details as payload.
*   **Task 4.3: Develop `POST /v1/users/{userID}/persona/traits/reject` Endpoint.**
    *   Description: Implement the API to handle user rejection of an `ExtractedTraitCandidate`. Update PKG `Trait` node (or its relationship to user) to 'rejected_by_user', update `ExtractedTraitCandidate` status. Payload includes `candidateID` and optional rejection reason.
*   **Task 4.4: Develop `POST /v1/users/{userID}/persona/traits/custom` Endpoint.**
    *   Description: Implement the API for users to add a new custom trait. Create a new `Trait` node in the PKG with `origin: 'user_defined'` and link it to the user. Payload includes trait name, description, category, etc.
*   **Task 4.5: Develop `POST /v1/users/{userID}/persona/communication-style` Endpoint (Conceptual).**
    *   Description: Implement API to update `CommunicationStyleElement` nodes and their relationships to the `User` node in the PKG based on user preferences.
*   **Task 4.6: Implement `UserRefinedTrait` Logging.**
    *   Description: For each of the above actions (confirm, modify, reject, custom add), implement logic to create and save a `UserRefinedTrait` record to PostgreSQL, logging the user's specific action and inputs.

## 5. Persona Knowledge Graph (PKG) Interaction Logic

*   **Task 5.1: PKG `Trait` Node Creation/Update Functions.**
    *   Description: Develop robust functions to create new `Trait` nodes in the PKG or update existing ones (e.g., changing name, description, category, status, confidence). Ensure these functions also handle the `(User)-[:HAS_TRAIT]->(Trait)` relationship.
*   **Task 5.2: PKG `Trait` Node Rejection/Deactivation Logic.**
    *   Description: Implement functions to mark a `Trait` node in the PKG as 'rejected_by_user' or 'dormant', or to remove/flag the `(User)-[:HAS_TRAIT]->(Trait)` relationship.
*   **Task 5.3: PKG Evidence Linking Functions.**
    *   Description: Implement functions to link/re-link `Trait` nodes to `SourceDataReferenceNode`s in the PKG, based on user validation of evidence or user-provided evidence for custom traits.
*   **Task 5.4: PKG `CommunicationStyleElement` Update Functions.**
    *   Description: Develop functions to create/update `CommunicationStyleElement` nodes and their relationships to the `User` node in the PKG.
*   **Task 5.5: Query Functions for PKG Data Display (if PTFI shows PKG views).**
    *   Description: If the PTFI UI will display parts of the PKG (e.g., a graph visualization of traits and concepts), develop backend functions to query and format this data from the graph database.

## 6. Testing

*   **Task 6.1: Unit Tests for PTFI Service Logic.**
    *   Description: Write unit tests (`pytest`) for business logic within API endpoint handlers, Pydantic models, and any helper functions. Mock database/PKG interactions.
*   **Task 6.2: API Integration Tests for PTFI Endpoints.**
    *   Description: Use FastAPI's `TestClient` to test each PTFI API endpoint, covering successful operations, error handling, authentication, and authorization.
*   **Task 6.3: Database Integration Tests (PostgreSQL).**
    *   Description: Test interactions with the PostgreSQL database for `ExtractedTraitCandidate` (read/update status) and `UserRefinedTrait` (write) tables using a test database instance.
*   **Task 6.4: Graph Database Integration Tests (PKG).**
    *   Description: Test interactions with the graph database (Neo4j/Neptune). Verify that trait nodes and relationships are correctly created, updated, and marked/deleted based on PTFI actions. Use a test graph database instance.
*   **Task 6.5: End-to-End Flow Tests (Conceptual).**
    *   Description: Simulate a user flow:
        1.  Fetch trait candidates.
        2.  Select a candidate and confirm/modify it. Verify API response and check PKG/PostgreSQL for correct updates.
        3.  Select another candidate and reject it. Verify API response and check PKG/PostgreSQL.
        4.  Add a new custom trait. Verify API response and check PKG for new trait node.

## 7. Documentation

*   **Task 7.1: Refine PTFI API Documentation.**
    *   Description: Review and enhance the auto-generated OpenAPI (Swagger) documentation from FastAPI for all PTFI endpoints. Ensure clarity, examples, and accurate schema definitions.
*   **Task 7.2: PTFI Module README.**
    *   Description: Document the setup, configuration, and operation of the PTFI backend service.
```
