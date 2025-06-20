# Phase 1: User Data Ingestion Module (UDIM) - Finalized Technology Stack

This document outlines the proposed technology stack for the User Data Ingestion Module (UDIM) in EchoSphere's Phase 1. Choices are based on UDIM's requirements for security, scalability, performance, data integrity, and integration capabilities.

## 1. Backend Language & Framework

*   **Choice:** **Python with FastAPI**
*   **Justification:**
    *   **Performance & Async Capabilities:** FastAPI is built on Starlette and Pydantic, offering high performance comparable to Node.js and Go, particularly for I/O-bound operations like handling API requests, file uploads, and interacting with databases/KMS/object storage. Its native support for `async/await` is crucial for efficiently managing concurrent connections and external service calls without blocking.
    *   **Developer Productivity & Ecosystem:** Python has a vast ecosystem of libraries, especially for AI/ML tasks (relevant for downstream MAIPP integration, though not directly in UDIM), cloud SDKs, and general web development. FastAPI's use of Python type hints for data validation (via Pydantic) and automatic OpenAPI documentation generation significantly speeds up development and improves code quality.
    *   **Security:** FastAPI has good security practices, and Python offers mature libraries for authentication, cryptography, etc. The framework's explicitness helps in writing secure code.
    *   **Scalability:** FastAPI applications can be easily containerized and scaled horizontally using ASGI servers like Uvicorn with multiple workers, or managed by Kubernetes.
    *   **Team Familiarity (Assumed):** Python is a widely known language, potentially easing team onboarding and developer availability.
*   **Key Libraries/Tools:**
    *   **FastAPI:** The core web framework.
    *   **Uvicorn:** ASGI server for running FastAPI applications.
    *   **Pydantic:** For data validation, serialization, and settings management (leveraged by FastAPI for request/response models).
    *   **SQLAlchemy (Async Mode with Alembic):** For ORM capabilities if complex queries or relational integrity beyond basic metadata storage is needed. Alembic for database migrations. (Alternatively, a simpler async database driver like `asyncpg` for PostgreSQL if ORM is overkill for UDIM's direct needs).
    *   **`python-jose` or `PyJWT`:** For JWT validation (if user authentication tokens are JWTs and introspection is not used).
    *   **`boto3` (for AWS), `google-cloud-storage`/`google-cloud-kms` (for GCP), `azure-storage-blob`/`azure-keyvault` (for Azure):** Cloud provider SDKs for interacting with object storage and KMS.
    *   **`httpx`:** For making asynchronous HTTP requests to internal services (e.g., Consent Verification, MAIPP Notification).

## 2. Database for `UserDataPackage` Metadata & General UDIM Data

*   **Choice:** **PostgreSQL (Managed Cloud Service, e.g., AWS RDS for PostgreSQL, Google Cloud SQL for PostgreSQL, Azure Database for PostgreSQL)**
*   **Justification:**
    *   **Relational Integrity & ACID Compliance:** UDIM metadata (`UserDataPackage`) has clear relationships with `User` and `ConsentLedgerEntry` tables. PostgreSQL's strong support for foreign keys, transactions, and ACID properties ensures data consistency.
    *   **JSONB Support:** Excellent for the `metadata` field in `UserDataPackage`, allowing flexible, schemaless data storage with powerful indexing (GIN) and querying capabilities for nested elements.
    *   **Scalability & Reliability:** Managed PostgreSQL services offer high availability, automated backups, point-in-time recovery, read replicas, and vertical/horizontal scaling options.
    *   **Querying Capabilities:** Rich SQL dialect with advanced features, suitable for any analytical queries UDIM might need on its metadata.
    *   **Maturity & Ecosystem:** A very mature, open-source database with a strong community and wide tool support. Python has excellent drivers (`psycopg2` for synchronous, `asyncpg` for asynchronous).
*   **Key Considerations:**
    *   **Connection Pooling:** Use a robust connection pooler (e.g., PgBouncer if self-managed, or built-in pooling with cloud services) to manage connections efficiently from the async FastAPI application.
    *   **Backup Strategy:** Leverage automated backup and point-in-time recovery features of the managed cloud service. Regular testing of restore procedures.
    *   **Security:** Network isolation (VPC), encryption at rest and in transit, strict IAM roles/database user permissions.

## 3. Database/Ledger for `ConsentLedgerEntry`

*   **Choice:** **Amazon QLDB (Quantum Ledger Database)**
*   **Justification:**
    *   **Immutability & Verifiability:** QLDB is specifically designed as a fully managed ledger database that provides a transparent, immutable, and cryptographically verifiable transaction log. This is ideal for `ConsentLedgerEntry` records, where auditability and proof of consent state over time are critical. Every change is journaled.
    *   **Auditability:** Provides a verifiable history of all changes to consent data, which is essential for compliance and user trust.
    *   **Document-Oriented Data Model:** QLDB's document model (Amazon Ion, a superset of JSON) maps well to the structure of `ConsentLedgerEntry`, including its potentially complex `consentScope` (JSONB-like).
    *   **Scalability & Serverless:** QLDB is serverless and scales automatically, reducing operational overhead.
    *   **Integration with AWS Ecosystem:** If other parts of EchoSphere leverage AWS, QLDB integrates well with services like IAM, Lambda, etc.
*   **Alternatives & Considerations:**
    *   **Hyperledger Fabric:** A more heavyweight permissioned DLI option. Offers greater decentralization among participating organizations if EchoSphere's governance model required it for consent, but adds significant operational complexity for Phase 1 UDIM's direct needs.
    *   **PostgreSQL with Strict Controls:** Could be used with append-only tables, triggers to prevent updates/deletes, and application-level cryptographic chaining for `recordProof`. Less inherently immutable than QLDB but might be simpler if already using PostgreSQL extensively and DLI features are not immediately paramount.
    *   **Key Considerations:**
        *   **Data Model Mapping:** Ensure the `ConsentLedgerEntry` structure (especially `consentScope` JSON) is efficiently modeled and queryable in QLDB's PartiQL.
        *   **Transaction Throughput:** Evaluate QLDB's limits if consent events are extremely high volume (though typically manageable for consent changes).
        *   **Verification Process:** Define how external parties or users can independently verify consent records from QLDB's journal exports if needed.

## 4. Object Storage for Encrypted Raw Data

*   **Choice:** **AWS S3 (Simple Storage Service)**
*   **Justification:**
    *   **Scalability & Durability:** Virtually unlimited scalability for storing vast amounts of user data (encrypted files). Designed for 11 nines of durability.
    *   **Security Features:**
        *   **Server-Side Encryption (SSE-KMS or SSE-S3):** SSE-KMS is preferred, allowing use of Customer Managed Keys (CMKs) via AWS KMS for fine-grained control over encryption, as detailed for `encryptionKeyID`.
        *   **Bucket Policies & IAM:** Granular access control to ensure only authorized UDIM processes can write and specific, consented downstream services can read.
        *   **Object Lock:** Can be used for immutability for specific retention periods if needed for compliance or data integrity for raw data before processing.
        *   **Access Logging:** Detailed server access logs for auditing object access.
    *   **Lifecycle Management:** Policies for automatically transitioning data to cheaper storage tiers (e.g., S3 Glacier) or deleting it after defined retention periods (supporting data minimization).
    *   **Integration & SDKs:** Excellent integration with AWS SDKs (like `boto3` for Python), making it easy to manage uploads, downloads, and security settings from the FastAPI backend.
    *   **Performance:** High throughput for uploads and downloads. Supports multipart uploads for large files.
*   **Alternatives:** Google Cloud Storage (GCS), Azure Blob Storage. All offer very similar core capabilities. The choice might be influenced by the primary cloud provider for the rest of EchoSphere.
*   **Key Features to Use:**
    *   Server-Side Encryption with KMS-Managed Keys (SSE-KMS).
    *   Bucket versioning (to recover from accidental deletions/overwrites before processing).
    *   Strict IAM roles and bucket policies.
    *   S3 Transfer Acceleration (optional, for geographically dispersed users).
    *   Multipart Upload for large files.

## 5. Key Management Service (KMS)

*   **Choice:** **AWS Key Management Service (KMS)**
*   **Justification:**
    *   **Secure Key Management:** Provides a secure and resilient service for creating, managing, and controlling cryptographic keys. Keys can be backed by FIPS 140-2 validated HSMs.
    *   **Integration with S3:** Native integration with S3 for SSE-KMS, simplifying envelope encryption for object storage. UDIM would primarily interact with KMS to ensure S3 objects are encrypted with specific CMKs.
    *   **IAM Integration:** Fine-grained access control over who (users, roles, services) can use which keys and for what operations (encrypt, decrypt). This is crucial for enforcing that only UDIM can trigger encryption of new `UserDataPackage` files and only authorized, consented services can trigger decryption.
    *   **Auditability:** AWS CloudTrail logs all KMS API calls, providing an audit trail of key usage.
    *   **Envelope Encryption Support:** While S3 SSE-KMS handles this transparently for S3 objects, if UDIM needed to encrypt other data (e.g., certain database fields directly, though less likely for Phase 1), KMS provides primitives for envelope encryption (generate data key, encrypt data key with CMK).
*   **Alternatives:** Google Cloud KMS, Azure Key Vault, HashiCorp Vault (if a multi-cloud or self-hosted solution is preferred, adds operational overhead).
*   **Usage Pattern:**
    *   UDIM will ensure that when objects are written to S3, they are encrypted using SSE-KMS with a specific Customer Master Key (CMK) designated for EchoSphere user data, or even per-user/per-package keys if granularity demands (though this adds complexity to key policy management).
    *   The `encryptionKeyID` in `UserDataPackage` will store the ARN of the KMS CMK used.
    *   Downstream services (like MAIPP) needing to read the data will be granted `kms:Decrypt` permission on specific keys/contexts, only after consent verification.

## 6. Messaging Queue (for MAIPP Notification)

*   **Choice:** **AWS Simple Queue Service (SQS)**
*   **Justification:**
    *   **Decoupling & Reliability:** Effectively decouples UDIM from MAIPP. If MAIPP is temporarily unavailable, messages (notifications) persist in the queue and can be processed when MAIPP recovers. This improves overall system resilience.
    *   **Scalability:** SQS scales automatically to handle high volumes of messages.
    *   **Durability:** Standard queues offer at-least-once delivery. FIFO queues can ensure ordering if strictly necessary (though potentially not for MAIPP notifications if processing can be idempotent and out-of-order).
    *   **Dead-Letter Queues (DLQs):** Easy to configure DLQs to capture messages that consistently fail processing by MAIPP, allowing for later investigation without losing the notification.
    *   **Cost-Effective:** Pay-per-use model, generally very cost-effective for typical message volumes.
    *   **Integration with AWS Ecosystem:** Seamless integration with other AWS services (Lambda for consumers, IAM for access control, Python SDK `boto3`).
*   **Alternatives:** RabbitMQ (more features, but requires self-management or a managed service), Apache Kafka (powerful for streaming, but might be overkill for simple notifications unless MAIPP has streaming needs), Google Pub/Sub, Azure Queue Storage.
*   **Key Features:**
    *   Standard Queues (for high throughput, at-least-once delivery).
    *   Message visibility timeout (to handle processing failures and retries by MAIPP).
    *   Dead-Letter Queues (DLQs).
    *   Message attributes (for sending metadata along with the `packageID`).

## 7. Security Libraries & Tools

*   **OAuth 2.0 / JWT Libraries:**
    *   **Python `Authlib` or `python-jose` with `cryptography`:** For validating OAuth 2.0 Bearer Tokens (JWTs) if introspection is not used. `Authlib` provides broader OAuth client/provider capabilities. `python-jose` is more focused on JWTs.
*   **Encryption Libraries:**
    *   Primarily relying on AWS SDK (`boto3`) for KMS interactions which abstracts direct cryptographic operations for S3 SSE.
    *   If any application-layer symmetric encryption were needed (e.g., for specific fields before DB storage, though not primary for UDIM Phase 1), `cryptography` library in Python.
*   **Input Validation Libraries:**
    *   **Pydantic:** Used natively by FastAPI for request body validation against defined schemas, including type checking, format validation, and custom validators.
*   **Malware Scanning Tool (Conceptual):**
    *   **ClamAV:** Open-source antivirus engine. Can be run as a separate service container that UDIM calls via an internal API to scan uploaded files (e.g., by passing the file path in a shared temporary volume or streaming the file).
    *   **Cloud Provider Security Services:** Some cloud providers offer malware scanning for objects uploaded to storage (e.g., integrations with their security hubs or specific scanning services). This would be configured at the S3 bucket level or via event-driven functions.

## 8. Containerization & Orchestration (Deployment Environment - Conceptual)

*   **Choice:** **Docker & Kubernetes (e.g., AWS EKS, Google GKE, Azure AKS)**
*   **Justification:**
    *   **Docker:** For packaging UDIM (FastAPI application and its dependencies) into standardized, portable containers. Ensures consistency across development, testing, and production environments.
    *   **Kubernetes:** For orchestrating containerized UDIM services. Provides:
        *   **Scalability:** Horizontal auto-scaling of UDIM API server pods based on load.
        *   **High Availability:** Manages service uptime, restarts failed containers.
        *   **Service Discovery & Load Balancing:** For internal communication (e.g., to Consent Service) and external exposure of APIs.
        *   **Configuration Management & Secrets:** Securely manages application configuration and sensitive data like database credentials or API keys for internal services.
*   **Note:** While this is a higher-level infrastructure choice, designing UDIM as stateless microservices aligns well with a Kubernetes deployment model, facilitating scalability and resilience.
```
