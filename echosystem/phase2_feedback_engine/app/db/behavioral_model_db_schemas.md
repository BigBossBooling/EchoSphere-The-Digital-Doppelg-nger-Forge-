# Phase 2: Persona Behavioral Model - Conceptual DB Schemas

This document outlines conceptual database schemas for storing components of the Persona Behavioral Model.
The strategy involves using a flexible NoSQL database (like AWS DynamoDB or MongoDB) for parameters and rules,
and AWS S3 for storing large model artifact files (e.g., fine-tuned LLM weights).

## 1. Persona Behavioral Model Store (DynamoDB/MongoDB)

**Objective:** To store versioned sets of behavioral rules, style parameters, and references to model artifacts for each persona.
This store needs to be easily queryable by `persona_id` to retrieve the active model or specific versions.

**A. Using AWS DynamoDB (Example)**

*   **Table Name:** `EchoSphere_PersonaBehavioralModels`
    *   **Purpose:** Stores the main `PersonaBehavioralModel` document.
*   **Primary Key:**
    *   `persona_id` (Partition Key, String - from UUID)
    *   `model_version_id` (Sort Key, String - from UUID, or a timestamp-based version string like `v_YYYYMMDDHHMMSS_uuid_short`)
*   **Attributes (mirroring `PersonaBehavioralModel` Pydantic model):**
    *   `primary_llm_reference` (Map): Stores `ModelFileReference` object (see Pydantic model).
        *   `storage_type`: (String)
        *   `path_uri`: (String)
        *   `version_id`: (String, Optional)
        *   `checksum_sha256`: (String, Optional)
        *   `metadata`: (Map, Optional)
    *   `behavioral_rules` (List of Maps): Stores `List[BehavioralRule]`. Each map in the list would contain:
        *   `rule_id`: (String - UUID)
        *   `description`: (String)
        *   `condition_script`: (String)
        *   `action_to_take`: (String)
        *   `priority`: (Number)
        *   `is_active`: (Boolean)
        *   `created_at`: (String - ISO8601 Timestamp)
        *   `updated_at`: (String - ISO8601 Timestamp)
    *   `style_parameters` (List of Maps): Stores `List[StyleParameter]`. Each map contains:
        *   `parameter_name`: (String)
        *   `value`: (DynamoDB flexible type: String, Number, Boolean, Map, List)
        *   `source_of_truth`: (String, Optional)
        *   `updated_at`: (String - ISO8601 Timestamp)
    *   `created_at` (String - ISO8601 Timestamp)
    *   `last_updated_at` (String - ISO8601 Timestamp)
    *   `is_active_model` (Boolean - Represented as Number 0 or 1 for GSI, or String "true"/"false")
*   **Global Secondary Index (GSI) for Active Model Lookup:**
    *   `PersonaActiveModelIndex`:
        *   Partition Key: `persona_id` (String)
        *   Sort Key: `is_active_model_marker` (String or Number).
            *   To use this effectively for a sparse index to find only the active model:
                1.  Create an attribute `active_model_lookup_key` which is ONLY populated if `is_active_model` is true (e.g., value could be "ACTIVE").
                2.  Index on `persona_id` (Partition Key) and `active_model_lookup_key` (Sort Key).
            *   Alternatively, if `is_active_model` is stored as a number (1 for true, 0 for false), you can query where `is_active_model = 1`.
            *   A simpler GSI if only one active model per persona: Index on `is_active_model` (as PK) and `persona_id` (as SK) but this is less common for "active" flags.
            *   **Recommended GSI:** `persona_id` (PK), `is_active_model` (SK - using 0/1 or "false"/"true" string). Query where `persona_id = :pid AND is_active_model = 1` (or "true"). This requires `is_active_model` to be present on all items.

**B. Using MongoDB (Example)**

*   **Collection Name:** `persona_behavioral_models`
*   **Document Structure (aligns with `PersonaBehavioralModel` Pydantic model):**
    ```json
    {
      "_id": "<model_version_id_uuid>", // Can use the UUID directly
      "persona_id": "<persona_id_uuid>",
      "primary_llm_reference": { /* ModelFileReference object */ },
      "behavioral_rules": [ /* List of BehavioralRule objects, with UUIDs as strings */ ],
      "style_parameters": [ /* List of StyleParameter objects */ ],
      "created_at": "ISODate(...)", // MongoDB ISODate type
      "last_updated_at": "ISODate(...)",
      "is_active_model": false // Boolean
    }
    ```
*   **Indexes:**
    *   `{ "persona_id": 1 }` (Basic lookup by persona)
    *   `{ "persona_id": 1, "is_active_model": 1 }` (To quickly find the active model for a persona; ensure this is a sparse index if not all items have `is_active_model: true`)
    *   `{ "persona_id": 1, "last_updated_at": -1 }` (To find the latest model version for a persona if `model_version_id` is not timestamp-based)
    *   `{ "persona_id": 1, "model_version_id": 1 }` (If `_id` is not `model_version_id`, this ensures uniqueness and lookup)

## 2. Large Model Artifact Storage (AWS S3)

**Objective:** To store large binary files like fine-tuned LLM weights, embeddings, voice model files, etc.

*   **Bucket Name:** `echosphere-persona-models-<account-id>-<region>` (example, ensure globally unique)
*   **Object Key Structure:** A consistent naming convention is crucial.
    *   `personas/<persona_id>/<model_type>/<model_version_id_from_db>/<artifact_filename_with_extension>`
    *   **Examples:**
        *   LLM fine-tune: `personas/uuid-of-persona/llm_finetune/uuid-of-model-version/model_weights.tar.gz`
        *   Embeddings: `personas/uuid-of-persona/embeddings/uuid-of-model-version/user_knowledge_embeddings.pkl`
        *   Voice model: `personas/uuid-of-persona/voice/uuid-of-model-version/voice_clone.pth`
    *   The `<model_version_id_from_db>` here refers to the `model_version_id` from the DynamoDB/MongoDB record, linking the metadata record to its S3 artifacts.
*   **Security:**
    *   Bucket policy: Private by default.
    *   Encryption: Server-Side Encryption (SSE-S3 or SSE-KMS with CMK).
    *   IAM Roles:
        *   Fine-tuning/training pipelines: Role with write access to specific paths (`personas/<persona_id>/...`).
        *   Inference engine (e.g., Persona Runtime Environment): Role with read access to specific paths.
*   **Versioning:** S3 Object Versioning should be enabled on the bucket to keep history of model artifacts. The `version_id` in `ModelFileReference` can refer to a specific S3 object version.
*   **Metadata:** Custom S3 object metadata can store additional information like `checksum_sha256` (though S3 provides Content-MD5), `base_model_used`, `training_date`, etc., complementing the `ModelFileReference.metadata`.
*   **Lifecycle Policies:** Implement lifecycle policies for managing older model artifacts (e.g., transition to cheaper storage like S3 Glacier, or delete after a certain period if not actively used or linked).

**Considerations:**

*   **Atomicity:** Updating the model (e.g., rules in DynamoDB/MongoDB and artifacts in S3) might involve multiple steps. Consider patterns for ensuring consistency (e.g., two-phase commit if possible, or eventual consistency with clear state management). For activating a new model, first ensure all artifacts are uploaded and verified, then update the `is_active_model` flag in the database.
*   **Scalability:** Both DynamoDB/MongoDB and S3 are highly scalable. Design partition keys (DynamoDB) and document structures (MongoDB) to avoid hotspots.
*   **Cost:** Consider storage costs for S3 and provisioned throughput/request costs for DynamoDB/MongoDB. Optimize data structures and access patterns.
```
