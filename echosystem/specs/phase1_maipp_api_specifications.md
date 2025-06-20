# Phase 1: AI Persona Analysis & Trait Extraction (MAIPP) - API & Interaction Specifications

This document details the Application Programming Interfaces (APIs) and other interaction patterns for the AI Persona Analysis & Trait Extraction (MAIPP) module in EchoSphere's Phase 1. MAIPP is primarily a backend processing module, so its "APIs" are largely internal or represent how it consumes messages and interacts with other services and third-party AI providers.

## I. Inbound Data Trigger (from UDIM via SQS)

MAIPP is triggered by messages from the User Data Ingestion Module (UDIM) indicating new data is ready for analysis.

### 1. SQS Message Consumption

*   **Queue Source:** A designated AWS SQS queue (e.g., `maipp-data-ready-queue.fifo` if order is important for specific user data, otherwise a standard queue). This queue is populated by UDIM.
*   **Message Payload Schema (JSON):**
    The message body will be a JSON object containing details of the `UserDataPackage` ready for processing. This aligns with the "Notify MAIPP API" payload defined in UDIM's API specification.
    ```json
    {
      "packageID": "a1b2c3d4-e5f6-7890-1234-567890abcdef", // UserDataPackage.packageID (UUID)
      "userID": "user_uuid_placeholder_123", // UUID
      "consentTokenID": "consent_uuid_placeholder_789", // UUID
      "rawDataReference": "s3://echosphere-user-data-bucket/user_uuid_placeholder_123/a1b2c3d4-e5f6-7890-1234-567890abcdef/data.enc", // String URI
      "dataType": "text/plain", // String (MIME type)
      "sourceDescription": "Direct Upload: My daily journal.txt", // String
      "metadata": { // Optional JSON object from UserDataPackage.metadata
        "originalFilename": "My daily journal.txt",
        "fileSizeBytes": 102400,
        "custom_tags": ["journal", "personal"]
      }
    }
    ```
*   **Consumption Logic (Conceptual):**
    1.  **Polling/Receiving:** MAIPP worker instances continuously poll the SQS queue for new messages.
    2.  **De-serialization & Validation:** Upon receiving a message, MAIPP de-serializes the JSON payload and validates its structure and required fields (e.g., using Pydantic models).
    3.  **Error on Invalid Message:** If the message is malformed or missing critical information:
        *   Log the error with the message content.
        *   Move the message to a configured Dead-Letter Queue (DLQ) for MAIPP.
        *   Acknowledge the original message to remove it from the main queue.
    4.  **Initiate Analysis Workflow:** If the message is valid, MAIPP initiates its internal analysis workflow for the specified `packageID` and `userID`, using the provided details. (See MAIPP Core Logic document for workflow details).
    5.  **Message Deletion from Queue:** After successfully initiating processing (or after moving to DLQ), MAIPP deletes the message from the SQS queue to prevent reprocessing. This is typically handled by the SQS SDK upon successful processing of the `receive_message` call.
    6.  **Error Handling during Workflow Initiation:** If MAIPP fails to even *start* the workflow (e.g., due to a critical internal configuration issue before any actual data processing begins):
        *   Log the error.
        *   Do *not* delete the message from the SQS queue immediately. Allow SQS visibility timeout to expire, so the message can be retried a few times.
        *   If retries are exhausted (based on SQS redrive policy), the message will automatically go to the DLQ.
        *   Update `UserDataPackage` status to an error state (e.g., `error_maipp_initiation_failed`).

## II. Internal Service Interactions (MAIPP initiated)

MAIPP initiates several internal interactions to fulfill its processing tasks.

### 1. Data Retrieval (from Secure Storage - e.g., AWS S3)

*   **Interaction Type:** Direct AWS SDK calls (using `boto3` for Python).
*   **Inputs (for MAIPP logic):**
    *   `packageID` (UUID): To fetch `UserDataPackage` metadata.
    *   (From fetched metadata) `rawDataReference` (String - S3 URI).
    *   (From fetched metadata) `encryptionKeyID` (String - ARN of the AWS KMS key).
*   **Logic:**
    1.  **Fetch `UserDataPackage` Metadata:** MAIPP queries UDIM's PostgreSQL database (or an internal cache/replica if available) using the `packageID` from the SQS message to retrieve the full `UserDataPackage` record, which includes `rawDataReference` and `encryptionKeyID`.
        *   **Internal API/DB Call:** `SELECT encryptionKeyID, rawDataReference FROM UserDataPackage WHERE packageID = :packageID;`
    2.  **Download Encrypted Object from S3:** Use the `boto3` S3 client's `download_file` or `get_object` method with the `rawDataReference` (Bucket and Key).
    3.  **Decrypt Object using KMS:**
        *   If using S3 Server-Side Encryption with KMS-managed keys (SSE-KMS), decryption is largely transparent during the `get_object` call, provided MAIPP's IAM role has `kms:Decrypt` permission on the `encryptionKeyID` and `s3:GetObject` on the S3 object. The S3 client handles the KMS interaction.
        *   If client-side encryption was used by UDIM (less likely for UDIM's primary storage, but if so), MAIPP would download the encrypted object, then explicitly call KMS `decrypt` with the ciphertext of the data encryption key (stored as object metadata), then use the plaintext data key to decrypt the object data. This is more complex and SSE-KMS is preferred.
*   **Output:** Decrypted data stream or temporary local file for analysis by AI models.
*   **Security:**
    *   MAIPP's IAM role MUST have `s3:GetObject` permission on the specific S3 bucket/path where user data is stored.
    *   MAIPP's IAM role MUST have `kms:Decrypt` permission on the KMS keys used for encrypting user data. KMS key policies should restrict this permission to only be callable by MAIPP's role and potentially only for specific encryption contexts if used.
    *   Decrypted data MUST be handled in memory or secure ephemeral storage and be purged immediately after the relevant analysis step is complete.

### 2. Consent Verification (Interaction with UCMS/Consent Service)

*   **API Endpoint (Internal - Called by MAIPP):** `GET /internal/consent/v1/verify` (This API is hosted by the Universal Consent Management Service - UCMS, or its Phase 1 precursor).
*   **Usage by MAIPP:**
    *   Before performing any specific type of AI analysis on the decrypted data (e.g., sentiment analysis on text, emotion extraction from audio, topic modeling), MAIPP must verify explicit user consent for that action.
    *   MAIPP constructs a `requiredScope` string or JSON object that precisely describes the analysis about to be performed. Examples:
        *   `action:analyze_text_sentiment,resource_category:text_from_package:${packageID}`
        *   `action:extract_audio_emotion,resource_category:audio_from_package:${packageID}`
        *   `action:generate_text_summary_llm,model_type:generative_llm,resource_category:text_from_package:${packageID}`
    *   MAIPP calls the `GET /internal/consent/v1/verify` endpoint with:
        *   `userID` (from the SQS message)
        *   `consentTokenID` (from the SQS message / `UserDataPackage` metadata)
        *   The specific `requiredScope`
        *   Optionally, `dataHash` if the consent is tied to a specific data hash and MAIPP can reliably use/derive it.
*   **Action Based on Response:**
    *   If the API response indicates `isValid: false`, MAIPP logs this consent denial for the specific scope and **MUST NOT** perform that particular analysis step. It may proceed with other analysis steps for which consent *is* granted.
    *   If `isValid: true`, MAIPP proceeds with the authorized analysis.

### 3. AI Service Provider Interactions (Generic Adapter Pattern)

MAIPP acts as an orchestrator, calling various third-party AI APIs. A generic internal adapter pattern is used to standardize these interactions.

*   **Generic Internal Adapter Interface (Conceptual Python):**
    ```python
    class AIModelAdapter:
        async def analyze(self, data_input: Any, analysis_type: str, model_config: Dict, api_key_ref: str) -> Dict:
            # 1. Securely retrieve API key using api_key_ref from secrets manager
            # 2. Transform data_input and model_config into provider-specific request format
            # 3. Make the HTTP call to the AI provider's API endpoint
            # 4. Handle provider-specific responses (success, errors, rate limits)
            # 5. Transform provider's response into MAIPP's standardized
            #    RawAnalysisFeatures.extractedFeatures schema for this analysis_type
            # 6. Implement retry logic for transient errors
            pass
    ```
*   **Inputs to `analyze` method:**
    *   `data_input`: The actual data (e.g., string of text, path to temporary audio file, image bytes).
    *   `analysis_type`: An ENUM or string constant identifying the specific analysis (e.g., `TEXT_SENTIMENT_OPENAI`, `AUDIO_TRANSCRIPTION_WHISPER`, `MULTIMODAL_FUSED_INSIGHTS_GEMINI`). This helps select the correct adapter and internal parsing logic.
    *   `model_config`: JSON object specifying the exact model name/version (e.g., `gpt-4-1106-preview`, `claude-3-opus-20240229`, `gemini-1.0-pro-vision`) and any provider-specific parameters (e.g., `temperature`, `max_tokens`, `language`, specific sub-prompts or instructions for the AI model).
    *   `api_key_ref`: A reference string (e.g., `secretsmanager_arn_openai_api_key`) used by a centralized secrets management client within MAIPP to securely fetch the actual API key. **API keys are NOT passed directly in this interface.**
*   **Standardized Internal Request/Response Data Formats:**
    *   **Requests (Internal to MAIPP before adapter):** MAIPP might have an internal standardized structure for each `analysis_type` before it's passed to the specific adapter. For example, for `TEXT_NER`:
        ```json
        { "text_content": "The quick brown fox jumps over EchoSphere.", "language_hint": "en" }
        ```
        The adapter for `TEXT_NER_OPENAI` would translate this into OpenAI's specific API request format.
    *   **Responses (Internal from adapter back to MAIPP core):** Adapters MUST transform the AI provider's native response into MAIPP's defined `RawAnalysisFeatures.extractedFeatures` schema for that `analysis_type` and `modality`. This ensures consistency for downstream storage and trait derivation.
        *   Example for `TEXT_NER` (standardized internal MAIPP format):
            ```json
            {
              "named_entities": [ {"text": "EchoSphere", "type": "ORG", "start_char": 30, "end_char": 40, "confidence": 0.95} ],
              "language_detected": "en", // if applicable
              "model_version_used": "gpt-4-1106-preview_ner_v1.2" // specific model version from provider if available
            }
            ```
*   **API Key Management:**
    *   MAIPP includes a secure component/client for a secrets management system (e.g., AWS Secrets Manager, HashiCorp Vault, Google Secret Manager).
    *   The `api_key_ref` is used by this client to fetch the actual API key at runtime.
    *   MAIPP's IAM role/service account needs permission to access these specific secrets.
*   **Error Handling within Adapters:**
    *   Adapters must catch common HTTP errors (4xx, 5xx), authentication errors, rate limit errors, and timeout errors from AI providers.
    *   Implement retry mechanisms (with exponential backoff and jitter) for transient errors (e.g., 429 Too Many Requests, 503 Service Unavailable).
    *   Log detailed error information from the provider.
    *   Return a standardized error object to the MAIPP orchestrator if an error persists after retries, so MAIPP can record a `RawAnalysisFeatures` entry with `status: 'failure'` and relevant `errorDetails`.

### 4. Persona Knowledge Graph (PKG) Service Interaction

MAIPP is responsible for the initial population of the PKG based on its analysis. It interacts with a dedicated PKG Service (which fronts the graph database like Neo4j or Neptune).

*   **API Endpoints (Internal, hosted by PKG Service, called by MAIPP):**

    *   **Endpoint A: `POST /internal/pkg/v1/users/{userID}/trait-candidates` (If `ExtractedTraitCandidate` is primarily managed by PKG Service)**
        *   **Description:** MAIPP sends fully formed `ExtractedTraitCandidate` objects (as per its data model) to be stored or updated by the PKG service. This might be used if the PKG service itself manages the lifecycle of candidates before they become confirmed traits.
        *   **Authentication:** Secure internal service-to-service.
        *   **Request Body (JSON):** A single `ExtractedTraitCandidate` object or an array of them.
            ```json
            // Example: Single object
            {
              "candidateID": "traitcand_uuid_placeholder_001", // Can be pre-generated by MAIPP
              "userID": "user_uuid_placeholder_123",
              "traitName": "Inquisitive Questioning Style",
              // ... other fields from ExtractedTraitCandidate model
              "status": "candidate" // Initial status
            }
            ```
        *   **Response (Success - 201 Created or 200 OK):**
            ```json
            {
              "candidateID": "traitcand_uuid_placeholder_001",
              "status": "created_in_pkg_as_candidate" // Or similar confirmation
            }
            ```
        *   **Error Handling:** Standard API errors (400 for bad request, 500 for PKG service error).

    *   **Endpoint B: `POST /internal/pkg/v1/users/{userID}/graph/batch-update` (Primary mechanism for PKG population)**
        *   **Description:** Allows MAIPP to send a batch of operations to directly create/update nodes (Users, Concepts, Emotions, SourceDataReferences) and relationships in the graph based on its analysis. This is more powerful and flexible for initial PKG structuring.
        *   **Authentication:** Secure internal service-to-service.
        *   **Request Body (JSON):**
            ```json
            {
              "userID": "user_uuid_placeholder_123", // Often redundant if in path, but good for payload self-containment
              "operations": [
                {
                  "type": "MERGE_NODE", // Create if not exists, or match if exists
                  "label": "User",
                  "lookup_properties": {"userID": "user_uuid_placeholder_123"},
                  "set_properties": {"lastAnalyzedByMAIPP": "2024-03-17T10:00:00Z"}
                },
                {
                  "type": "MERGE_NODE",
                  "label": "Concept",
                  "lookup_properties": {"name": "AI Ethics"}, // Normalized concept name
                  "set_properties": {"conceptID": "concept_uuid_001", "description": "Branch of ethics..."}
                },
                {
                  "type": "MERGE_RELATIONSHIP",
                  "from_node": {"label": "User", "lookup_properties": {"userID": "user_uuid_placeholder_123"}},
                  "to_node": {"label": "Concept", "lookup_properties": {"name": "AI Ethics"}},
                  "relationship_type": "MENTIONED_CONCEPT",
                  "properties": {"frequency": 5, "sentiment_avg": 0.6, "sourcePackageID": "package_uuid_abc"}
                },
                // Operations to create Trait nodes (initially as candidates) and link them
                {
                  "type": "MERGE_NODE",
                  "label": "Trait", // Could be "TraitCandidateNode" initially
                  "lookup_properties": {"traitID": "traitcand_uuid_placeholder_001"}, // From ExtractedTraitCandidate
                  "set_properties": {
                      "name": "Inquisitive Questioning Style",
                      "category": "LinguisticStyle",
                      "status_in_pkg": "candidate_from_maipp", // PKG's internal status
                      // ... other properties from ExtractedTraitCandidate
                  }
                },
                {
                  "type": "MERGE_RELATIONSHIP",
                  "from_node": {"label": "User", "lookup_properties": {"userID": "user_uuid_placeholder_123"}},
                  "to_node": {"label": "Trait", "lookup_properties": {"traitID": "traitcand_uuid_placeholder_001"}},
                  "relationship_type": "HAS_CANDIDATE_TRAIT",
                  "properties": {"confidenceScore": 0.85, "addedByMAIPP": true}
                }
                // Could also include raw Cypher/Gremlin queries if PKG service supports that directly,
                // but structured operations are generally safer for inter-service communication.
              ]
            }
            ```
        *   **Response (Success - 200 OK):**
            ```json
            {
              "userID": "user_uuid_placeholder_123",
              "operations_attempted": 5,
              "operations_succeeded": 5,
              "operations_failed": 0,
              "errors": [] // Array of error details if any failures
            }
            ```
        *   **Error Handling:** The PKG service should return detailed error messages for failed operations, allowing MAIPP to log issues or potentially retry certain types of failures.
*   **Idempotency:**
    *   The PKG service, particularly for the `graph/batch-update` endpoint, should strive for idempotency. Using `MERGE` (in Cypher) or similar "get-or-create" logic for nodes and relationships ensures that if MAIPP reprocesses a message or sends the same update twice, it doesn't create duplicate entities in the PKG. Lookup properties are key to achieving this.
```
