# Phase 1: User Data Ingestion Module (UDIM) - Data Models

This document specifies the data models for the User Data Ingestion Module (UDIM) as part of EchoSphere's Phase 1. These models define the structure for handling raw user data intake, metadata, and associated user consent.

## 1. `UserDataPackage` Data Model

**Objective:** To define the structure for temporarily and securely holding incoming raw user data and its immediate metadata before it is processed by the AI Persona Analysis & Trait Extraction module (MAIPP). This record acts as a manifest for a given data ingestion event.

| Attribute           | Data Type                                  | Constraints                                                                                                | Description                                                                                                                               | Indexing Suggestion                     |
|---------------------|--------------------------------------------|------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------|
| `packageID`         | UUID                                       | NOT NULL, PRIMARY KEY, DEFAULT gen_random_uuid()                                                           | Unique identifier for this data package.                                                                                                  | Yes (Primary Key)                       |
| `userID`            | UUID                                       | NOT NULL, REFERENCES User(`userID`)                                                                        | Identifier of the user who owns and provided this data. Assumes a `User` table with `userID` as its primary key.                        | Yes (Foreign Key, for user-based queries) |
| `dataType`          | VARCHAR(128)                               | NOT NULL                                                                                                   | MIME type or a descriptive string for the data content (e.g., 'text/plain', 'audio/mpeg', 'video/mp4', 'application/pdf', 'image/jpeg'). | Yes (for filtering by data type)        |
| `sourceDescription` | VARCHAR(512)                               | NOT NULL                                                                                                   | User-provided or system-generated description of the data source (e.g., 'Direct Upload: MyJournal_2023.txt', 'Google Drive API Import: meeting_notes_project_alpha.gdoc', 'Twitter Archive Upload'). |                                         |
| `rawDataReference`  | VARCHAR(1024)                              | NOT NULL, UNIQUE                                                                                           | A secure reference (e.g., URI/URL) to the actual encrypted raw data stored externally (e.g., in AWS S3, Google Cloud Storage).           | Yes (for quick lookup if needed)        |
| `encryptionKeyID`   | VARCHAR(255)                               | NOT NULL                                                                                                   | Identifier or ARN of the encryption key used for this specific data package, managed by a Key Management Service (KMS).                   |                                         |
| `consentTokenID`    | UUID                                       | NOT NULL, REFERENCES ConsentLedgerEntry(`consentTokenID`)                                                  | Identifier linking this data package to a specific `ConsentLedgerEntry` that authorizes its collection and processing.                  | Yes (Foreign Key)                       |
| `uploadTimestamp`   | TIMESTAMP WITH TIME ZONE                   | NOT NULL, DEFAULT CURRENT_TIMESTAMP                                                                        | Timestamp of when the data package was successfully ingested and recorded.                                                              | Yes (for time-based queries/sorting)    |
| `metadata`          | JSONB                                      | NULLABLE                                                                                                   | Flexible field for storing additional, source-specific metadata. Examples: original filename, file size, image dimensions, audio duration, number of pages in PDF. Using JSONB allows for varied structures and efficient querying of nested elements. | Yes (GIN index if querying keys/values) |
| `status`            | ENUM('pending_processing', 'processing', 'processed', 'error_ingestion', 'error_processing') | NOT NULL, DEFAULT 'pending_processing'                                                                   | Current status of this data package within the ingestion and initial processing pipeline.                                               | Yes (for filtering by status)           |

**Conceptual JSON Representation of `UserDataPackage`:**

```json
{
  "packageID": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "userID": "user_uuid_placeholder_123",
  "dataType": "application/pdf",
  "sourceDescription": "Direct Upload: ResearchPaper_AI_Ethics.pdf",
  "rawDataReference": "s3://echosphere-user-data-bucket/user_uuid_placeholder_123/a1b2c3d4-e5f6-7890-1234-567890abcdef/ResearchPaper_AI_Ethics.pdf.enc",
  "encryptionKeyID": "arn:aws:kms:us-east-1:123456789012:key/key_uuid_placeholder_456",
  "consentTokenID": "consent_uuid_placeholder_789",
  "uploadTimestamp": "2024-03-15T10:30:00Z",
  "metadata": {
    "originalFilename": "ResearchPaper_AI_Ethics.pdf",
    "fileSizeBytes": 2048576,
    "totalPages": 15,
    "pdfVersion": "1.7"
  },
  "status": "pending_processing"
}
```

## 2. `ConsentLedgerEntry` Data Model

**Objective:** To define the structure for an immutable or cryptographically verifiable record of user consent. Each entry details the permissions granted by a user for a specific data processing activity or data sharing instance. This model is suitable for implementation on a Decentralized Ledger Infrastructure (DLI) or an immutable append-only database table.

| Attribute             | Data Type                               | Constraints                                                                                                                             | Description                                                                                                                                                                                                                              | Indexing Suggestion                               |
|-----------------------|-----------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------|
| `consentTokenID`      | UUID                                    | NOT NULL, PRIMARY KEY, DEFAULT gen_random_uuid()                                                                                        | Unique identifier for this consent grant. This ID is referenced by `UserDataPackage` or other modules that require consent verification.                                                                                             | Yes (Primary Key)                                 |
| `userID`              | UUID                                    | NOT NULL, REFERENCES User(`userID`)                                                                                                     | Identifier of the user granting the consent.                                                                                                                                                                                             | Yes (Foreign Key, for user-based queries)         |
| `dataHash`            | VARCHAR(256)                            | NOT NULL                                                                                                                                | Cryptographic hash (e.g., SHA-256) of the specific raw data (or a manifest of multiple data items) to which this consent applies. This ensures consent is tied to particular data, preventing re-application to different data.        | Yes (for linking consent to specific data proofs) |
| `consentScope`        | JSONB                                   | NOT NULL                                                                                                                                | A structured field detailing the granular permissions granted. See **`consentScope` Structure** below for details. Using JSONB allows for complex, nested permission structures.                                                        | Yes (GIN index for querying scope elements)       |
| `purposeDescription`  | TEXT                                    | NOT NULL                                                                                                                                | A human-readable description of why the data access or processing is being requested, explaining the benefit or functionality it enables.                                                                                              |                                                   |
| `processingDetails`   | JSONB                                   | NULLABLE                                                                                                                                | Optional field for more technical details about the processing, e.g., specific AI models or techniques to be used if user requests this level of detail.                                                                           |                                                   |
| `consentTimestamp`    | TIMESTAMP WITH TIME ZONE                | NOT NULL, DEFAULT CURRENT_TIMESTAMP                                                                                                     | Timestamp of when the consent was granted.                                                                                                                                                                                               | Yes (for time-based queries)                      |
| `expirationTimestamp` | TIMESTAMP WITH TIME ZONE                | NULLABLE                                                                                                                                | Timestamp when this consent automatically expires. If NULL, consent is valid until explicitly revoked or superseded.                                                                                                                   | Yes (for managing expired consents)               |
| `revocationTimestamp` | TIMESTAMP WITH TIME ZONE                | NULLABLE                                                                                                                                | Timestamp of when the consent was revoked by the user. If NULL, consent is active (or pending if not yet granted/expired).                                                                                                                 |                                                   |
| `revocationStatus`    | BOOLEAN                                 | NOT NULL, DEFAULT FALSE                                                                                                                 | True if the consent has been revoked, False otherwise. This allows for quick checks without relying solely on `revocationTimestamp`.                                                                                                   | Yes (for filtering active/revoked consents)       |
| `consentVersion`      | INTEGER                                 | NOT NULL, DEFAULT 1                                                                                                                     | Version number for this consent instance, allowing for updates to consent terms where a new version supersedes an old one (the old one would be marked as revoked/superseded).                                                         |                                                   |
| `recordProof`         | VARCHAR(512)                            | NULLABLE                                                                                                                                | If stored on a DLI, this could be the transaction hash or a pointer to the immutable record on the ledger. For database immutability, could be a chained hash.                                                                        | Yes (if used for external verification)           |

**`consentScope` Structure:**

The `consentScope` attribute is crucial for granularity. It should be an array of objects, where each object defines a specific permission.

*Example `consentScope` object:*
```json
{
  "resourceType": "data_category", // e.g., 'data_category', 'feature_access', 'api_endpoint'
  "resourceIdentifier": "user_uploaded_text", // e.g., 'email_content', 'voice_recordings', 'trait_extraction_module', 'social_media_posting_api'
  "actions": ["read_raw", "analyze_sentiment", "extract_linguistic_patterns"], // Array of permitted actions, e.g., 'read', 'write', 'analyze', 'share_with_app_X'
  "conditions": { // Optional conditions
    "purpose": "persona_trait_extraction_phase1",
    "retention": "30_days_for_raw_data_after_processing"
  }
}
```
An array of such objects would constitute the full `consentScope`. For example:
```json
[
  {
    "resourceType": "data_category",
    "resourceIdentifier": "user_uploaded_text_files",
    "actions": ["read_raw", "process_for_text_analysis"],
    "conditions": {
      "purpose": "To extract linguistic traits for your Echo persona as per EchoSphere Phase 1 analysis.",
      "data_retention_raw": "Delete after 7 days post-successful-analysis or upon user request."
    }
  },
  {
    "resourceType": "feature_access",
    "resourceIdentifier": "voice_cloning_module_preview",
    "actions": ["process_voice_sample"],
    "conditions": {
      "purpose": "To generate a preview of your cloned voice for your Echo persona."
    }
  }
]
```

**Immutability Considerations:**

*   **DLI/Blockchain:** If stored on a DLI, immutability is an inherent property of the ledger. Each `ConsentLedgerEntry` (or its hash) would be part of a transaction in a block, cryptographically linked to previous blocks.
*   **Immutable Database Table:** If a traditional database is used, immutability can be approximated by:
    *   Making the table append-only (no UPDATE or DELETE operations allowed directly).
    *   Using database triggers to prevent modifications and log any attempts.
    *   Implementing cryptographic chaining: each new entry includes a hash of the previous entry, creating a verifiable chain. The `recordProof` attribute could store this chain hash.
    *   Regularly hashing the entire table or batches of records and anchoring these hashes to a public blockchain (timestamping/notarization).

**Conceptual JSON Representation of `ConsentLedgerEntry`:**

```json
{
  "consentTokenID": "consent_uuid_placeholder_789",
  "userID": "user_uuid_placeholder_123",
  "dataHash": "sha256_hash_of_ResearchPaper_AI_Ethics.pdf.enc_content",
  "consentScope": [
    {
      "resourceType": "data_category",
      "resourceIdentifier": "application/pdf_user_uploads",
      "actions": ["read_raw", "decrypt_for_processing", "extract_text_content", "analyze_for_linguistic_traits"],
      "conditions": {
        "purpose": "To analyze the content of your uploaded PDF document ('ResearchPaper_AI_Ethics.pdf') for extracting linguistic patterns and topics to build your initial Echo persona profile.",
        "data_lifetime_post_processing": "Processed text snippets may be retained as part of your Persona Knowledge Graph. Raw decrypted PDF content will be expunged from temporary processing storage within 24 hours of successful analysis."
      }
    }
  ],
  "purposeDescription": "Allow EchoSphere to analyze the uploaded PDF document 'ResearchPaper_AI_Ethics.pdf' to understand your writing style and knowledge areas for persona creation.",
  "processingDetails": {
    "modules_involved": ["UDIM_DecryptionService", "MAIPP_TextAnalysisModule"],
    "primary_ai_models_conceptual": ["LLM_for_topic_extraction", "NLP_for_linguistic_features"]
  },
  "consentTimestamp": "2024-03-15T10:25:00Z",
  "expirationTimestamp": null, // Or "2025-03-15T10:25:00Z" for a 1-year consent
  "revocationTimestamp": null,
  "revocationStatus": false,
  "consentVersion": 1,
  "recordProof": "dli_transaction_hash_or_chained_hash_placeholder"
}
```

## 3. Related Data Structures

For the initial operation of UDIM, the primary external dependency is a `User` table.

*   **`User` Table (Assumed)**
    *   `userID` (UUID, Primary Key): Unique identifier for the user.
    *   Other attributes like `username`, `email_hashed`, `did_user` (Phase 4), `creationTimestamp`, etc.

No other new tables are immediately required *by UDIM itself* for its core data management in Phase 1, beyond these two defined structures and the assumed `User` table. Other modules will introduce their own specific tables (e.g., for the Persona Knowledge Graph).

## 4. Secure Storage Considerations

*   **Raw Data (`rawDataReference`):**
    *   The `rawDataReference` will typically be a URI pointing to an encrypted object in a secure, private cloud storage bucket (e.g., AWS S3, Google Cloud Storage).
    *   **Encryption Method:** Server-Side Encryption with Customer-Managed Encryption Keys (SSE-KMS using CMEK) is highly recommended. This means:
        *   The cloud provider encrypts the data as it's written.
        *   The encryption keys themselves are managed by EchoSphere (or the user in an advanced model) via a Key Management Service (e.g., AWS KMS, Google Cloud KMS). EchoSphere controls the policies for key usage.
        *   Each `UserDataPackage` (or potentially each user) can have its own `encryptionKeyID`, allowing for granular key rotation and access control.
    *   **Access Control:** Bucket policies and IAM roles must be strictly configured to ensure only authorized UDIM processes (and later, consented MAIPP processes) can access these encrypted objects, and only with the correct key.
    *   **Object Immutability (Optional):** S3 Object Lock or similar features can be used to make the encrypted raw data objects immutable for a defined period, preventing accidental deletion or modification before processing and archival/deletion policies take effect.

*   **Metadata Database (Storing `UserDataPackage` & `ConsentLedgerEntry`):**
    *   **Encryption at Rest:** The database instances (e.g., PostgreSQL, MongoDB) storing the metadata tables must themselves be encrypted at rest using provider-managed keys (e.g., AWS RDS encryption, Google Cloud SQL encryption) or customer-managed keys via KMS.
    *   **Encryption in Transit:** All connections to this database must use TLS/SSL.
    *   **Network Security:** Database instances should be placed in private subnets (VPCs) with strict firewall rules (security groups/NACLs) allowing access only from specific application servers/services.
    *   **Access Controls:** Robust authentication and authorization for database users. Application services should use unique credentials with the principle of least privilege (e.g., UDIM service only has write access to `UserDataPackage`, UCMS has write access to `ConsentLedgerEntry`).
    *   **Audit Logging:** Database audit logging should be enabled to track access and DML/DDL statements.
    *   **Backups:** Regular, encrypted backups of the metadata database are essential, stored securely with restricted access.
```
