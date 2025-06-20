# Phase 1: User Data Ingestion Module (UDIM) - Core Logic

This document outlines the core logical flows for the User Data Ingestion Module (UDIM) components in EchoSphere's Phase 1. The logic is presented primarily through pseudocode or detailed step-by-step descriptions.

## 1. User Authentication & Authorization (for API access)

**Objective:** To ensure that any request to a UDIM API endpoint is made by an authenticated user with the necessary permissions for the requested action.

*   **Input:** API Request containing an Authentication Token (e.g., OAuth 2.0 Bearer Token in `Authorization` header).
*   **Logic:**
    ```pseudocode
    FUNCTION HANDLE_API_REQUEST(request):
        token = EXTRACT_TOKEN_FROM_HEADER(request.headers.Authorization)

        IF token IS NULL OR EMPTY:
            RETURN HTTP_401_UNAUTHORIZED("Authentication token is missing.")
        END IF

        // Step 1: Token validation (format, expiry, signature)
        validationResult = VALIDATE_TOKEN_SIGNATURE_EXPIRY_FORMAT(token) // Uses a trusted JWT library or OAuth introspection endpoint
        IF validationResult.isValid IS FALSE:
            RETURN HTTP_401_UNAUTHORIZED("Invalid token: " + validationResult.error)
        END IF

        // Step 2: Extraction of userID and associated scopes/permissions
        tokenClaims = DECODE_TOKEN(token) // Contains userID, scopes, expiry, etc.
        requestingUserID = tokenClaims.userID
        grantedScopes = tokenClaims.scopes

        // Step 3: Verification that userID matches any userID in request path/body if applicable
        // Example: For an endpoint like /users/{userID}/data/upload
        IF request.pathParameters.userID IS NOT NULL AND request.pathParameters.userID IS NOT requestingUserID:
            RETURN HTTP_403_FORBIDDEN("User ID in path does not match authenticated user.")
        END IF
        // Similar checks if userID is expected in request body for certain operations

        // Step 4: Verification that token scopes permit the requested API action
        requiredScope = DETERMINE_REQUIRED_SCOPE_FOR_ENDPOINT(request.endpoint, request.method)
        IF requiredScope IS NOT IN grantedScopes:
            RETURN HTTP_403_FORBIDDEN("Insufficient permissions. Required scope: " + requiredScope)
        END IF

        // If all checks pass, store authenticated user info in request context for further processing
        request.context.authenticatedUserID = requestingUserID
        request.context.grantedScopes = grantedScopes

        PROCEED_WITH_REQUEST_LOGIC(request)

    OUTPUT: Proceed with request-specific logic OR HTTP Error Response (401 Unauthorized, 403 Forbidden).
    ```

## 2. Data Source Connection Management (OAuth Flow - simplified)

**Objective:** To securely connect a user's EchoSphere account with third-party data sources using OAuth 2.0.

*   **A. Initiate Connection (`GET /v1/users/{userID}/connections/oauth/{serviceName}/initiate`)**
    *   **Input:** Authenticated API Request (userID from token, serviceName from path).
    *   **Logic:**
        ```pseudocode
        FUNCTION INITIATE_OAUTH_CONNECTION(request):
            // User authentication/authorization already handled by a preceding general handler (Logic 1)
            callingUserID = request.context.authenticatedUserID
            serviceName = request.pathParameters.serviceName

            IF IS_SUPPORTED_OAUTH_SERVICE(serviceName) IS FALSE:
                RETURN HTTP_400_BAD_REQUEST("Unsupported service: " + serviceName)
            END IF

            // Generate and store a 'state' parameter for CSRF protection and session correlation
            csrfState = GENERATE_SECURE_RANDOM_STRING()
            STORE_OAUTH_STATE(csrfState, callingUserID, serviceName, request.queryParameters.redirect_uri_override) // Store with short expiry

            // Construct the third-party OAuth provider's authorization URL
            oauthProviderConfig = GET_OAUTH_PROVIDER_CONFIG(serviceName)
            authURL = CONSTRUCT_AUTHORIZATION_URL(
                oauthProviderConfig.authorizationEndpoint,
                oauthProviderConfig.clientID,
                oauthProviderConfig.requestedScopes, // Scopes for the third-party service
                UDIM_CALLBACK_URL_FOR_SERVICE(serviceName), // UDIM's /callback endpoint
                csrfState,
                oauthProviderConfig.additionalParams // e.g., response_type=code
            )

            RETURN HTTP_302_REDIRECT(authURL)
        OUTPUT: HTTP Redirect (302) to the third-party OAuth provider's authorization URL.
        ```

*   **B. Handle Callback (`GET /v1/connections/oauth/{serviceName}/callback`)**
    *   **Input:** Request from user's browser (redirected by OAuth provider) with `code` and `state` query parameters.
    *   **Logic:**
        ```pseudocode
        FUNCTION HANDLE_OAUTH_CALLBACK(request):
            receivedCode = request.queryParameters.code
            receivedState = request.queryParameters.state
            serviceName = request.pathParameters.serviceName

            IF receivedState IS NULL OR EMPTY:
                RETURN HTTP_400_BAD_REQUEST("State parameter is missing.")
            END IF

            // Validate received 'state' against the stored one
            storedStateDetails = RETRIEVE_AND_DELETE_OAUTH_STATE(receivedState)
            IF storedStateDetails IS NULL OR storedStateDetails.serviceName IS NOT serviceName:
                RETURN HTTP_400_BAD_REQUEST("Invalid or expired state parameter.")
            END IF

            userID = storedStateDetails.userID // User identified from stored state

            IF request.queryParameters.error IS NOT NULL:
                // User denied access or an error occurred at the provider
                LOG_OAUTH_ERROR(userID, serviceName, request.queryParameters.error, request.queryParameters.error_description)
                RETURN REDIRECT_TO_USER_FACING_ERROR_PAGE("OAuth authorization failed for " + serviceName + ": " + request.queryParameters.error_description)
            END IF

            IF receivedCode IS NULL OR EMPTY:
                RETURN HTTP_400_BAD_REQUEST("Authorization code is missing.")
            END IF

            // Exchange 'code' for access/refresh tokens with the OAuth provider
            oauthProviderConfig = GET_OAUTH_PROVIDER_CONFIG(serviceName)
            tokenResponse = EXCHANGE_CODE_FOR_TOKENS(
                oauthProviderConfig.tokenEndpoint,
                oauthProviderConfig.clientID,
                oauthProviderConfig.clientSecret,
                receivedCode,
                UDIM_CALLBACK_URL_FOR_SERVICE(serviceName) // Must match what was used in initiate
            )

            IF tokenResponse.isError:
                LOG_OAUTH_TOKEN_EXCHANGE_ERROR(userID, serviceName, tokenResponse.error)
                RETURN REDIRECT_TO_USER_FACING_ERROR_PAGE("Failed to obtain tokens for " + serviceName)
            END IF

            // Securely store these tokens (encrypted), associating them with the userID and serviceName
            connectionID = GENERATE_UUID()
            STORE_CONNECTION_DETAILS(
                connectionID,
                userID,
                serviceName,
                ENCRYPT(tokenResponse.accessToken),
                ENCRYPT(tokenResponse.refreshToken IF_EXISTS),
                tokenResponse.expiresIn,
                tokenResponse.grantedScopes // Scopes granted by the third party
            )

            // Optionally, create a basic ConsentLedgerEntry for the connection itself (e.g., "permission to list files")
            // More specific consents will be needed for actual data import.

            RETURN REDIRECT_TO_USER_FACING_SUCCESS_PAGE("Successfully connected to " + serviceName + ". Connection ID: " + connectionID)
        OUTPUT: Success/failure indication to the user (typically a redirect to a status page in the EchoSphere application).
        ```

## 3. Granular Consent Acquisition (Conceptual Flow)

**Objective:** To ensure explicit, informed user consent is obtained *before* any data is uploaded or imported for processing. UDIM relies on receiving a `consentTokenID` from this process.

*   **Trigger:** User initiates an action in a UI (not UDIM API directly) that will require new data to be processed (e.g., selecting files for upload, choosing items to import from a connected source).
*   **Logic (Conceptual - primarily UI/Consent Service interaction):**
    ```pseudocode
    FUNCTION OBTAIN_CONSENT_FOR_DATA_PROCESSING(userID, dataItemsDescriptors, purposeKey, requestedScopes):
        // dataItemsDescriptors: List of objects describing each item (e.g., {fileName, dataType, source})
        // purposeKey: A key identifying the reason for processing (e.g., "persona_creation_phase1_text_analysis")
        // requestedScopes: List of specific permissions needed (e.g., ["read_raw", "extract_linguistic_traits"])

        // 1. Present UI to the user detailing:
        humanReadablePurpose = LOOKUP_PURPOSE_DESCRIPTION(purposeKey)
        humanReadableScopes = FORMAT_SCOPES_FOR_DISPLAY(requestedScopes)
        relevantRetentionPolicy = GET_DATA_RETENTION_POLICY(purposeKey, dataItemsDescriptors.dataType)

        UI_DISPLAY_CONSENT_REQUEST_SCREEN(
            dataItems: dataItemsDescriptors,
            purpose: humanReadablePurpose,
            permissionsRequested: humanReadableScopes,
            retentionInfo: relevantRetentionPolicy
        )

        // 2. User reviews and makes granular choices (UI allows toggling scopes if design permits)
        userChoices = WAIT_FOR_USER_INTERACTION_ON_UI() // Returns accepted/modified scopes

        IF userChoices.isRejected:
            RETURN NULL // Consent denied
        END IF

        // 3. User explicitly confirms consent (e.g., clicks "Agree & Proceed" button)
        IF userChoices.isConfirmed IS FALSE: // e.g. user navigates away
            RETURN NULL
        END IF

        // 4. A ConsentLedgerEntry object is constructed
        dataHashes = []
        FOR EACH item IN dataItemsDescriptors:
            // In a real scenario, hash might be of actual data if available, or a stable descriptor
            dataHashes.ADD(CALCULATE_DATA_HASH(item.descriptor_or_preview_content))
        END FOR
        // Consolidate hashes if many items, e.g., Merkle root
        consolidatedDataHash = COMPUTE_CONSOLIDATED_HASH(dataHashes)

        consentEntry = CREATE_CONSENT_LEDGER_ENTRY_OBJECT(
            userID = userID,
            dataHash = consolidatedDataHash,
            consentScope = userChoices.finalScopes,
            purposeDescription = humanReadablePurpose,
            // ... other fields like expiration, version
        )

        // 5. User "signs" or approves this consent record
        // This step is conceptual for Phase 1 UDIM's direct involvement.
        // In a full system, this might be a call to a UCMS API which handles the signature.
        // For now, we assume approval is captured by the UI flow.

        // 6. The ConsentLedgerEntry is securely recorded
        // This is an internal call to a Consent Ledger Service (or UCMS) API
        recordingResult = RECORD_CONSENT_IN_LEDGER(consentEntry)

        IF recordingResult.isSuccess:
            // 7. The consentTokenID of the new entry is returned
            RETURN recordingResult.consentTokenID
        ELSE:
            LOG_ERROR("Failed to record consent: " + recordingResult.error)
            UI_DISPLAY_ERROR("Could not save consent preferences.")
            RETURN NULL
        END IF
    OUTPUT: `consentTokenID` (UUID) OR NULL if consent denied/failed.
    ```

## 4. Data Reception & Validation (for `POST /v1/users/{userID}/data/upload`)

**Objective:** To receive, validate, and perform initial security checks on directly uploaded user data.

*   **Input:** HTTP request with `multipart/form-data` (containing `file`, `sourceDescription`, `dataType` (optional), `consentTokenID`).
*   **Logic:**
    ```pseudocode
    FUNCTION HANDLE_DATA_UPLOAD_REQUEST(request):
        // 1. Authenticate and authorize user (handled by general auth logic - see 1)
        //    Ensures token is valid and user in path matches token.
        //    Ensures token has 'data:upload' scope.
        authenticatedUserID = request.context.authenticatedUserID

        // 2. Verify consentTokenID
        consentTokenID = request.formData.consentTokenID
        IF consentTokenID IS NULL:
            RETURN HTTP_400_BAD_REQUEST("consentTokenID is required.")
        END IF

        // Construct required scope for consent verification based on provided data info
        // This scope needs to be specific enough for the consent system.
        // For example, it might include dataType if provided, or a general "upload" action.
        // For simplicity, a generic scope for upload is used here.
        // A more robust system might derive a hash of the file to check against dataHash in consent.
        requiredConsentScope = "action:data:upload,resource_type:" + (request.formData.dataType OR "generic_file")

        consentVerificationResult = CALL_INTERNAL_CONSENT_API_VERIFY(
            userID = authenticatedUserID,
            consentTokenID = consentTokenID,
            requiredScope = requiredConsentScope
            // Potentially add dataHash if feasible to compute pre-upload or from client
        )

        IF consentVerificationResult.isValid IS FALSE:
            RETURN HTTP_403_FORBIDDEN("Provided consentTokenID is invalid, expired, revoked, or does not cover this data upload. Reason: " + consentVerificationResult.reason_for_invalidity)
        END IF

        // 3. Parse multipart/form-data
        fileData = request.formData.file
        sourceDescription = request.formData.sourceDescription
        clientProvidedDataType = request.formData.dataType

        // 4. Validate presence of required fields
        IF fileData IS NULL OR sourceDescription IS NULL OR EMPTY:
            RETURN HTTP_400_BAD_REQUEST("Missing required fields: 'file' and 'sourceDescription'.")
        END IF

        // 5. Validate file size
        IF fileData.size > MAX_ALLOWED_FILE_SIZE:
            RETURN HTTP_413_PAYLOAD_TOO_LARGE("File size exceeds maximum limit of " + MAX_ALLOWED_FILE_SIZE_MB + "MB.")
        END IF

        // 6. Perform initial security scan on the file
        scanResult = SCAN_FILE_FOR_MALWARE(fileData.tempPath)
        IF scanResult.isThreatDetected:
            LOG_SECURITY_EVENT("Malware detected in upload from " + authenticatedUserID + ", file: " + fileData.originalName)
            RETURN HTTP_400_BAD_REQUEST("Malicious file detected.")
        END IF

        // 7. Determine/confirm dataType (MIME type)
        determinedDataType = DETERMINE_MIME_TYPE(fileData.tempPath, clientProvidedDataType, fileData.originalName)
        IF IS_UNSUPPORTED_DATA_TYPE(determinedDataType):
             RETURN HTTP_415_UNSUPPORTED_MEDIA_TYPE("File type " + determinedDataType + " is not supported.")
        END IF

        // Store validated data for next step
        request.context.validatedFileData = fileData
        request.context.validatedSourceDescription = sourceDescription
        request.context.validatedDataType = determinedDataType
        request.context.validatedConsentTokenID = consentTokenID

        PROCEED_TO_ENCRYPTION_AND_STORAGE(request)

    OUTPUT: Proceed to Encryption & Secure Storage OR HTTP Error Response.
    ```

## 5. Encryption & Secure Temporary Storage

**Objective:** To encrypt validated user data and store it securely, then record its metadata.

*   **Input:** Validated file data (from `request.context`), `userID`, `sourceDescription`, `dataType`, `consentTokenID`.
*   **Logic:**
    ```pseudocode
    FUNCTION ENCRYPT_AND_STORE_DATA(request):
        userID = request.context.authenticatedUserID
        fileData = request.context.validatedFileData
        sourceDescription = request.context.validatedSourceDescription
        dataType = request.context.validatedDataType
        consentTokenID = request.context.validatedConsentTokenID

        // 1. Generate a unique packageID (UUID)
        packageID = GENERATE_UUID()

        // 2. Retrieve/generate a unique encryptionKeyID for this package via KMS
        // The key itself is managed by KMS; UDIM only handles the key's ID/alias.
        encryptionKeyID = GET_OR_CREATE_ENCRYPTION_KEY_FOR_PACKAGE(userID, packageID) // KMS interaction
        IF encryptionKeyID IS NULL:
            LOG_ERROR("Failed to get encryption key from KMS for user " + userID)
            RETURN HTTP_500_INTERNAL_SERVER_ERROR("Failed to prepare data for secure storage.")
        END IF

        // 3. Encrypt the file data using this key
        // Stream encryption for large files is preferred
        encryptedFileStreamOrPath = ENCRYPT_FILE_STREAM(fileData.tempPath, encryptionKeyID) // KMS might be involved in encryption directly or provide data key
        IF encryptedFileStreamOrPath IS NULL:
            LOG_ERROR("File encryption failed for " + fileData.originalName + " for user " + userID)
            RETURN HTTP_500_INTERNAL_SERVER_ERROR("Failed to encrypt data.")
        END IF

        // 4. Construct the rawDataReference (e.g., S3 object path)
        // Path should prevent collisions and allow for easier data lifecycle management.
        s3ObjectKey = "users/" + userID + "/packages/" + packageID + "/" + SanitizeFilename(fileData.originalName) + ".enc"
        rawDataReference = "s3://" + S3_USER_DATA_BUCKET + "/" + s3ObjectKey

        // 5. Upload the encrypted file to secure external storage
        uploadSuccess = UPLOAD_TO_S3(encryptedFileStreamOrPath, S3_USER_DATA_BUCKET, s3ObjectKey, SERVER_SIDE_ENCRYPTION_SETTINGS_WITH_KMS_KEY(encryptionKeyID))
        CLEANUP_TEMP_ENCRYPTED_FILE(encryptedFileStreamOrPath) // If it was a temp file
        CLEANUP_TEMP_UPLOADED_FILE(fileData.tempPath)

        IF uploadSuccess IS FALSE:
            LOG_ERROR("S3 upload failed for " + rawDataReference)
            RETURN HTTP_500_INTERNAL_SERVER_ERROR("Failed to store data securely.")
        END IF

        // 6. Store UserDataPackage metadata in UDIM database
        packageMetadata = {
            originalFilename: fileData.originalName,
            fileSizeBytes: fileData.size
            // Add other relevant metadata, e.g., image dimensions if applicable
        }
        userDataPackageRecord = CREATE_USER_DATA_PACKAGE_RECORD(
            packageID = packageID,
            userID = userID,
            dataType = dataType,
            sourceDescription = sourceDescription,
            rawDataReference = rawDataReference,
            encryptionKeyID = encryptionKeyID, // Store the ID/ARN of the KMS key used
            consentTokenID = consentTokenID,
            uploadTimestamp = CURRENT_UTC_TIMESTAMP(),
            metadata = packageMetadata,
            status = "pending_processing" // Initial status after successful storage
        )
        dbSuccess = SAVE_TO_DATABASE(userDataPackageRecord)

        IF dbSuccess IS FALSE:
            LOG_CRITICAL_ERROR("Failed to save UserDataPackage metadata for " + packageID + ". S3 object " + rawDataReference + " might be orphaned.")
            // Implement compensating action: e.g., flag for cleanup, alert admins.
            RETURN HTTP_500_INTERNAL_SERVER_ERROR("Failed to finalize data ingestion record.")
        END IF

        // Store details for notification step
        request.context.createdPackageID = packageID
        request.context.createdPackageRecord = userDataPackageRecord

        PROCEED_TO_NOTIFICATION_HANDOFF(request)

    OUTPUT: `packageID` and status recorded; proceed to Notification/Handoff.
    ```

## 6. ConsentLedger Interaction (Verification)

**Objective:** To ensure UDIM verifies consent before proceeding with data handling. (Consent creation is conceptually pre-UDIM for specific uploads/imports).

*   **Logic (primarily for verification by UDIM):**
    ```pseudocode
    // This logic is integrated into Step 2 of "Data Reception & Validation" (Logic 4)
    // and would also be used before initiating an import from a connected source (Phase 3 API).

    FUNCTION VERIFY_UPLOAD_CONSENT(userID, consentTokenID, fileMetadata):
        // fileMetadata could include dataType, fileName, or even a hash if available
        // to construct a very specific requiredScope.

        // Example: Construct a scope string representing the permission needed.
        // The actual structure of requiredScope must match what Consent Service expects.
        requiredScope = "action:data:upload,resource_type:" + fileMetadata.dataType
        // More granular: requiredScope = "action:data:upload,resource_hash:" + CALCULATE_DATA_HASH(fileMetadata.preview_or_full_data)


        consentVerificationResult = CALL_INTERNAL_CONSENT_API_VERIFY(
            userID = userID,
            consentTokenID = consentTokenID,
            requiredScope = requiredScope
            // dataHash = (if available and part of verification)
        )

        RETURN consentVerificationResult // Contains {isValid: true/false, reason_for_invalidity, ...}
    ```
    *   **Note on Consent Creation:** While UDIM doesn't *create* granular consent for each upload via its API (it expects a `consentTokenID`), the broader EchoSphere system ensures this `consentTokenID` corresponds to a `ConsentLedgerEntry`. If, hypothetically, UDIM needed to log a system-level consent (e.g., "consent to use UDIM service"), it would call a `RECORD_CONSENT_IN_LEDGER` internal API with a pre-defined scope.

## 7. Notification/Handoff to MAIPP

**Objective:** To inform the MAIPP that new data is ready for processing.

*   **Input:** Details of the successfully stored `UserDataPackage` (from `request.context.createdPackageRecord`).
*   **Logic:**
    ```pseudocode
    FUNCTION NOTIFY_MAIPP_OF_NEW_DATA(request):
        packageRecord = request.context.createdPackageRecord

        maippNotificationPayload = {
            packageID: packageRecord.packageID,
            userID: packageRecord.userID,
            consentTokenID: packageRecord.consentTokenID,
            rawDataReference: packageRecord.rawDataReference,
            dataType: packageRecord.dataType,
            sourceDescription: packageRecord.sourceDescription,
            metadata: packageRecord.metadata
        }

        // Make the internal API call to MAIPP
        maxRetries = 3
        FOR attempt FROM 1 TO maxRetries:
            maippResponse = CALL_INTERNAL_MAIPP_API_DATA_READY(maippNotificationPayload)

            IF maippResponse.isSuccess (e.g., HTTP 200 or 202):
                UPDATE_USER_DATA_PACKAGE_STATUS(packageRecord.packageID, "queued_for_maipp_processing")
                // Return success response to original user API call (e.g., 202 Accepted for the upload)
                RETURN GENERATE_UPLOAD_SUCCESS_RESPONSE(packageRecord, "pending_validation_and_processing") // The user sees "pending", internal status is "queued_for_maipp"
            END IF

            // If MAIPP call failed but is retryable (e.g. 5xx from MAIPP)
            IF maippResponse.isRetryable AND attempt < maxRetries:
                WAIT_FOR_EXPONENTIAL_BACKOFF_DELAY(attempt)
            ELSE:
                // Non-retryable error from MAIPP, or max retries reached
                LOG_ERROR("Failed to notify MAIPP for package " + packageRecord.packageID + " after " + attempt + " attempts. Error: " + maippResponse.error)
                UPDATE_USER_DATA_PACKAGE_STATUS(packageRecord.packageID, "error_maipp_notification")
                // This is an internal error; the user's upload was successful up to storage.
                // The original API call might still return 202, but an internal alert is critical.
                SEND_ADMIN_ALERT("MAIPP notification failed for package " + packageRecord.packageID)
                RETURN GENERATE_UPLOAD_SUCCESS_RESPONSE(packageRecord, "pending_validation_and_processing_error_downstream") // Or similar status indicating issue post-upload
            END IF
        END FOR
    OUTPUT: `UserDataPackage` status updated based on MAIPP notification outcome. Final response to the user's original upload API call.
    ```
```
