# Phase 1: AI Persona Analysis & Trait Extraction (MAIPP) - Preliminary Implementation Tasks

This document breaks down the development work for the AI Persona Analysis & Trait Extraction (MAIPP) module of EchoSphere's Phase 1 into manageable tasks, based on its defined Data Models, Core Logic, and Technology Stack.

## 1. Project Setup & Core Infrastructure (MAIPP Service/Orchestrator)

*   **Task 1.1: Initialize MAIPP Service Repository (if separate from UDIM).**
    *   Description: Set up a Git repository for the MAIPP service/orchestrator. Standard Python project structure.
*   **Task 1.2: Basic CI/CD Pipeline for MAIPP.**
    *   Description: Minimal CI pipeline (linters, placeholders for unit tests).
*   **Task 1.3: MAIPP Orchestration Framework Setup (FastAPI or Workflow Engine).**
    *   Description:
        *   If FastAPI: Set up the main application, routers, and core orchestration logic structure.
        *   If Airflow/Kubeflow: Define basic DAG/pipeline structure for data package processing.
*   **Task 1.4: Logging & Configuration Management for MAIPP.**
    *   Description: Implement structured logging and configuration management (Pydantic `BaseSettings`) similar to UDIM.
*   **Task 1.5: Dockerization of MAIPP Service/Workers.**
    *   Description: Create `Dockerfile`(s) for the MAIPP orchestration component and any custom AI model serving components (if not using purely API-based AI services).

## 2. Data Handling & Security

*   **Task 2.1: Secure Data Retrieval & Decryption Logic.**
    *   Description: Implement logic to receive `UserDataPackage` details (e.g., from SQS message). Develop the secure process to retrieve the `encryptionKeyID` and use it with the chosen KMS (e.g., AWS KMS via Boto3) to decrypt the raw data stream fetched from object storage (e.g., S3). Ensure decrypted data is handled ephemerally.
*   **Task 2.2: Input Data Preprocessing & Normalization.**
    *   Description: Implement functions to prepare input data for various AI models (e.g., text extraction from PDF/DOCX using `pypdf2`/`python-docx`, audio resampling using `librosa`, image normalization if applicable).

## 3. Consent Verification Integration (MAIPP Side)

*   **Task 3.1: Client for Internal Consent Verification API.**
    *   Description: Develop/reuse the asynchronous HTTP client within MAIPP to call the internal Consent Verification API (`GET /internal/consent/v1/verify`).
*   **Task 3.2: Granular Consent Check Logic.**
    *   Description: Before each specific AI analysis (e.g., sentiment, topic modeling, voice emotion), implement logic to determine the `requiredScope` and call the Consent Verification API. Ensure processing is skipped if consent is not valid for that specific scope.

## 4. AI Model Integration & Feature Extraction

*   **Task 4.1: Text Analysis Pipeline Integration.**
    *   **Task 4.1.1: LLM Integration (e.g., Google Gemini, OpenAI GPT).**
        *   Description: Implement client code to call chosen LLM APIs for tasks like summarization, topic extraction, NER, and complex pattern recognition. Handle API authentication, request formatting, and response parsing.
    *   **Task 4.1.2: Hugging Face Transformers Integration (Sentiment/Emotion).**
        *   Description: Implement logic to use pre-trained Hugging Face models (e.g., for sentiment, emotion from text). This might involve loading models locally or calling Hugging Face Inference Endpoints.
    *   **Task 4.1.3: Basic Text Stats Calculation.**
        *   Description: Implement logic for basic text statistics (word count, readability).
*   **Task 4.2: Audio Analysis Pipeline Integration.**
    *   **Task 4.2.1: Speech-to-Text (STT) Integration (e.g., OpenAI Whisper).**
        *   Description: Implement client code to call chosen STT API. Handle audio data streaming/batching and transcript retrieval.
    *   **Task 4.2.2: Voice Characteristics Analysis (Prosody/Metrics).**
        *   Description: Integrate libraries like `Librosa` or `parselmouth` (for Praat) to extract features like pitch, speech rate, jitter, shimmer from audio data.
    *   **Task 4.2.3: Voice Emotion/Sentiment Model Integration (e.g., HF Wav2Vec2).**
        *   Description: Implement logic to use pre-trained models for analyzing emotion/sentiment directly from audio.
*   **Task 4.3: (Conceptual) Multimodal Analysis Integration (e.g., Google Gemini).**
    *   Description: If tackling advanced multimodal tasks in Phase 1, implement client code to send combined text/audio/image data to Gemini API and parse its fused insights.
*   **Task 4.4: `RawAnalysisFeatures` Record Creation.**
    *   Description: For each AI model output, implement logic to structure the results into the `RawAnalysisFeatures` data model format.

## 5. Storage of Analysis Outputs

*   **Task 5.1: `RawAnalysisFeatures` Storage (MongoDB).**
    *   Description: Implement logic to connect to MongoDB (or chosen document DB/object storage) and save `RawAnalysisFeatures` records. Ensure appropriate indexing is configured on MongoDB.
*   **Task 5.2: `ExtractedTraitCandidate` Storage (PostgreSQL).**
    *   Description: Implement logic to connect to PostgreSQL and save `ExtractedTraitCandidate` records. Define and run database migrations for this table (Alembic).

## 6. Trait Candidate Derivation & Synthesis

*   **Task 6.1: Initial Trait Derivation Logic.**
    *   Description: Develop initial rule-based or simple ML-based logic to map specific `RawAnalysisFeatures` to potential `ExtractedTraitCandidate`s. (E.g., high frequency of question marks -> "Inquisitive Questioning Style" candidate). Define how `supportingEvidenceSnippets`, `confidenceScore`, `originatingModels`, etc., are populated.
*   **Task 6.2: Trait Candidate Aggregation & Deduplication.**
    *   Description: Implement a basic mechanism to aggregate trait candidates generated from different analyzers for the same `UserDataPackage` and perform simple deduplication or merging of very similar candidates.

## 7. Persona Knowledge Graph (PKG) Initial Population

*   **Task 7.1: Graph Database Client Setup (e.g., Neo4j, Neptune).**
    *   Description: Implement client code to connect to the chosen graph database. Handle authentication and session management.
*   **Task 7.2: Node Creation Logic (`User`, `Trait`, `Concept`, `SourceDataReferenceNode`, etc.).**
    *   Description: Develop functions to create or get existing nodes in the PKG based on `userID`, `ExtractedTraitCandidate` data, and identified concepts from `RawAnalysisFeatures`. Ensure properties are correctly mapped.
*   **Task 7.3: Relationship Creation Logic.**
    *   Description: Develop functions to create relationships between nodes (e.g., `(User)-[:HAS_CANDIDATE_TRAIT]->(Trait)`, `(Trait)-[:EVIDENCED_BY]->(SourceDataReferenceNode)`), including setting properties on these relationships.
*   **Task 7.4: PKG Update Orchestration.**
    *   Description: Implement the main logic flow for updating the PKG based on new trait candidates and raw features, ensuring idempotency where possible.

## 8. Internal State Management & Error Handling

*   **Task 8.1: Update `UserDataPackage` Status.**
    *   Description: Implement logic to call an internal UDIM API (or directly update the database if permitted by architecture) to reflect the processing status of a `UserDataPackage` by MAIPP (e.g., 'processing_by_maipp', 'maipp_completed', 'maipp_error_X').
*   **Task 8.2: Robust Error Handling & Retries for External API Calls.**
    *   Description: Implement comprehensive error handling (timeouts, connection errors, API rate limits, specific API errors) for all calls to external AI services. Include retry mechanisms with exponential backoff where appropriate.
*   **Task 8.3: Secure Disposal of Decrypted Data.**
    *   Description: Ensure that any temporarily stored decrypted data is securely deleted from memory or ephemeral storage immediately after processing for that data segment is complete.

## 9. Testing

*   **Task 9.1: Unit Tests for MAIPP Components.**
    *   Description: Write unit tests for individual functions (e.g., feature mapping, trait derivation logic, data transformation), mocking AI model responses and database interactions.
*   **Task 9.2: Integration Tests for AI Model Clients.**
    *   Description: Test the client code for each integrated AI service, potentially against sandboxed/test versions of those APIs if available, or by carefully mocking their HTTP responses.
*   **Task 9.3: Integration Tests for Database Interactions.**
    *   Description: Test saving and retrieving `RawAnalysisFeatures` (MongoDB) and `ExtractedTraitCandidate` (PostgreSQL). Test PKG node and relationship creation/querying against a test graph database instance.
*   **Task 9.4: Workflow/Pipeline Integration Tests.**
    *   Description: Test the overall MAIPP orchestration flow for a sample `UserDataPackage` (mocking the decrypted data input and consent verification). Verify that the correct sequence of analysis, feature storage, trait candidate generation, and PKG updates (mocked DB calls) occurs.
*   **Task 9.5: Consent Verification Logic Tests.**
    *   Description: Specifically test the logic that checks consent before performing each type of analysis, ensuring it correctly permits or denies processing based on mocked Consent API responses.

## 10. Documentation

*   **Task 10.1: Internal MAIPP Documentation.**
    *   Description: Document the MAIPP architecture, data flows, individual component responsibilities, AI model integration details, and key decision points in the logic.
*   **Task 10.2: Configuration and Deployment Guide for MAIPP.**
    *   Description: Instructions on how to configure MAIPP (environment variables, service endpoints) and deploy it (Docker images, Kubernetes manifests if applicable).
```
