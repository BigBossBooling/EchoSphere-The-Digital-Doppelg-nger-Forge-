# Phase 1: AI Persona Analysis & Trait Extraction (MAIPP) - Core Logic

This document outlines the core logical flows for the AI Persona Analysis & Trait Extraction (MAIPP) module in EchoSphere's Phase 1. The logic is presented primarily through pseudocode or detailed step-by-step descriptions. MAIPP is responsible for processing consented user data, extracting features, identifying trait candidates, and populating the initial Persona Knowledge Graph (PKG).

## Overall MAIPP Orchestration Flow

**Trigger:** Notification from UDIM (via SQS message or internal API call like `POST /internal/maipp/v1/data-ready`) indicating a new `UserDataPackage` is ready for processing.

**Input:** `UserDataPackage` details (`packageID`, `userID`, `consentTokenID`, `rawDataReference`, `dataType`, `sourceDescription`, `metadata`).

**Core Logic:**
```pseudocode
FUNCTION HANDLE_NEW_DATA_PACKAGE_FOR_MAIPP(packageDetails):
    // 1. Log receipt of processing request
    LOG_INFO("MAIPP: Received package " + packageDetails.packageID + " for user " + packageDetails.userID)

    // 2. Initial Consent Verification for overall MAIPP processing (broad scope)
    // This is a general consent to allow MAIPP to orchestrate various analyses.
    // Specific analyses within MAIPP will perform more granular consent checks.
    maippProcessingScope = "action:analyze_data_for_persona_creation,resource_package_id:" + packageDetails.packageID
    consentResult = CALL_INTERNAL_CONSENT_API_VERIFY(
        userID = packageDetails.userID,
        consentTokenID = packageDetails.consentTokenID,
        requiredScope = maippProcessingScope
    )
    IF consentResult.isValid IS FALSE:
        LOG_ERROR("MAIPP: Consent denied for overall processing of package " + packageDetails.packageID + ". Reason: " + consentResult.reason_for_invalidity)
        UPDATE_USER_DATA_PACKAGE_STATUS(packageDetails.packageID, "error_maipp_consent_denied")
        RETURN FAILURE
    END IF

    // 3. Securely Retrieve and Decrypt Raw Data
    // This step requires careful handling of decryption keys, potentially involving KMS.
    // The rawDataReference points to encrypted data in S3.
    encryptedDataLocation = packageDetails.rawDataReference
    encryptionKeyID = GET_ENCRYPTION_KEY_ID_FOR_PACKAGE(packageDetails.packageID) // From UserDataPackage metadata

    decryptedDataStream = SECURELY_DECRYPT_DATA_FROM_STORAGE(encryptedDataLocation, encryptionKeyID) // Involves KMS
    IF decryptedDataStream IS NULL:
        LOG_ERROR("MAIPP: Failed to decrypt data for package " + packageDetails.packageID)
        UPDATE_USER_DATA_PACKAGE_STATUS(packageDetails.packageID, "error_maipp_decryption_failed")
        RETURN FAILURE
    END IF
    // Note: Decrypted data should only exist in memory or secure, ephemeral storage during processing.

    // 4. Modality-Specific Analysis Orchestration
    // This is the core of MAIPP, dispatching to different analysis pipelines.
    allExtractedFeatures = [] // List to hold RawAnalysisFeatures records
    allTraitCandidates = []   // List to hold ExtractedTraitCandidate records

    SWITCH packageDetails.dataType:
        CASE "text/plain", "application/pdf", "application/msword", ... (Text-based types):
            textAnalysisResults = PROCESS_TEXT_DATA(
                packageDetails.userID,
                packageDetails.packageID,
                packageDetails.consentTokenID,
                decryptedDataStream,
                packageDetails.metadata
            )
            allExtractedFeatures.ADD_ALL(textAnalysisResults.rawFeatures)
            allTraitCandidates.ADD_ALL(textAnalysisResults.traitCandidates)
            BREAK

        CASE "audio/mpeg", "audio/wav", "audio/ogg", ... (Audio-based types):
            audioAnalysisResults = PROCESS_AUDIO_DATA(
                packageDetails.userID,
                packageDetails.packageID,
                packageDetails.consentTokenID,
                decryptedDataStream,
                packageDetails.metadata
            )
            allExtractedFeatures.ADD_ALL(audioAnalysisResults.rawFeatures)
            allTraitCandidates.ADD_ALL(audioAnalysisResults.traitCandidates)
            BREAK

        CASE "video/mp4", "video/quicktime", ... (Video-based types - conceptual for Phase 1, might be limited):
            videoAnalysisResults = PROCESS_VIDEO_DATA( // Might involve extracting audio & text first
                packageDetails.userID,
                packageDetails.packageID,
                packageDetails.consentTokenID,
                decryptedDataStream,
                packageDetails.metadata
            )
            allExtractedFeatures.ADD_ALL(videoAnalysisResults.rawFeatures)
            allTraitCandidates.ADD_ALL(videoAnalysisResults.traitCandidates)
            BREAK

        CASE "image/jpeg", "image/png", ... (Image-based types - conceptual for Phase 1, limited scope e.g. OCR):
             imageAnalysisResults = PROCESS_IMAGE_DATA(
                packageDetails.userID,
                packageDetails.packageID,
                packageDetails.consentTokenID,
                decryptedDataStream,
                packageDetails.metadata
            )
            allExtractedFeatures.ADD_ALL(imageAnalysisResults.rawFeatures)
            allTraitCandidates.ADD_ALL(imageAnalysisResults.traitCandidates)
            BREAK

        DEFAULT:
            LOG_WARNING("MAIPP: Unsupported data type " + packageDetails.dataType + " for package " + packageDetails.packageID)
            UPDATE_USER_DATA_PACKAGE_STATUS(packageDetails.packageID, "error_maipp_unsupported_type")
            // No features or traits extracted for this package type by MAIPP.
            // UDIM should ideally filter these, but MAIPP has a fallback.
    END SWITCH

    // 5. Securely Store RawAnalysisFeatures
    IF allExtractedFeatures IS NOT EMPTY:
        SAVE_RAW_ANALYSIS_FEATURES_BATCH(allExtractedFeatures) // To MongoDB or chosen store
    END IF

    // 6. Trait Candidate Synthesis & Refinement (Initial - more advanced in later phases)
    // For Phase 1, this might be a direct aggregation of candidates from different analyzers.
    // Later phases might involve more complex synthesis, cross-referencing, and confidence boosting.
    synthesizedTraitCandidates = AGGREGATE_AND_DEDUPLICATE_TRAIT_CANDIDATES(allTraitCandidates)

    // 7. Securely Store ExtractedTraitCandidates
    IF synthesizedTraitCandidates IS NOT EMPTY:
        SAVE_EXTRACTED_TRAIT_CANDIDATES_BATCH(synthesizedTraitCandidates) // To PostgreSQL
    END IF

    // 8. Initial Persona Knowledge Graph (PKG) Population
    // This involves adding/updating nodes and relationships based on candidates and features.
    IF synthesizedTraitCandidates IS NOT EMPTY OR allExtractedFeatures IS NOT EMPTY:
        UPDATE_PERSONA_KNOWLEDGE_GRAPH(
            packageDetails.userID,
            synthesizedTraitCandidates,
            allExtractedFeatures
            // Pass consentTokenID if PKG updates need to verify specific fine-grained consents
        )
    END IF

    // 9. Finalize and Cleanup
    SECURELY_DISPOSE_DECRYPTED_DATA(decryptedDataStream)
    UPDATE_USER_DATA_PACKAGE_STATUS(packageDetails.packageID, "processed_by_maipp")
    LOG_INFO("MAIPP: Successfully processed package " + packageDetails.packageID)
    RETURN SUCCESS

OUTPUT: SUCCESS or FAILURE (with UserDataPackage status updated accordingly).
```

## Modality-Specific Processing Logic (Examples)

### A. `PROCESS_TEXT_DATA`

**Input:** `userID`, `packageID`, `consentTokenID`, `textDataStream`, `metadata`
**Core Logic:**
```pseudocode
FUNCTION PROCESS_TEXT_DATA(userID, packageID, consentTokenID, textDataStream, metadata):
    extractedText = EXTRACT_TEXT_CONTENT_FROM_STREAM(textDataStream, metadata.originalMimeType) // Handles PDF, DOCX to TXT
    rawFeaturesList = []
    traitCandidatesList = []

    // --- Stage 1: Basic Text Features (e.g., Readability, Complexity) ---
    consentScope_basic = "action:analyze_text_basic_features,resource_package_id:" + packageID
    IF VERIFY_CONSENT(userID, consentTokenID, consentScope_basic).isValid:
        basicFeatures = CALCULATE_BASIC_TEXT_STATS(extractedText) // Word count, sentence count, readability (Flesch-Kincaid)
        rawFeaturesList.ADD(CREATE_RAW_ANALYSIS_FEATURES_RECORD(
            userID, packageID, "text", "Internal_TextStat_Analyzer", basicFeatures
        ))
        // Potentially generate trait candidates like "Writes concisely" or "Uses complex sentences"
        traitCandidatesList.ADD_ALL(DERIVE_TRAITS_FROM_BASIC_STATS(basicFeatures, packageID))
    END IF

    // --- Stage 2: Sentiment & Emotion Analysis ---
    consentScope_sentiment = "action:analyze_text_sentiment_emotion,resource_package_id:" + packageID
    IF VERIFY_CONSENT(userID, consentTokenID, consentScope_sentiment).isValid:
        // Example: Using Hugging Face Transformer model
        sentimentResults = CALL_SENTIMENT_EMOTION_MODEL(extractedText, "HF_BERT_Sentiment_Emotion")
        rawFeaturesList.ADD(CREATE_RAW_ANALYSIS_FEATURES_RECORD(
            userID, packageID, "text", "HF_BERT_Sentiment_Emotion", sentimentResults.features
        ))
        traitCandidatesList.ADD_ALL(DERIVE_TRAITS_FROM_SENTIMENT(sentimentResults.traits, packageID))
    END IF

    // --- Stage 3: Topic Modeling & Keyword Extraction ---
    consentScope_topic = "action:analyze_text_topics_keywords,resource_package_id:" + packageID
    IF VERIFY_CONSENT(userID, consentTokenID, consentScope_topic).isValid:
        // Example: Using OpenAI/Anthropic/Google LLM for summarization, topics, keywords
        llmAnalysisResults = CALL_LLM_FOR_TEXT_ANALYSIS(extractedText, "Google_Gemini_Text_Summarize_Topic")
        rawFeaturesList.ADD(CREATE_RAW_ANALYSIS_FEATURES_RECORD(
            userID, packageID, "text", "Google_Gemini_Text_Summarize_Topic", llmAnalysisResults.features
        ))
        // Traits like "Frequently discusses AI", "Knowledgeable in History"
        traitCandidatesList.ADD_ALL(DERIVE_TRAITS_FROM_LLM_ANALYSIS(llmAnalysisResults.traits, packageID))
    END IF

    // --- Stage 4: Linguistic Style & Pattern Analysis (Advanced) ---
    // (e.g., passive/active voice, question frequency, use of specific jargon)
    consentScope_style = "action:analyze_text_linguistic_style,resource_package_id:" + packageID
    IF VERIFY_CONSENT(userID, consentTokenID, consentScope_style).isValid:
        styleFeatures = ANALYZE_LINGUISTIC_STYLE(extractedText, "Custom_Style_Analyzer_v1")
        rawFeaturesList.ADD(CREATE_RAW_ANALYSIS_FEATURES_RECORD(
            userID, packageID, "text", "Custom_Style_Analyzer_v1", styleFeatures
        ))
        traitCandidatesList.ADD_ALL(DERIVE_TRAITS_FROM_LINGUISTIC_STYLE(styleFeatures, packageID))
    END IF

    RETURN {rawFeatures: rawFeaturesList, traitCandidates: traitCandidatesList}
```

### B. `PROCESS_AUDIO_DATA`

**Input:** `userID`, `packageID`, `consentTokenID`, `audioDataStream`, `metadata`
**Core Logic:**
```pseudocode
FUNCTION PROCESS_AUDIO_DATA(userID, packageID, consentTokenID, audioDataStream, metadata):
    rawFeaturesList = []
    traitCandidatesList = []

    // --- Stage 1: Transcription (Speech-to-Text) ---
    // Consent for transcription might be separate or bundled with voice analysis
    consentScope_transcribe = "action:transcribe_audio,resource_package_id:" + packageID
    transcribedText = NULL
    IF VERIFY_CONSENT(userID, consentTokenID, consentScope_transcribe).isValid:
        transcriptionResult = CALL_SPEECH_TO_TEXT_API(audioDataStream, "OpenAI_Whisper_v3") // e.g., OpenAI Whisper
        rawFeaturesList.ADD(CREATE_RAW_ANALYSIS_FEATURES_RECORD(
            userID, packageID, "audio", "OpenAI_Whisper_v3_Transcription", transcriptionResult.features // features like word timings, confidence
        ))
        transcribedText = transcriptionResult.text
    ELSE:
        LOG_INFO("MAIPP: Transcription consent denied for audio package " + packageID)
    END IF

    // --- Stage 2: Voice Characteristics Analysis (Prosody, Speech Metrics) ---
    consentScope_voice_char = "action:analyze_audio_voice_characteristics,resource_package_id:" + packageID
    IF VERIFY_CONSENT(userID, consentTokenID, consentScope_voice_char).isValid:
        // Use original audio stream for this, not just transcript
        voiceFeatures = ANALYZE_VOICE_PROSODY_METRICS(audioDataStream, "Librosa_Praat_Analyzer") // e.g., pitch, jitter, shimmer, speech rate
        rawFeaturesList.ADD(CREATE_RAW_ANALYSIS_FEATURES_RECORD(
            userID, packageID, "audio", "Librosa_Praat_Analyzer", voiceFeatures
        ))
        // Traits like "Speaks quickly", "Modulated voice tone"
        traitCandidatesList.ADD_ALL(DERIVE_TRAITS_FROM_VOICE_FEATURES(voiceFeatures, packageID))
    END IF

    // --- Stage 3: Emotion/Sentiment from Audio Tone ---
    consentScope_voice_emotion = "action:analyze_audio_voice_emotion,resource_package_id:" + packageID
    IF VERIFY_CONSENT(userID, consentTokenID, consentScope_voice_emotion).isValid:
        voiceEmotionResults = CALL_VOICE_EMOTION_MODEL(audioDataStream, "HF_Wav2Vec2_Emotion")
        rawFeaturesList.ADD(CREATE_RAW_ANALYSIS_FEATURES_RECORD(
            userID, packageID, "audio", "HF_Wav2Vec2_Emotion", voiceEmotionResults.features
        ))
        // Traits like "Often sounds cheerful", "Expresses conviction through tone"
        traitCandidatesList.ADD_ALL(DERIVE_TRAITS_FROM_VOICE_EMOTION(voiceEmotionResults.traits, packageID))
    END IF

    // --- Stage 4: Process Transcribed Text (If available and consented) ---
    IF transcribedText IS NOT NULL:
        // Re-use PROCESS_TEXT_DATA logic, but ensure consent scopes are specific to "text_derived_from_audio"
        // This requires careful consent scope definition, e.g.,
        // "action:analyze_text_sentiment_emotion,resource_derived_from_audio_package_id:" + packageID
        // For simplicity, assuming consentTokenID for audio might cover derived text analysis if scoped broadly,
        // otherwise, a new consent check or derived consent is needed.

        LOG_INFO("MAIPP: Processing transcribed text from audio package " + packageID)
        // Pass a new data stream created from 'transcribedText'
        textFromAudioResults = PROCESS_TEXT_DATA(
            userID,
            packageID, // Link to original audio package
            consentTokenID, // Use same token, assuming it covers derived text analysis or verify specific scope
            CREATE_STREAM_FROM_STRING(transcribedText),
            {originalMimeType: "text/plain", source_package_type: "audio"} // New metadata
        )
        // Prepend model names with e.g. "AudioDerivedText_" to distinguish
        rawFeaturesList.ADD_ALL(PREFIX_MODEL_NAMES(textFromAudioResults.rawFeatures, "AudioDerivedText_"))
        traitCandidatesList.ADD_ALL(PREFIX_TRAIT_ORIGINS(textFromAudioResults.traitCandidates, "AudioDerivedText_"))
    END IF

    RETURN {rawFeatures: rawFeaturesList, traitCandidates: traitCandidatesList}
```

### C. `UPDATE_PERSONA_KNOWLEDGE_GRAPH`

**Input:** `userID`, `traitCandidatesList`, `rawFeaturesList`
**Core Logic (Conceptual for Phase 1 - focuses on adding traits and concepts):**
```pseudocode
FUNCTION UPDATE_PERSONA_KNOWLEDGE_GRAPH(userID, traitCandidatesList, rawFeaturesList):
    // Ensure User node exists
    userNode = GET_OR_CREATE_USER_NODE_IN_PKG(userID)

    FOR EACH candidate IN traitCandidatesList:
        // Only process candidates with sufficient confidence or specific status if needed
        IF candidate.confidenceScore < MIN_CONFIDENCE_FOR_PKG_INITIAL_ADD:
            CONTINUE
        END IF

        // Check if a similar Trait node already exists to avoid duplicates, or update.
        // This logic can become complex, involving semantic similarity.
        // For Phase 1, assume new trait nodes are created from candidates, to be refined later by PTFI.

        traitNode = CREATE_TRAIT_NODE_IN_PKG(
            name = candidate.traitName,
            description = candidate.traitDescription,
            category = candidate.traitCategory,
            // PKG 'Trait' node might have a 'candidate_confidence' or similar field
            // It will get its final 'confidence' after user refinement.
            candidateConfidence = candidate.confidenceScore,
            originModels = candidate.originatingModels,
            status = "candidate_in_pkg" // A status specific to PKG representation of a candidate
        )

        // Create relationship from User to Trait
        CREATE_RELATIONSHIP_IN_PKG(userNode, "HAS_CANDIDATE_TRAIT", traitNode, {
            addedTimestamp: CURRENT_TIMESTAMP(),
            sourceCandidateID: candidate.candidateID
        })

        // Link Trait node to evidence snippets (SourceDataReferenceNode)
        FOR EACH evidence IN candidate.supportingEvidenceSnippets:
            evidenceNode = GET_OR_CREATE_EVIDENCE_NODE_IN_PKG(
                sourceUserDataPackageID = evidence.sourcePackageID,
                snippet = evidence.content, // Or reference like offset/timestamp
                sourceDetail = evidence.sourceDetail
            )
            CREATE_RELATIONSHIP_IN_PKG(traitNode, "EVIDENCED_BY", evidenceNode, {relevance: evidence.relevanceScore_if_any})
        END FOR
    END FOR

    // Extract and add Concepts from raw features (e.g., NER results, topics)
    // This requires specific logic to iterate through rawFeaturesList, find relevant features,
    // and then create/link Concept nodes.
    identifiedConcepts = EXTRACT_CONCEPTS_FROM_RAW_FEATURES(rawFeaturesList, userID, consentTokenID) // Consent for concept extraction
    FOR EACH conceptName IN identifiedConcepts:
        conceptNode = GET_OR_CREATE_CONCEPT_NODE_IN_PKG(conceptName)
        // Link User to Concept or Trait to Concept based on analysis
        // Example: If a trait was derived from text discussing "AI Ethics"
        // relevantTraitNode = FIND_TRAIT_NODE_LINKED_TO_FEATURE(conceptDerivationFeature)
        // CREATE_RELATIONSHIP_IN_PKG(relevantTraitNode, "ASSOCIATED_WITH_CONCEPT", conceptNode)
        // Or directly:
        CREATE_RELATIONSHIP_IN_PKG(userNode, "DISCUSSED_CONCEPT", conceptNode, {frequency: identifiedConcepts.frequency[conceptName]})
    END FOR

    LOG_INFO("MAIPP: Persona Knowledge Graph updated for user " + userID)
```

**Helper Functions (Conceptual Signatures):**
*   `VERIFY_CONSENT(userID, consentTokenID, requiredScope)`: Calls internal Consent Verification API.
*   `SECURELY_DECRYPT_DATA_FROM_STORAGE(location, keyID)`: Interacts with S3 and KMS.
*   `EXTRACT_TEXT_CONTENT_FROM_STREAM(stream, mimeType)`: Uses libraries like `pypdf2`, `python-docx`.
*   `CALCULATE_BASIC_TEXT_STATS(text)`: Uses text processing libraries.
*   `CALL_SENTIMENT_EMOTION_MODEL(text, modelIdentifier)`: Calls a specific AI service/model.
*   `CALL_LLM_FOR_TEXT_ANALYSIS(text, modelIdentifier)`: Calls an LLM API.
*   `ANALYZE_LINGUISTIC_STYLE(text, modelIdentifier)`: Calls a specific AI service/model.
*   `CREATE_RAW_ANALYSIS_FEATURES_RECORD(...)`: Constructs a `RawAnalysisFeatures` object.
*   `DERIVE_TRAITS_FROM_...(features, packageID)`: Logic to map low-level features to `ExtractedTraitCandidate` objects.
*   `SAVE_RAW_ANALYSIS_FEATURES_BATCH(featuresList)`: Saves to chosen database (MongoDB).
*   `AGGREGATE_AND_DEDUPLICATE_TRAIT_CANDIDATES(candidatesList)`: Basic deduplication for Phase 1.
*   `SAVE_EXTRACTED_TRAIT_CANDIDATES_BATCH(candidatesList)`: Saves to chosen database (PostgreSQL).
*   `GET_OR_CREATE_USER_NODE_IN_PKG(userID)`: Interacts with the Graph DB.
*   `CREATE_TRAIT_NODE_IN_PKG(...)`: Interacts with the Graph DB.
*   `CREATE_RELATIONSHIP_IN_PKG(...)`: Interacts with the Graph DB.
*   `GET_OR_CREATE_EVIDENCE_NODE_IN_PKG(...)`: Interacts with the Graph DB.
*   `EXTRACT_CONCEPTS_FROM_RAW_FEATURES(...)`: Processes raw features to find concepts.
*   `GET_OR_CREATE_CONCEPT_NODE_IN_PKG(conceptName)`: Interacts with the Graph DB.
*   `SECURELY_DISPOSE_DECRYPTED_DATA(decryptedStream)`: Clears data from memory/temp storage.
*   `UPDATE_USER_DATA_PACKAGE_STATUS(packageID, status)`: Updates status in UDIM's database.
```
