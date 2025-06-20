# UDIM: Conceptual IaC for S3 Bucket & KMS Key Provisioning

This document outlines the conceptual Infrastructure as Code (IaC) definitions, primarily using AWS CloudFormation or Terraform syntax as illustrative examples, for provisioning the S3 bucket and KMS key required by the User Data Ingestion Module (UDIM).

## 1. AWS S3 Bucket for Raw User Data

**Objective:** To create a secure, private S3 bucket for storing encrypted raw user data uploaded via UDIM.

**Key Considerations:**
*   **Bucket Naming:** Should be globally unique. Suggestion: `echosphere-udim-user-data-<aws-account-id>-<region>`.
*   **Versioning:** Enable versioning to protect against accidental deletions or overwrites.
*   **Server-Side Encryption:** Enforce SSE-KMS by default, using a dedicated Customer Managed Key (CMK).
*   **Access Control:** Block all public access. Access should be granted only to specific IAM roles (UDIM service role for write, MAIPP service role for read/decrypt, Admin role for management).
*   **Lifecycle Policies:** Define policies for data archival (e.g., to S3 Glacier) or deletion after a certain retention period (configurable, user-driven where possible in later phases). For Phase 1, a basic retention or manual cleanup might suffice.
*   **Logging:** Enable server access logging and S3 object-level logging (via CloudTrail) for auditability.

**Illustrative IaC (Terraform Example Comments):**

```terraform
# resource "aws_s3_bucket" "udim_user_data_bucket" {
#   bucket = "echosphere-udim-user-data-${var.aws_account_id}-${var.aws_region}" # Ensure global uniqueness
#   acl    = "private" # Canned ACL, but bucket policies are preferred for fine-grained control
#
#   versioning {
#     enabled = true
#   }
#
#   server_side_encryption_configuration {
#     rule {
#       apply_server_side_encryption_by_default {
#         sse_algorithm     = "aws:kms"
#         kms_master_key_id = aws_kms_key.udim_data_encryption_key.arn
#       }
#       bucket_key_enabled = true # Recommended for cost and performance benefits with SSE-KMS
#     }
#   }
#
#   # Block all public access using S3 Block Public Access settings
#   # These are often configured on the bucket resource directly or via a separate aws_s3_bucket_public_access_block resource
#   # For example, within the aws_s3_bucket resource:
#   # block_public_acls   = true
#   # block_public_policy = true
#   # ignore_public_acls  = true
#   # restrict_public_buckets = true
#
#   logging {
#     target_bucket = aws_s3_bucket.s3_access_logs.id # A separate bucket for S3 server access logs
#     target_prefix = "logs/udim-user-data/"
#   }
#
#   tags = {
#     Name        = "EchoSphere UDIM User Data"
#     Environment = var.environment
#     Project     = "EchoSphere"
#   }
# }

# resource "aws_s3_bucket_public_access_block" "udim_user_data_bucket_pab" {
#   bucket = aws_s3_bucket.udim_user_data_bucket.id
#
#   block_public_acls       = true
#   block_public_policy     = true
#   ignore_public_acls      = true
#   restrict_public_buckets = true
# }

# resource "aws_s3_bucket_policy" "udim_user_data_bucket_policy" {
#   bucket = aws_s3_bucket.udim_user_data_bucket.id
#   policy = jsonencode({
#     Version = "2012-10-17",
#     Statement = [
#       {
#         Sid    = "DenyIncorrectEncryptionHeader",
#         Effect = "Deny",
#         Principal = "*",
#         Action = "s3:PutObject",
#         Resource = "${aws_s3_bucket.udim_user_data_bucket.arn}/*",
#         Condition = {
#           StringNotEqualsIfExists = { # Use StringNotEqualsIfExists if header might not be present
#             "s3:x-amz-server-side-encryption" = "aws:kms"
#           }
#         }
#       },
#       {
#         Sid    = "DenyUnencryptedObjectUploads", # Enforce encryption
#         Effect = "Deny",
#         Principal = "*",
#         Action = "s3:PutObject",
#         Resource = "${aws_s3_bucket.udim_user_data_bucket.arn}/*",
#         Condition = {
#           Null = {
#             "s3:x-amz-server-side-encryption" = "true"
#           }
#         }
#       },
#       # Statement to enforce HTTPS/TLS for all actions
#       {
#         Sid    = "DenyInsecureTransport",
#         Effect = "Deny",
#         Principal = "*",
#         Action = "s3:*",
#         Resource = "${aws_s3_bucket.udim_user_data_bucket.arn}/*",
#         Condition = {
#           Bool = {"aws:SecureTransport": "false"}
#         }
#       }
#       # Further statements would grant specific IAM roles (UDIM service, MAIPP service)
#       # necessary s3:PutObject, s3:GetObject, s3:ListBucket (if needed) permissions.
#       # Example for UDIM service role to PutObject:
#       # {
#       #   Sid    = "AllowUDIMServicePutObject",
#       #   Effect = "Allow",
#       #   Principal = { AWS = var.udim_service_iam_role_arn },
#       #   Action = "s3:PutObject", # Consider s3:PutObjectAcl if specific ACLs are needed by app
#       #   Resource = "${aws_s3_bucket.udim_user_data_bucket.arn}/*"
#       # },
#       # Example for MAIPP service role to GetObject:
#       # {
#       #   Sid    = "AllowMAIPPServiceGetObject",
#       #   Effect = "Allow",
#       #   Principal = { AWS = var.maipp_service_iam_role_arn },
#       #   Action = "s3:GetObject",
#       #   Resource = "${aws_s3_bucket.udim_user_data_bucket.arn}/*"
#       # }
#     ]
#   })
# }
```

## 2. AWS KMS Key for Data Encryption

**Objective:** To create a Customer Managed Key (CMK) in AWS KMS for encrypting and decrypting data stored in the UDIM S3 bucket via Server-Side Encryption (SSE-KMS).

**Key Considerations:**
*   **Key Policy (Resource Policy):** Define a key policy that grants necessary permissions:
    *   To AWS account administrators for managing the key (e.g., `arn:aws:iam::${var.aws_account_id}:root`).
    *   To the UDIM service IAM role for cryptographic operations required by S3 for SSE-KMS (primarily `kms:GenerateDataKey*` when S3 puts objects, and potentially `kms:Decrypt` if UDIM ever needs to read its own encrypted data, though less common).
    *   To the MAIPP service IAM role for `kms:Decrypt` operations on data it needs to process.
    *   It's crucial to scope these permissions correctly. S3 service needs permission to use the key on behalf of the roles putting objects.
*   **Key Rotation:** Enable automatic key rotation (annual, managed by AWS KMS).
*   **Alias:** Create a friendly alias for the key (e.g., `alias/echosphere/udim-data-key`) for easier reference.
*   **Deletion Window:** Set a reasonable deletion window (e.g., 7-30 days) to allow recovery from accidental deletion.

**Illustrative IaC (Terraform Example Comments):**

```terraform
# data "aws_iam_policy_document" "udim_kms_key_policy_doc" {
#   statement {
#     sid = "EnableRootUserManagement"
#     actions   = ["kms:*"]
#     resources = ["*"]
#     principals {
#       type        = "AWS"
#       identifiers = ["arn:aws:iam::${var.aws_account_id}:root"]
#     }
#   }
#
#   # Statement allowing S3 service to use the key on behalf of authorized users/roles for encryption
#   # This is often needed for SSE-KMS to work seamlessly when objects are put.
#   statement {
#     sid = "AllowS3ServiceToUseKeyForAuthorizedUploads"
#     actions = [
#       "kms:GenerateDataKey*", # For S3 to generate data keys
#       "kms:Encrypt"           # For S3 to encrypt objects
#     ]
#     resources = ["*"] # This key
#     principals {
#       type        = "Service"
#       identifiers = ["s3.amazonaws.com"]
#     }
#     # Condition to restrict to specific bucket can be added but can be complex
#     # Often, role-based S3 PutObject permissions combined with bucket's default encryption handles this
#   }
#
#   # Grant UDIM service role permissions for S3 object encryption (via S3 actions)
#   # The role performing s3:PutObject with SSE-KMS needs kms:GenerateDataKey* on the key
#   statement {
#     sid    = "AllowUDIMServiceForS3SSEKMSUploads"
#     effect = "Allow"
#     principals {
#       type        = "AWS"
#       identifiers = [var.udim_service_iam_role_arn]
#     }
#     actions   = ["kms:GenerateDataKey*"] # S3 needs this for PutObject with SSE-KMS
#     resources = ["*"] # Refers to this key
#   }
#
#   # Grant MAIPP service role permissions to decrypt data from S3
#   # The role performing s3:GetObject on SSE-KMS encrypted objects needs kms:Decrypt on the key
#   statement {
#     sid    = "AllowMAIPPServiceToDecryptS3Objects"
#     effect = "Allow"
#     principals {
#       type        = "AWS"
#       identifiers = [var.maipp_service_iam_role_arn]
#     }
#     actions   = ["kms:Decrypt"]
#     resources = ["*"] # Refers to this key
#   }
# }

# resource "aws_kms_key" "udim_data_encryption_key" {
#   description             = "KMS key for encrypting EchoSphere UDIM user data in S3"
#   deletion_window_in_days = 10 # Default is 30, can be 7-30.
#   enable_key_rotation     = true
#   policy                  = data.aws_iam_policy_document.udim_kms_key_policy_doc.json
#
#   tags = {
#     Name        = "EchoSphere UDIM Data Encryption Key"
#     Environment = var.environment
#     Project     = "EchoSphere"
#   }
# }

# resource "aws_kms_alias" "udim_data_encryption_key_alias" {
#   name          = "alias/echosphere/udim-data-key" # Define a clear alias
#   target_key_id = aws_kms_key.udim_data_encryption_key.key_id
# }
```

## 3. Summary

This conceptual IaC outline provides a blueprint for creating the necessary S3 and KMS resources for UDIM, emphasizing security best practices. Actual implementation will require translating this into executable Terraform, CloudFormation, or other IaC tool scripts, and populating variables such as AWS account IDs, regions, and specific IAM role ARNs derived from the application's deployment. The defined policies aim for a secure-by-default posture with least privilege access, ensuring data is encrypted and access is strictly controlled.
```
