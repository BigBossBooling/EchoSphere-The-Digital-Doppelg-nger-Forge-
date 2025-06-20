# MAIPP: Conceptual IaC & Basic Schema for Persona Knowledge Graph (PKG)

This document outlines the conceptual Infrastructure as Code (IaC) definitions for provisioning a Graph Database (Neo4j is assumed for primary examples due to Cypher syntax clarity) and a basic schema for the Persona Knowledge Graph (PKG) as utilized by MAIPP in EchoSphere Phase 1.

## 1. Graph Database Provisioning (Conceptual IaC)

**Objective:** To provision a managed graph database instance suitable for storing and querying the PKG. Neo4j AuraDB (managed cloud service) or Amazon Neptune are primary considerations based on previous technology stack discussions.

**Key Considerations for Provisioning:**
*   **Instance Size:** Start with an instance size appropriate for development and initial Phase 1 load (e.g., smallest available professional/production tier for managed services to ensure feature completeness, or a developer-tier instance).
*   **Memory & CPU:** Chosen based on expected graph size (initially small, growing with users/data) and query complexity (Phase 1 queries will be for population and basic retrieval).
*   **Storage:** Sufficient for graph data, indexes, and transaction logs. Auto-scaling for storage is a desirable feature of managed services.
*   **Backups:** Automated daily backups with point-in-time recovery capabilities are essential.
*   **Networking:** Secure network configuration, ideally placing the database in a private network (e.g., VPC) with controlled access from MAIPP and PTFI services (e.g., via VPC peering, private link, or security groups). Public endpoints should be avoided or heavily secured.
*   **Authentication:** Strong credentials for database access, managed via a secrets manager. IAM authentication if supported by the managed service (e.g., Neptune).

**Illustrative IaC (Terraform Example Comments for Neo4j AuraDB - simplified):**
(Actual AuraDB provisioning might be more nuanced and often involves their specific provider or API interactions if not using a generic cloud resource manager.)

```terraform
# resource "neo4j_auradb_instance" "pkg_instance" {
#   # Provider configuration for Neo4j AuraDB (or equivalent cloud provider resource for managed Neo4j)
#   # would be needed here. This is highly dependent on the specific Terraform provider for AuraDB.
#   name           = "echosphere-pkg-${var.environment}"
#   region         = var.neo4j_region # e.g., "europe-west1", "us-east-1"
#   instance_type  = "aura-professional-small" # Example: Smallest professional tier
#   memory         = "4GB" # Example memory allocation
#   # version        = "5.x" # Specify Neo4j version
#   # cloud_provider = "GCP" or "AWS" or "AZURE" # Depending on AuraDB options
#
#   # Credentials should be managed securely, potentially set initially and then rotated.
#   # For IaC, you might pass references to secrets stored in a secrets manager.
#   # initial_username = var.neo4j_initial_username
#   # initial_password_secret_arn = var.neo4j_initial_password_secret_arn
#
#   tags = {
#     Name        = "EchoSphere PKG"
#     Environment = var.environment
#     Project     = "EchoSphere"
#   }
# }

# output "neo4j_auradb_instance_connection_uri" {
#   description = "Connection URI for the Neo4j AuraDB PKG instance."
#   value       = neo4j_auradb_instance.pkg_instance.connection_uri # Actual attribute name may vary
# }
# output "neo4j_auradb_instance_username" {
#   description = "Initial username for the Neo4j AuraDB PKG instance."
#   value       = neo4j_auradb_instance.pkg_instance.username # Actual attribute name may vary
# }
```

**Illustrative IaC (Terraform Example Comments for Amazon Neptune):**

```terraform
# resource "aws_neptune_cluster" "pkg_neptune_cluster" {
#   cluster_identifier_prefix = "echosphere-pkg-${var.environment}"
#   engine                    = "neptune"
#   engine_version            = "1.3.0.0" # Example: Specify a recent, stable Neptune engine version
#   instance_class            = "db.t3.medium"  # Example: Smaller instance class for dev/Phase 1
#   # For production, consider "db.r5.large" or larger.
#   skip_final_snapshot       = true # For dev/test; set to false for production
#   iam_database_authentication_enabled = true # Recommended for secure access
#   storage_encrypted         = true
#   kms_key_arn               = var.neptune_kms_key_arn # Use a dedicated KMS key for Neptune encryption
#
#   # Networking (examples, replace with actual VPC Subnet and Security Group IDs)
#   neptune_subnet_group_name = aws_neptune_subnet_group.pkg_neptune_subnet_group.name
#   vpc_security_group_ids    = [aws_security_group.pkg_neptune_sg.id]
#
#   backup_retention_period   = 7 # Days, adjust as needed
#   preferred_backup_window   = "03:00-04:00" # UTC
#
#   tags = {
#     Name        = "EchoSphere PKG Cluster"
#     Environment = var.environment
#     Project     = "EchoSphere"
#   }
# }

# resource "aws_neptune_cluster_instance" "pkg_neptune_instance" {
#   count              = 1 # Start with one instance for Phase 1 dev/test
#   cluster_identifier = aws_neptune_cluster.pkg_neptune_cluster.id
#   engine             = "neptune"
#   instance_class     = "db.t3.medium" # Match cluster or use compatible instance class
#
#   tags = {
#     Name        = "EchoSphere PKG Instance"
#     Environment = var.environment
#     Project     = "EchoSphere"
#   }
# }

# resource "aws_neptune_subnet_group" "pkg_neptune_subnet_group" {
#   name       = "echosphere-pkg-sng-${var.environment}"
#   subnet_ids = var.private_subnet_ids # List of private subnet IDs
#   tags = { Name = "EchoSphere PKG Subnet Group" }
# }

# resource "aws_security_group" "pkg_neptune_sg" {
#   name        = "echosphere-pkg-sg-${var.environment}"
#   description = "Security group for EchoSphere PKG Neptune cluster"
#   vpc_id      = var.vpc_id
#   # Ingress rules to allow MAIPP/PTFI services (e.g., from their security groups or IP ranges)
#   # Egress rules (typically allow all outbound within VPC)
# }

# output "neptune_cluster_endpoint" {
#   description = "The endpoint of the Neptune DB cluster for writers."
#   value       = aws_neptune_cluster.pkg_neptune_cluster.endpoint
# }
# output "neptune_cluster_reader_endpoint" {
#   description = "The reader endpoint of the Neptune DB cluster."
#   value       = aws_neptune_cluster.pkg_neptune_cluster.reader_endpoint
# }
```

## 2. Basic PKG Schema (Nodes & Relationships for MAIPP Phase 1)

This initial schema focuses on the entities MAIPP will create or link to during Phase 1. It's based on the PKG structure defined in `phase1_maipp_data_models.md`. Constraints and indexes are crucial for data integrity and query performance.

**Node Labels & Key Properties (Neo4j Cypher Syntax for Constraints/Indexes):**

*   **`User`**
    *   Properties: `userID`: STRING (Primary Key, Unique, Indexed), `did_user`: STRING (Indexed, Optional, for Phase 4), `createdAt`: DATETIME (NOT NULL, default to transaction timestamp).
    *   `CREATE CONSTRAINT User_userID_unique IF NOT EXISTS FOR (u:User) REQUIRE u.userID IS UNIQUE;`
    *   `CREATE INDEX User_userID_index IF NOT EXISTS FOR (u:User) ON (u.userID);`
    *   `CREATE INDEX User_did_user_index IF NOT EXISTS FOR (u:User) ON (u.did_user);`

*   **`Trait`** (Represents traits, initially as candidates from MAIPP, later refined by PTFI)
    *   Properties: `traitID`: STRING (Primary Key, Unique, Indexed - typically maps to `ExtractedTraitCandidate.candidateID`), `name`: STRING (Indexed), `description`: STRING, `category`: STRING (Indexed), `status_in_pkg`: STRING (Indexed - e.g., 'candidate_from_maipp', 'active_user_confirmed', 'active_user_modified', 'rejected_by_user', 'user_added'), `maipp_confidence`: FLOAT (Optional), `user_confidence`: FLOAT (Optional, from PTFI), `origin`: STRING (e.g., 'ai_gemini_topics', 'ai_hf_sentiment', 'user_defined'), `originModels`: LIST<STRING> (Optional), `associatedFeatureSetIDs`: LIST<STRING> (Optional, stringified UUIDs), `creationTimestamp`: DATETIME, `lastUpdatedTimestamp`: DATETIME.
    *   `CREATE CONSTRAINT Trait_traitID_unique IF NOT EXISTS FOR (t:Trait) REQUIRE t.traitID IS UNIQUE;`
    *   `CREATE INDEX Trait_traitID_index IF NOT EXISTS FOR (t:Trait) ON (t.traitID);`
    *   `CREATE INDEX Trait_name_index IF NOT EXISTS FOR (t:Trait) ON (t.name);`
    *   `CREATE INDEX Trait_category_status_index IF NOT EXISTS FOR (t:Trait) ON (t.category, t.status_in_pkg);`

*   **`Concept`** (Key topics, entities, ideas the user engages with)
    *   Properties: `conceptID`: STRING (Primary Key, Unique, Indexed - can be a hash of normalized name), `name`: STRING (Unique, Indexed - normalized form, e.g., lowercase, lemmatized), `description`: STRING (Optional), `ontologyLink`: STRING (Optional, URI).
    *   `CREATE CONSTRAINT Concept_conceptID_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.conceptID IS UNIQUE;`
    *   `CREATE CONSTRAINT Concept_name_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE;`
    *   `CREATE INDEX Concept_name_text_index IF NOT EXISTS FOR (c:Concept) ON (c.name) OPTIONS {indexProvider: 'text'};` (If full-text search on concept names is needed)

*   **`Emotion`** (Standard emotions that might be linked to traits or user expressions)
    *   Properties: `emotionID`: STRING (Primary Key, Unique, Indexed - e.g., "ekman_joy", "plutchik_trust"), `name`: STRING (e.g., "Joy", "Trust"), `model_source`: STRING (e.g., "EkmanBasic", "PlutchikWheel").
    *   `CREATE CONSTRAINT Emotion_emotionID_unique IF NOT EXISTS FOR (e:Emotion) REQUIRE e.emotionID IS UNIQUE;`
    *   `CREATE INDEX Emotion_name_index IF NOT EXISTS FOR (e:Emotion) ON (e.name);`

*   **`SourceDataReferenceNode`** (Represents evidence snippets or sources)
    *   Properties: `referenceID`: STRING (Primary Key, Unique, Indexed - can be hash of sourcePackageID + snippet/offset), `sourceUserDataPackageID`: STRING (Indexed, NOT NULL), `snippet`: STRING (Optional - the actual text snippet, if short), `mediaOffset`: MAP (Optional - e.g., `{"type": "audio", "startTimeSec": 10.5, "endTimeSec": 15.2}`), `sourceDescription`: STRING (Optional - e.g., original filename, model that generated this reference).
    *   `CREATE CONSTRAINT SourceDataReferenceNode_referenceID_unique IF NOT EXISTS FOR (sdr:SourceDataReferenceNode) REQUIRE sdr.referenceID IS UNIQUE;`
    *   `CREATE INDEX SourceDataReferenceNode_sourceUserDataPackageID_index IF NOT EXISTS FOR (sdr:SourceDataReferenceNode) ON (sdr.sourceUserDataPackageID);`

**Relationship Types & Key Properties (MAIPP Phase 1 Focus):**

*   `(User)-[r:HAS_TRAIT]->(Trait)`
    *   Properties on `r`: `confidenceScore`: FLOAT (This would be the *user's* confidence after PTFI, or MAIPP's if still a candidate), `status`: STRING (e.g., 'candidate', 'confirmed', 'rejected' - reflects the state of this user-trait link), `lastModifiedBy`: STRING ('MAIPP' or 'USER'), `lastObservedTimestamp`: DATETIME, `evidenceLinks`: LIST<STRING> (Optional, list of `referenceID`s from `SourceDataReferenceNode` if not using direct relationships).
*   `(User)-[r:MENTIONED_CONCEPT]->(Concept)`
    *   Properties on `r`: `frequency`: INTEGER (How often mentioned in a given context/package), `sentiment_avg`: FLOAT (Optional, average sentiment when mentioning), `firstSeen`: DATETIME, `lastSeen`: DATETIME, `sourcePackageIDs`: LIST<STRING>.
*   `(Trait)-[r:EVIDENCED_BY]->(SourceDataReferenceNode)`
    *   Properties on `r`: `relevanceScore`: FLOAT (Optional, MAIPP's assessment), `modelAttribution`: STRING (MAIPP model that made the link), `timestamp`: DATETIME.
*   `(Trait)-[r:ASSOCIATED_WITH_CONCEPT]->(Concept)`
    *   Properties on `r`: `strength`: FLOAT (How strongly trait relates to concept), `context_description`: STRING (Optional, e.g., "Trait often expressed when discussing this concept").

**Schema Application:**
*   These constraints and indexes are typically applied to the graph database after it's provisioned. This is done via Cypher (for Neo4j) or Gremlin commands (for Neptune, though Neptune's schema is more implicit, property graph indexes are defined differently).
*   For Neo4j, these commands can be run through the Neo4j Browser, Cypher Shell, or a client driver.
*   For Neptune, indexing is usually managed at the property level via service configurations or specific Gremlin/SPARQL commands if applicable.

## 3. Summary

This document provides a conceptual starting point for provisioning the PKG graph database and defining its initial schema relevant to MAIPP's outputs in Phase 1. The actual IaC scripts will require careful implementation by the DevOps/Cloud Engineering team, tailored to the chosen graph database service (AuraDB, Neptune, or self-hosted). The schema, particularly node properties and relationships, will be refined and expanded in subsequent phases as EchoSphere's capabilities grow. Applying constraints and indexes early is vital for data integrity and query performance.
```
