# Phase 1: User Data Ingestion Module (UDIM) - Testing Strategies

This document outlines the testing strategies for the User Data Ingestion Module (UDIM) of EchoSphere's Phase 1. The approach encompasses various levels and types of testing to ensure functionality, reliability, security, and performance.

## 1. Unit Testing

*   **Objective:** To verify the correctness of individual functions, methods, and classes in isolation, ensuring each small piece of code behaves as expected.
*   **Scope:**
    *   **Helper Utilities:** Functions for tasks like data type determination (MIME type inference), filename sanitization, S3 path construction, `state` parameter generation for OAuth.
    *   **Pydantic Models:** Validation logic defined within Pydantic models for API request/response bodies and internal data structures. Testing various valid and invalid inputs.
    *   **Business Logic within API Endpoint Handlers:** Core logic within FastAPI path operation functions, with external dependencies (database connections, S3 client, KMS client, SQS client, internal API clients) mocked. This includes logic for parsing requests, calling validation routines, orchestrating calls to other services (mocked), and formatting responses.
    *   **Specific Data Processing Steps:** Logic for constructing `UserDataPackage` metadata, generating MAIPP notification payloads.
    *   **Error Handling Logic:** How specific errors from external services (mocked) are caught and translated into appropriate HTTP error responses.
*   **Tools:**
    *   `pytest`: Primary Python testing framework for its flexibility, fixtures, and rich plugin ecosystem.
*   **Techniques:**
    *   **Mocking:** Extensive use of `unittest.mock` (standard library) or `pytest-mock` (pytest plugin) to replace external dependencies (databases, S3, KMS, SQS, internal API clients like Consent Verification client) with mock objects. This allows testing the logic of a unit without actual network calls or side effects.
    *   **Parameterized Testing (`pytest.mark.parametrize`):** Testing functions with a wide range of valid and invalid inputs to ensure robustness.
    *   **Fixtures (`pytest.fixture`):** Creating reusable setup and teardown code for test dependencies (e.g., sample Pydantic models, mock service responses).
    *   **Code Coverage:** Aim for high code coverage (e.g., >90%) for new code, measured using tools like `pytest-cov`. While not a guarantee of quality, it helps identify untested code paths.
    *   **Focus on Logic Paths:** Ensure all significant conditional branches and loops within functions are tested.

## 2. Integration Testing

*   **Objective:** To verify the interactions between different components of UDIM and with other services it directly depends on, ensuring they work together correctly.
*   **Scope:**
    *   **API Endpoint Testing (FastAPI `TestClient`):**
        *   Testing FastAPI endpoints from the perspective of an HTTP client. This verifies request routing, request validation (Pydantic models), authentication/authorization middleware execution, happy path responses, and HTTP error code generation for various invalid inputs or conditions.
        *   Ensures that path parameters, query parameters, form data, and request bodies are correctly processed.
    *   **Database Integration (PostgreSQL & Amazon QLDB):**
        *   Verifying that `UserDataPackage` metadata is correctly written to and read from a test PostgreSQL database. Test transactions, constraints (foreign keys), and data integrity.
        *   For QLDB (ConsentLedgerEntry), UDIM primarily reads/verifies. Integration tests would focus on the client logic that calls the (mocked or test instance of) Consent Verification API, which in turn would interact with QLDB. Direct QLDB interaction tests for UDIM are minimal unless UDIM writes system-level consents.
    *   **Object Storage (AWS S3) Integration:**
        *   Verifying that files are correctly uploaded to a test S3 bucket.
        *   Confirming that Server-Side Encryption with KMS (SSE-KMS) is applied as expected.
        *   Testing that `rawDataReference` is correctly constructed and stored.
        *   Testing error handling for S3 failures (e.g., bucket not found, access denied - by configuring mock S3 appropriately).
    *   **KMS Integration:**
        *   Ensuring that the application correctly specifies the KMS key ID when uploading to S3 (indirectly tested via S3 integration).
        *   Testing permissions related to KMS key usage (e.g., UDIM's role can use the key for encryption).
    *   **Messaging Queue (AWS SQS) Integration:**
        *   Verifying that MAIPP notification messages are correctly formatted (matching the defined schema) and successfully published to a designated test SQS queue.
        *   Testing that messages are routed to a Dead-Letter Queue (DLQ) if the SQS publishing fails persistently (if applicable at this level, though SDKs might handle retries transparently).
    *   **Internal API Client Integration:**
        *   Testing the client code within UDIM that calls the internal Consent Verification API. This involves mocking the HTTP responses of the Consent Service endpoint to simulate various scenarios (valid consent, invalid consent, service unavailable) and ensuring UDIM's client handles these responses correctly.
*   **Tools:**
    *   `pytest`: For orchestrating integration tests.
    *   FastAPI `TestClient`: For in-process testing of API endpoints without needing a running HTTP server.
    *   `boto3` (AWS SDK for Python): For interacting with real (test) AWS resources like S3, SQS, KMS, or with mocks.
    *   **Local Mocking Tools:**
        *   `moto`: A library that allows mocking out AWS services in Python tests. Useful for S3, SQS, KMS.
        *   `LocalStack`: Provides a more comprehensive local AWS cloud stack emulation.
        *   `ElasticMQ`: A local, in-memory SQS-compatible message queue server.
    *   `docker-compose`: To spin up local instances of PostgreSQL, ElasticMQ, or even LocalStack for a self-contained integration test environment. Test containers can be used.
    *   Alembic: For managing test database schema migrations.

## 3. End-to-End (E2E) Testing (Limited Scope for UDIM as a module)

*   **Objective:** To verify complete data ingestion flows from the perspective of an external API client, ensuring all integrated components of UDIM work together as expected in a deployed-like environment.
*   **Scope:**
    *   **Direct Upload Flow:**
        1.  Simulate an API client authenticating (obtaining a test token).
        2.  Client uploads a sample file via the `POST /v1/users/{userID}/data/upload` API, providing a (mocked or pre-existing valid) `consentTokenID`.
        3.  Verify:
            *   A successful `202 Accepted` API response is received.
            *   The uploaded file exists in the designated test S3 bucket and is encrypted correctly.
            *   A corresponding `UserDataPackage` metadata record is created in the test PostgreSQL database with correct information.
            *   A notification message (with the correct payload) is published to the test SQS queue for MAIPP.
    *   **OAuth Connection & Import Flow (Simplified E2E):**
        1.  Simulate client initiating OAuth flow (`.../initiate`).
        2.  Mock the third-party OAuth provider's response to UDIM's callback (`.../callback`), providing a dummy `code`.
        3.  Verify that UDIM attempts to exchange the code and (mocked) stores tokens.
        4.  Simulate client calling the import endpoint (`.../import`) with a reference to a (mocked) item from the connected source and a valid `consentTokenID`.
        5.  Verify similar outcomes as direct upload flow (S3, PostgreSQL, SQS).
*   **Tools:**
    *   `pytest` with `httpx` (for making real HTTP requests to a deployed UDIM instance).
    *   Custom test scripts (Python, shell scripts).
    *   A deployed instance of UDIM connected to actual test AWS resources (S3, SQS, KMS, PostgreSQL, QLDB). This environment should be isolated from production.
    *   Tools to inspect S3 bucket contents, database records, and SQS messages.

## 4. Security Testing

*   **Objective:** To proactively identify and mitigate security vulnerabilities within the UDIM service.
*   **Scope & Techniques:**
    *   **Authentication & Authorization Testing:**
        *   Verify all endpoints require authentication.
        *   Test that users can only access or manage data associated with their `userID`.
        *   Attempt to access endpoints with tokens having insufficient scopes.
        *   Test for Insecure Direct Object References (IDOR) by trying to access/modify resources of one user using another authenticated user's session.
        *   Verify OAuth `state` parameter effectively prevents CSRF in the connection flow.
    *   **Input Validation Testing:**
        *   Submit requests with missing required fields, malformed data (e.g., invalid UUIDs, incorrect data types), and overly long inputs to ensure robust validation and error handling.
        *   Test file upload with various file types (valid and invalid/unexpected) and sizes (including very large files to test limits).
        *   Ensure `consentTokenID` presence and format is validated.
    *   **Secure Configuration Review (Manual & Automated):**
        *   Audit AWS S3 bucket policies for least privilege access.
        *   Verify S3 server-side encryption settings (SSE-KMS).
        *   Review AWS KMS key policies to ensure only authorized principals can use keys.
        *   Audit PostgreSQL and QLDB access controls, network exposure, and encryption-at-rest settings.
        *   Review IAM roles assigned to the UDIM service for least privilege.
    *   **Dependency Scanning:**
        *   Integrate tools like `pip-audit` (Python specific), Snyk, or GitHub Dependabot into the CI/CD pipeline to scan for known vulnerabilities in third-party libraries.
    *   **Static Application Security Testing (SAST):**
        *   Integrate SAST tools like `Bandit` (for Python) or SonarQube into the CI/CD pipeline to automatically identify potential security flaws in the UDIM codebase (e.g., hardcoded secrets (though config management should prevent this), use of insecure functions).
    *   **Dynamic Application Security Testing (DAST) (Conceptual for later, more mature stages):**
        *   Run automated DAST tools against a deployed UDIM instance in a test environment to probe for common web API vulnerabilities (e.g., OWASP Top 10 related issues like injection, broken authentication, etc.).
    *   **Penetration Testing (Conceptual for later, broader EchoSphere scope):**
        *   Schedule periodic manual penetration testing by qualified security professionals covering UDIM and its interactions within the EchoSphere ecosystem.
*   **Focus for UDIM:** Secure handling of sensitive data in transit and at rest, robust authentication and authorization for all API operations, protection against common web API vulnerabilities (e.g., related to file uploads, input handling).

## 5. Performance & Load Testing (Conceptual for later stages, but considered in design)

*   **Objective:** To ensure UDIM can handle the expected volume of concurrent users and data uploads/imports, performing within acceptable latency and error rate limits.
*   **Scope:**
    *   High-traffic endpoints: `POST /v1/users/{userID}/data/upload` and potentially `POST /v1/users/{userID}/connections/{connectionID}/import`.
    *   Internal interactions: Performance of S3 uploads, database writes, SQS publishing under load.
*   **Tools:** Locust, k6, Apache JMeter.
*   **Metrics:**
    *   Requests per second (RPS) supported.
    *   Latency (average, p95, p99) for API responses.
    *   Error rates under various load levels.
    *   Resource utilization (CPU, memory, network I/O) of UDIM services and backing resources (database, S3, SQS).
*   **Considerations for UDIM Design (already incorporated):**
    *   Use of asynchronous request processing in FastAPI.
    *   Scalable cloud services (S3, SQS, managed PostgreSQL/QLDB).
    *   Efficient database queries and connection pooling.
    *   Stateless service design to allow easy horizontal scaling.

## 6. Usability Testing (for API - Developer Experience)

*   **Objective:** To ensure the UDIM's external APIs (primarily for direct upload and potentially data source connection management if third-party devs use it) are clear, well-documented, consistent, and easy for developers to integrate with.
*   **Techniques:**
    *   **API Documentation Review:** Thoroughly review the auto-generated OpenAPI (Swagger) specification for clarity, accuracy, and completeness. Ensure all parameters, request/response bodies, and error codes are well-described with examples.
    *   **Internal "Dogfooding":** Have other internal teams (e.g., frontend team, or teams building services that might call UDIM in future phases) review and attempt to integrate with the API to gather feedback.
    *   **Sample Client Implementation:** Develop simple example clients or scripts that use the API to perform common tasks, which can highlight usability issues.
    *   **Feedback Collection:** Establish a channel for developers (initially internal) to provide feedback on the API design and documentation.

## General Testing Principles

*   **Automation:** Automate all levels of testing (unit, integration, E2E where practical) and integrate them into the CI/CD pipeline to ensure continuous quality feedback.
*   **Isolation:** Unit tests must mock all external dependencies. Integration tests should use dedicated test instances of databases/services or reliable mocks. Test environments should be isolated.
*   **Repeatability:** Tests must be deterministic, producing the same results when run multiple times with the same setup and inputs.
*   **Early Testing:** Write tests concurrently with feature development (Test-Driven Development or Behavior-Driven Development practices are encouraged).
*   **Comprehensive Coverage:** While aiming for high code coverage with unit tests, the overall strategy should ensure thorough testing of critical business logic, API contracts, security requirements, and integration points.
*   **Test Data Management:**
    *   Develop a strategy for generating and managing test data (e.g., sample files of different types/sizes, mock user accounts, pre-generated consent tokens for test scenarios).
    *   Ensure no real sensitive user data is ever used in test environments. Use anonymized or synthetic data where appropriate.
    *   Isolate test data to prevent interference between test runs.
```
