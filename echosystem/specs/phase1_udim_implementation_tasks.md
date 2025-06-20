# Phase 1: User Data Ingestion Module (UDIM) - Preliminary Implementation Tasks

This document breaks down the development work for the User Data Ingestion Module (UDIM) of EchoSphere's Phase 1 into manageable tasks, based on the defined Data Models, API Specifications, Core Logic, and Technology Stack.

## 1. Project Setup & Core Infrastructure

*   **Task 1.1: Initialize UDIM Service Repository.**
    *   Description: Set up a new Git repository for the UDIM microservice. Initialize with a standard Python project structure (e.g., `src`, `tests`, `docs`, `scripts`).
*   **Task 1.2: Basic CI/CD Pipeline Setup.**
    *   Description: Implement a minimal CI pipeline (e.g., using GitHub Actions, GitLab CI) that runs linters (Flake8, Black), and placeholders for unit tests on every push/merge.
*   **Task 1.3: FastAPI Application Skeleton.**
    *   Description: Create the main FastAPI application instance. Set up basic application structure with routers, and an initial health check endpoint (e.g., `/health`).
*   **Task 1.4: Logging Implementation.**
    *   Description: Configure structured logging (e.g., using `structlog` or standard Python logging configured for JSON output) for the FastAPI application. Ensure logs include correlation IDs for requests.
*   **Task 1.5: Configuration Management.**
    *   Description: Implement configuration management using Pydantic's `BaseSettings` to load settings from environment variables and/or `.env` files (for database URLs, KMS keys, S3 bucket names, etc.).
*   **Task 1.6: Dockerization.**
    *   Description: Create a `Dockerfile` for the FastAPI application. Ensure it builds a runnable image with all necessary dependencies and runs the Uvicorn server. Add Docker Compose for local development ease.

## 2. Database & Storage Setup

*   **Task 2.1: Provision PostgreSQL Instance.**
    *   Description: Set up a PostgreSQL database instance using a managed cloud service (e.g., AWS RDS, Google Cloud SQL). Configure initial user, database, and network access.
*   **Task 2.2: `UserDataPackage` Table Migration.**
    *   Description: Define the `UserDataPackage` SQLAlchemy model (if using SQLAlchemy). Create and apply the initial Alembic migration script to set up the table in the PostgreSQL database.
*   **Task 2.3: Provision Amazon QLDB Ledger.**
    *   Description: Create an Amazon QLDB ledger with appropriate journaling and indexing for `ConsentLedgerEntry` data. Define the initial table(s) structure within QLDB (e.g., for consent records).
*   **Task 2.4: (Placeholder) Scripts/Schema for QLDB `ConsentLedgerEntry`.**
    *   Description: Develop initial scripts or schema definitions for creating and indexing the `ConsentLedgerEntry` table/document structure in QLDB. (Full implementation depends on UCMS in Phase 4, but UDIM needs to know the target structure for `consentTokenID` FK relation).
*   **Task 2.5: Setup AWS S3 Bucket for Raw Data.**
    *   Description: Create an S3 bucket for storing encrypted raw user data. Configure strict bucket policies, enable versioning, server-side encryption (defaulting to KMS), and access logging. Set up lifecycle policies for eventual data archival/deletion.
*   **Task 2.6: Configure AWS KMS Key(s).**
    *   Description: Create and configure Customer Managed Key(s) (CMKs) in AWS KMS that will be used for S3 SSE-KMS encryption of user data. Define key policies to control access.

## 3. Authentication & Authorization

*   **Task 3.1: OAuth 2.0 Bearer Token Validation Middleware.**
    *   Description: Implement FastAPI middleware or a dependency to validate incoming OAuth 2.0 Bearer Tokens (JWTs). This includes checking signature, expiry, and audience. Use `Authlib` or `python-jose`.
*   **Task 3.2: User & Scope Extraction from Token.**
    *   Description: Extract `userID` and `scopes` from the validated token claims. Make these available in the request context.
*   **Task 3.3: Scope-Based Endpoint Authorization.**
    *   Description: Implement decorators or dependencies in FastAPI to check if the authenticated user's token scopes permit access to the specific endpoint and action being requested.

## 4. Consent Management Integration (UDIM side)

*   **Task 4.1: Client for Internal Consent Verification API.**
    *   Description: Develop an asynchronous HTTP client (using `httpx`) within UDIM to call the (future) internal Consent Verification API (`GET /internal/consent/v1/verify`).
*   **Task 4.2: Consent Verification Logic.**
    *   Description: Implement logic within relevant UDIM flows (e.g., before file upload processing) to use the client from Task 4.1 to verify the provided `consentTokenID` against the required scope.
*   **Task 4.3: Error Handling for Consent Issues.**
    *   Description: Implement robust error handling for scenarios where consent is invalid, insufficient, expired, or revoked, returning appropriate HTTP error codes (e.g., 403 Forbidden, 422 Unprocessable Entity).
*   **Task 4.4 (External Dependency - UI/UCMS): Define `ConsentLedgerEntry` creation flow.**
    *   Description: Although not a UDIM backend task, document the dependency on a UI/UCMS flow that allows users to grant consent, leading to the creation of a `ConsentLedgerEntry` and generation of a `consentTokenID` *before* UDIM's upload/import APIs are called with that token.

## 5. Direct Data Upload API (`POST /v1/users/{userID}/data/upload`)

*   **Task 5.1: Develop Endpoint & Route.**
    *   Description: Create the FastAPI route, path operations, and request/response Pydantic models for the direct data upload endpoint.
*   **Task 5.2: Multipart/Form-Data Parsing.**
    *   Description: Implement logic to correctly parse `multipart/form-data`, extracting the file, `sourceDescription`, `dataType`, and `consentTokenID`.
*   **Task 5.3: File Validation Logic.**
    *   Description: Implement file size validation against configured limits.
*   **Task 5.4: Malware Scanning Integration.**
    *   Description: Implement a call to a malware scanning service (e.g., local ClamAV daemon API or cloud service) for the uploaded file. Handle positive scan results by rejecting the upload.
*   **Task 5.5: Data Type Determination.**
    *   Description: Implement logic to determine the file's MIME type, using the client-provided `dataType` as a hint but verifying/falling back to server-side detection if necessary.
*   **Task 5.6: File Encryption & S3 Upload.**
    *   Description: Integrate with AWS SDK (`boto3`) to upload the file stream to S3, ensuring SSE-KMS encryption is applied using the appropriate `encryptionKeyID`. This involves managing the file stream securely.
*   **Task 5.7: `UserDataPackage` Metadata Persistence.**
    *   Description: After successful S3 upload, create and save the `UserDataPackage` metadata record to the PostgreSQL database.
*   **Task 5.8: Asynchronous Response (202 Accepted).**
    *   Description: Ensure the endpoint returns a 202 Accepted response promptly after initial validation and queuing, with a URL to check processing status. The actual file processing (S3 upload, DB record) might happen in a background task if very large or time-consuming, though direct async processing is preferred.

## 6. Data Source Connection API (OAuth Connections)

*   **Task 6.1: Develop OAuth Initiate Endpoint (`.../initiate`).**
    *   Description: Implement the FastAPI endpoint for initiating OAuth connections. Include logic to generate and store `state` parameter (e.g., in Redis with TTL) and redirect to the third-party OAuth provider. Implement for one representative service first (e.g., Google Drive).
*   **Task 6.2: Develop OAuth Callback Endpoint (`.../callback`).**
    *   Description: Implement the FastAPI endpoint for handling OAuth callbacks. Include `state` validation, code-for-token exchange, and secure (encrypted) storage of OAuth tokens associated with the `userID` and a new `connectionID`.
*   **Task 6.3: Develop Data Import Endpoint (`.../import`).**
    *   Description: Implement the FastAPI endpoint for importing data from a connected source.
        *   Verify `connectionID` and retrieve stored OAuth tokens.
        *   (Simplified for initial task) Implement logic to use tokens to fetch one representative item from the third-party service API.
        *   Process the fetched item similarly to a direct upload: consent check (for this specific import), encryption, S3 storage, `UserDataPackage` metadata creation.
        *   Handle token refresh logic if an access token has expired and a refresh token is available.

## 7. Internal MAIPP Notification

*   **Task 7.1: Setup AWS SQS Queue & DLQ.**
    *   Description: Provision the SQS standard queue for MAIPP notifications and a corresponding Dead-Letter Queue (DLQ) using Infrastructure as Code (e.g., Terraform, CloudFormation) or console setup.
*   **Task 7.2: Implement SQS Message Publishing.**
    *   Description: In UDIM, after a `UserDataPackage` is successfully created and its metadata stored, implement logic to construct the notification payload (as per API spec) and publish it to the SQS queue.
*   **Task 7.3: Error Handling for SQS Publishing.**
    *   Description: Implement error handling and retry mechanisms for SQS publishing (though `boto3` often handles transient errors). Ensure critical failures are logged.

## 8. Testing

*   **Task 8.1: Unit Tests.**
    *   Description: Develop unit tests (using `pytest`) for critical business logic: Pydantic model validation, utility functions (e.g., data type determination, `state` generation), individual steps in API logic. Mock external dependencies like S3, KMS, SQS, and internal API calls.
*   **Task 8.2: API Integration Tests.**
    *   Description: Develop integration tests for each API endpoint. Use FastAPI's `TestClient`. Test successful cases, error responses, authentication/authorization enforcement, and consent verification logic.
*   **Task 8.3: Storage & Database Integration Tests.**
    *   Description: Write tests that verify actual file upload to a test S3 bucket (with encryption) and metadata persistence to a test PostgreSQL database. Test QLDB interactions if feasible in an automated test environment.
*   **Task 8.4: SQS Notification Publishing Tests.**
    *   Description: Test the SQS notification publishing mechanism, ensuring messages are correctly formatted and sent to the queue. This might involve a local SQS mock (e.g., ElasticMQ) or testing against a non-production AWS SQS queue.

## 9. Documentation

*   **Task 9.1: API Documentation Refinement.**
    *   Description: Review and refine the auto-generated OpenAPI (Swagger) documentation from FastAPI. Add detailed descriptions, examples, and explanations for all UDIM endpoints.
*   **Task 9.2: Module README.**
    *   Description: Create/update a README file for the UDIM service, covering setup instructions, environment variable configuration, how to run the service locally, and key operational notes.
*   **Task 9.3: Contribution Guidelines (If applicable).**
    *   Description: Basic guidelines for developers contributing to the UDIM codebase.
```
