# Phase 1: AI Persona Analysis & Trait Extraction (MAIPP) - Testing Strategies

This document outlines the testing strategies for the AI Persona Analysis & Trait Extraction (MAIPP) module of EchoSphere's Phase 1. The approach covers various levels and types of testing to ensure the complex data processing pipelines, AI model integrations, and data storage interactions function correctly and reliably.

## 1. Unit Testing

*   **Objective:** To verify the correctness of individual functions, methods, classes, and small components within MAIPP in isolation.
*   **Scope:**
    *   **Data Transformation Functions:** Logic for converting raw AI model outputs into the `RawAnalysisFeatures` schema. Logic for transforming `RawAnalysisFeatures` into potential `ExtractedTraitCandidate` structures.
    *   **Helper Utilities:** Any utility functions used for text processing (e.g., text extraction from PDF/DOCX if done within MAIPP, specific text cleaning routines), audio feature extraction helpers (if custom logic beyond library calls), or PKG node/relationship property formatting.
    *   **Consent Verification Client Logic:** The part of the MAIPP code that constructs requests to and parses responses from the (mocked) internal Consent Verification API.
    *   **Individual AI Model Client Wrappers:** If specific wrapper classes or functions are created to interact with AI APIs (e.g., formatting requests, parsing responses, handling specific errors for an OpenAI call), these wrappers should be unit tested with the external API call mocked.
    *   **Trait Derivation Rules:** If there's rule-based logic for suggesting traits from features (e.g., "if sentiment score > X and topic Y is present, suggest trait Z"), these rules should be unit tested with various feature inputs.
    *   **Pydantic Models (if used for internal data structures):** Validation logic within these models.
*   **Tools:**
    *   `pytest`: Primary Python testing framework.
*   **Techniques:**
    *   **Mocking:** Extensive use of `unittest.mock` or `pytest-mock` to simulate responses from:
        *   External AI APIs (OpenAI, Google Gemini, Hugging Face Inference Endpoints, etc.).
        *   Internal Consent Verification API.
        *   Database interactions (MongoDB for `RawAnalysisFeatures`, PostgreSQL for `ExtractedTraitCandidate`, Graph Database for PKG).
        *   Secure data decryption service (KMS interactions).
    *   **Parameterized Testing (`pytest.mark.parametrize`):** For testing data transformation and rule-based logic with diverse inputs and edge cases.
    *   **Fixtures (`pytest.fixture`):** To create reusable mock data (e.g., sample AI API responses, sample `UserDataPackage` details, sample feature sets).
    *   **Code Coverage (`pytest-cov`):** Aim for high unit test coverage, particularly for data transformation and business logic components.

## 2. Integration Testing

*   **Objective:** To verify the interactions between different components of MAIPP and with external services it directly depends on (AI APIs, databases, consent service).
*   **Scope:**
    *   **AI Model Integration Tests:**
        *   For each AI service integrated (e.g., OpenAI GPT, Google Gemini, specific Hugging Face models, STT services):
            *   Test the actual API call with sample valid input data (non-sensitive, test data).
            *   Verify that the MAIPP client correctly authenticates, sends the request, and successfully parses the expected response structure from the live (or sandboxed) AI service.
            *   Test handling of common API errors (e.g., rate limits, invalid input, authentication failure) from the live AI service.
            *   Focus on testing the *integration contract* (request/response schema, auth) rather than the AI model's output quality (which is a different type of evaluation).
    *   **Database Integration (`RawAnalysisFeatures` - MongoDB):**
        *   Test that `RawAnalysisFeatures` documents are correctly formatted and saved to a test MongoDB instance.
        *   Test retrieval of these documents by `userID` or `sourceUserDataPackageID`.
    *   **Database Integration (`ExtractedTraitCandidate` - PostgreSQL):**
        *   Test that `ExtractedTraitCandidate` records are correctly saved to a test PostgreSQL instance with correct relations and data types.
        *   Test retrieval and filtering of these records (e.g., by `userID`, `status`).
    *   **Graph Database Integration (PKG - Neo4j/Neptune):**
        *   Test creation of `User`, `Trait`, `Concept`, `SourceDataReferenceNode`, etc., nodes in a test graph database instance.
        *   Test creation of specified relationships (e.g., `:HAS_CANDIDATE_TRAIT`, `:EVIDENCED_BY`) with correct properties.
        *   Test basic graph traversal queries that MAIPP might use internally (e.g., to check if a concept already exists).
    *   **Consent Verification Workflow:**
        *   Test the MAIPP flow where it receives a `UserDataPackage`, retrieves the `consentTokenID`, and then calls the (mocked) Consent Verification API for various required scopes (e.g., text analysis, sentiment analysis).
        *   Verify that MAIPP correctly proceeds or halts specific analysis paths based on the mocked consent responses (`isValid: true/false`).
    *   **Secure Data Decryption Flow:**
        *   Test the interaction with the KMS (mocked or using a test KMS with test keys) to retrieve decryption keys and the subsequent decryption of sample encrypted data (e.g., a small encrypted file fetched from a test S3 bucket). Ensure decrypted data is handled correctly and disposed of.
*   **Tools:**
    *   `pytest`: For orchestrating integration tests.
    *   `httpx` or Python SDKs (`openai`, `google-cloud-aiplatform`, etc.): For making live calls to sandboxed/test tiers of AI APIs (if available and cost-effective) or to carefully controlled live APIs with test accounts.
    *   `pymongo` / `motor`: For MongoDB interactions.
    *   `psycopg2` / `asyncpg` / SQLAlchemy: For PostgreSQL interactions.
    *   `neo4j` driver / `gremlinpython`: For graph database interactions.
    *   `boto3`: For KMS and S3 interactions (against test resources or mocked with `moto`/`LocalStack`).
    *   `docker-compose`: To spin up local instances of MongoDB, PostgreSQL, Neo4j/Neptune (if local versions exist), or mocks like `moto` server for a self-contained integration test environment.

## 3. Workflow/Pipeline Testing (End-to-End within MAIPP)

*   **Objective:** To verify the entire MAIPP processing pipeline for a given `UserDataPackage` from notification receipt to PKG update, ensuring all internal stages and integrations function together.
*   **Scope:**
    *   Simulate a notification from UDIM (e.g., by placing a message on a test SQS queue that MAIPP listens to, or by calling MAIPP's entry point with `UserDataPackage` details).
    *   Use a sample (non-sensitive) raw data file (e.g., a text document, an audio snippet).
    *   Mock the Consent Verification API to return specific permissions for the test.
    *   Mock the KMS to allow decryption of the sample data.
    *   Allow calls to actual (sandboxed/test tier if possible) AI APIs for feature extraction.
    *   Verify:
        *   Correct parsing of input and decryption.
        *   Appropriate AI models are called based on `dataType` and mocked consent.
        *   `RawAnalysisFeatures` are generated and stored correctly in the test MongoDB.
        *   `ExtractedTraitCandidate`s are derived and stored correctly in the test PostgreSQL.
        *   The test Persona Knowledge Graph (PKG) is populated with expected nodes and relationships.
        *   The `UserDataPackage` status is updated correctly (via mocked UDIM interaction or direct DB check).
        *   Decrypted data is properly disposed of.
*   **Tools:**
    *   `pytest` for orchestration.
    *   Workflow engine's CLI or client library if MAIPP uses Airflow/Kubeflow (for triggering and monitoring test pipeline runs).
    *   Tools to inspect contents of MongoDB, PostgreSQL, Graph DB, and SQS (if used for internal MAIPP sub-task queuing).
    *   Mocks for Consent Verification API and potentially for some AI APIs if live calls are too slow/costly for all E2E tests (focus on testing one live AI path and mocking others).

## 4. AI Model Output Quality Evaluation (Offline/Iterative Process - distinct from functional testing)

*   **Objective:** To assess and improve the quality, relevance, and accuracy of the features extracted by AI models and the trait candidates derived from them. This is less about pass/fail of code and more about the effectiveness of the AI.
*   **Scope:**
    *   Evaluate the outputs of individual AI models (e.g., sentiment analysis accuracy, NER precision/recall, topic model coherence, STT Word Error Rate).
    *   Evaluate the relevance and correctness of `ExtractedTraitCandidate`s.
    *   Evaluate the structure and content of the initial PKG.
*   **Techniques:**
    *   **Golden Datasets:** Create or acquire labeled datasets for specific tasks (e.g., text with known sentiment, audio with manual transcripts, documents with pre-identified traits). Run MAIPP components on this data and compare AI outputs against labels.
    *   **Human Evaluation & Annotation:** Subject Matter Experts (SMEs) or annotators review samples of `RawAnalysisFeatures` and `ExtractedTraitCandidate`s for accuracy, relevance, and potential biases. This feedback is crucial for refining AI models, prompts, and trait derivation logic.
    *   **Benchmarking:** Compare different AI models or prompting strategies for the same task to select the best performers.
    *   **Error Analysis:** Deep dive into common errors made by the AI components to understand root causes and guide improvements.
*   **Tools:**
    *   Annotation tools (e.g., Label Studio, Doccano, Prodigy).
    *   Spreadsheets or databases for tracking evaluation results.
    *   Python libraries for metrics calculation (scikit-learn for classification/regression metrics, NLTK/spaCy for NLP metrics).
*   **Note:** This is an ongoing, iterative process that feeds back into AI model selection, fine-tuning (Phase 2), prompt engineering, and the logic for `ExtractedTraitCandidate` generation.

## 5. Security Testing (MAIPP Specifics)

*   **Objective:** To identify and mitigate security vulnerabilities specifically within MAIPP's data handling and processing logic.
*   **Scope & Techniques:**
    *   **Secure Handling of Decrypted Data:** Verify that decrypted data from `UserDataPackage`s is only held in memory or secure ephemeral storage for the minimum time necessary and is properly disposed of after processing. Test for potential leaks or unintended persistence.
    *   **Authentication to AI APIs:** Ensure API keys and authentication tokens for external AI services are securely stored (e.g., using a secrets manager like HashiCorp Vault or cloud provider's secret manager) and transmitted.
    *   **Input Validation for Internal APIs (if MAIPP exposes any):** If MAIPP components communicate via internal APIs, ensure these have proper validation.
    *   **Permissions for Database/Storage Access:** Ensure MAIPP service roles/accounts have least-privilege access to MongoDB, PostgreSQL, Graph DB, and S3 (e.g., only write permissions for its own data, read-only for `UserDataPackage` metadata if accessed directly).
    *   **Dependency Scanning & SAST:** Same as UDIM (Bandit, pip-audit, etc.) applied to MAIPP codebase.
*   **Focus for MAIPP:** Protecting sensitive user data during its transformation by AI, secure interaction with AI APIs, and integrity of the analytical results it produces.

## 6. Performance Testing (Conceptual for later, consider in design)

*   **Objective:** To ensure MAIPP can process `UserDataPackage`s within acceptable timeframes and handle the expected throughput.
*   **Scope:** The entire MAIPP pipeline for different data types and sizes. Performance of individual AI model calls. Database write performance for features and traits.
*   **Tools:** Load testing tools if MAIPP has an API entry point (e.g., for reprocessing). Profiling tools (e.g., `cProfile`, `Pyinstrument` for Python) to identify bottlenecks in the code. Cloud monitoring tools to observe resource utilization of MAIPP services and databases.
*   **Metrics:** End-to-end processing time per `UserDataPackage`, throughput (packages processed per unit of time), latency of individual AI API calls, resource utilization.
*   **Considerations for MAIPP Design:** Asynchronous processing of AI tasks, batching database writes, optimizing AI model parameters (e.g., smaller models for some tasks if quality is acceptable), horizontal scaling of MAIPP workers/services.

## General Testing Principles (Consistent with UDIM)

*   **Automation:** CI/CD integration for all automated test suites.
*   **Isolation:** Maintain isolation for unit and integration tests.
*   **Repeatability:** Ensure tests are deterministic.
*   **Early Testing:** Write tests alongside development.
*   **Test Data Management:** Use non-sensitive, representative test data. For AI model output quality, curated golden datasets are key. Anonymize or synthesize data where necessary.
```
