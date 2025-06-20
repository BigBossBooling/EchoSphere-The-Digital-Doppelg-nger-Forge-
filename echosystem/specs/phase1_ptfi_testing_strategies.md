# Phase 1: Persona Trait Finalization Interface (PTFI) - Testing Strategies

This document outlines the testing strategies for the backend components of the Persona Trait Finalization Interface (PTFI) module of EchoSphere's Phase 1. The focus is on ensuring the PTFI APIs function correctly, interact reliably with data stores (PostgreSQL and Graph Database for PKG), and enforce business rules for trait refinement. Frontend UI testing is considered separate but relies on these robust backend APIs.

## 1. Unit Testing

*   **Objective:** To verify the correctness of individual functions, methods, and classes within the PTFI backend service in isolation.
*   **Scope:**
    *   **Pydantic Models:** Validation logic for API request and response bodies specific to PTFI.
    *   **API Endpoint Handler Logic (Business Logic):** Core logic within FastAPI path operation functions, with external dependencies (PostgreSQL, Graph Database clients) thoroughly mocked. This includes:
        *   Logic for parsing and validating user input from API requests.
        *   Logic for constructing queries or commands for database/PKG interactions.
        *   Logic for transforming data from database/PKG into API response DTOs.
        *   Decision-making logic based on user input (e.g., how to update PKG for 'confirmed_asis' vs. 'confirmed_modified').
    *   **Helper Utilities:** Any utility functions specific to PTFI (e.g., formatting trait data for display if done in backend, helper functions for constructing PKG queries).
    *   **Error Handling Logic:** How specific errors from mocked database/PKG operations are caught and translated into appropriate HTTP error responses.
*   **Tools:**
    *   `pytest`: Primary Python testing framework.
*   **Techniques:**
    *   **Mocking (`unittest.mock` or `pytest-mock`):** Crucial for isolating PTFI logic. Mock:
        *   PostgreSQL client calls (for `ExtractedTraitCandidate` reads/updates and `UserRefinedTrait` writes).
        *   Graph Database (Neo4j/Neptune) client calls (for all PKG node/relationship CRUD operations).
        *   Authentication/Authorization dependencies (assume user is authenticated with specific `userID` for unit tests).
    *   **Parameterized Testing (`pytest.mark.parametrize`):** For testing API logic with various valid and invalid inputs, different user decisions, and diverse trait modification scenarios.
    *   **Fixtures (`pytest.fixture`):** To create reusable mock data (e.g., sample `ExtractedTraitCandidate` objects, sample user modification payloads, mock database responses).
    *   **Code Coverage (`pytest-cov`):** Aim for high unit test coverage for PTFI's business logic.

## 2. Integration Testing

*   **Objective:** To verify the interactions between the PTFI backend service and the actual data stores it depends on (`ExtractedTraitCandidate` table in PostgreSQL, `UserRefinedTrait` table in PostgreSQL, and the Persona Knowledge Graph in Neo4j/Neptune).
*   **Scope:**
    *   **API Endpoint Testing (FastAPI `TestClient`):**
        *   Testing PTFI's FastAPI endpoints from an HTTP client perspective, but allowing interactions with real (test instance) databases/PKG.
        *   Verifies request validation, authentication/authorization middleware (if not fully mocked), successful processing of trait refinement actions, and error handling for database/PKG related issues.
    *   **PostgreSQL Integration (`ExtractedTraitCandidate` & `UserRefinedTrait`):**
        *   Verify that PTFI can correctly read `ExtractedTraitCandidate` data from a test PostgreSQL database.
        *   Verify that PTFI correctly updates the `status` of `ExtractedTraitCandidate` records.
        *   Verify that PTFI correctly writes `UserRefinedTrait` log entries to the PostgreSQL database with all expected information.
        *   Test transactional behavior if multiple database operations are involved in one PTFI action.
    *   **Graph Database (PKG) Integration:**
        *   Verify that PTFI can correctly create, read, update, and manage `Trait` nodes in the test PKG based on user actions (confirm, modify, reject, add custom).
        *   Verify creation and modification of relationships (e.g., `(User)-[:HAS_TRAIT]->(Trait)`, `(Trait)-[:EVIDENCED_BY]->(SourceDataReferenceNode)`).
        *   Test complex update scenarios (e.g., user modifies a trait name, then rejects it – ensure final PKG state is correct).
        *   Test queries PTFI might use to display PKG information to the user (if any).
*   **Tools:**
    *   `pytest`: For orchestrating integration tests.
    *   FastAPI `TestClient`: For making requests to the PTFI API.
    *   SQLAlchemy (or `psycopg2`/`asyncpg`): For setting up test data in PostgreSQL and verifying results.
    *   `neo4j` driver / `gremlinpython`: For setting up test data in the graph database and verifying results.
    *   `docker-compose`: To spin up local instances of PostgreSQL and Neo4j/Neptune for a self-contained integration test environment. Test containers are ideal.
    *   Alembic: To ensure test database schemas are up-to-date.

## 3. End-to-End (E2E) Testing (Backend Focus)

*   **Objective:** To verify complete user-driven trait refinement flows through the PTFI backend APIs, ensuring all backend components (API, PostgreSQL, Graph DB) work together correctly.
*   **Scope:**
    *   **Fetch and Review:** Simulate a client fetching trait candidates for a test user.
    *   **Confirm Trait Flow:** Client selects a candidate, confirms it (as-is or modified). Verify API response, `ExtractedTraitCandidate` status update in PostgreSQL, `UserRefinedTrait` log creation, and corresponding `Trait` node creation/update in PKG.
    *   **Reject Trait Flow:** Client selects a candidate, rejects it. Verify API response, `ExtractedTraitCandidate` status update, `UserRefinedTrait` log, and PKG update (e.g., trait status changed to 'rejected_by_user' or relationship removed).
    *   **Add Custom Trait Flow:** Client submits details for a new custom trait. Verify API response, `UserRefinedTrait` log, and new `Trait` node creation in PKG linked to the user.
    *   **Modify Communication Style Flow (if implemented):** Client submits style preferences. Verify API response and PKG updates to `CommunicationStyleElement` nodes/relationships.
*   **Tools:**
    *   `pytest` with `httpx` (for making HTTP requests to a deployed PTFI instance).
    *   Custom test scripts (Python).
    *   A deployed instance of PTFI connected to test instances of PostgreSQL and Neo4j/Neptune.
    *   Tools to inspect database and graph database contents directly to verify outcomes.

## 4. Security Testing (PTFI Specifics)

*   **Objective:** To identify and mitigate security vulnerabilities in the PTFI backend service.
*   **Scope & Techniques:**
    *   **Authentication & Authorization Testing:**
        *   Verify all PTFI API endpoints correctly enforce authentication.
        *   Crucially, test that a user can *only* view and modify *their own* trait candidates and PKG data. Attempt cross-user data access/modification by manipulating `userID` in paths or payloads if not solely derived from a validated token.
        *   Test for Insecure Direct Object References (IDOR) if `candidateID` or `traitID_in_pkg` could be manipulated.
    *   **Input Validation Testing:**
        *   Submit requests with malformed or malicious payloads for trait names, descriptions, categories, etc., to ensure robust validation and prevent injection attacks (though ORMs/parameterized graph queries should largely mitigate SQL/Cypher injection).
        *   Test handling of unexpected or invalid ENUM values for `userDecision`, `traitCategory`, etc.
    *   **Secure Configuration Review:**
        *   Audit database access controls for PostgreSQL and the Graph Database, ensuring the PTFI service account has least-privilege permissions.
    *   **Dependency Scanning & SAST:** Same as other modules (`Bandit`, `pip-audit`) applied to PTFI codebase.
*   **Focus for PTFI:** Ensuring strict data ownership and preventing unauthorized modifications to a user's persona definition via its APIs.

## 5. Usability Testing (API Developer Experience)

*   **Objective:** To ensure the PTFI backend APIs are clear, well-documented, consistent, and easy for the frontend development team to integrate with.
*   **Techniques:**
    *   **API Documentation Review:** Ensure the OpenAPI (Swagger) spec generated by FastAPI is accurate, complete, and provides clear examples for request/response bodies.
    *   **Collaboration with Frontend Team:** Regular communication and feedback sessions with the frontend developers who will be consuming these APIs.
    *   **Mock API Server (Optional):** Provide a mock version of the PTFI API (e.g., using Prism or a simple FastAPI app with mock data) for early frontend development before the full backend is ready.

## General Testing Principles (Consistent with other modules)

*   **Automation:** Integrate all automated tests into CI/CD.
*   **Isolation:** Unit tests fully isolated. Integration tests use dedicated test databases/services or reliable mocks.
*   **Repeatability:** Deterministic tests.
*   **Early Testing:** Test-driven or behavior-driven approaches.
*   **Test Data Management:**
    *   Strategies for creating consistent test users, `ExtractedTraitCandidate` records, and initial PKG states for test runs.
    *   Use tools like `factory_boy` for generating test data objects in Python.
    *   Ensure test data is cleaned up or reset between integration/E2E test runs.
    *   No real user data in test environments.
```
