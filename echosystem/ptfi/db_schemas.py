# echosystem/ptfi/db_schemas.py

# Conceptual DDL for the table that logs user refinement actions.
# This table would store instances of UserRefinedTraitActionModel.
# Actual FK constraints to 'users' table or 'extracted_trait_candidates' table (from MAIPP's DB potentially)
# would depend on the broader database architecture and whether these tables are in the same DB instance.
# For this example, user_id and original_candidate_id are marked as UUIDs that would conceptually link.
# trait_id_in_pkg links to the canonical Trait ID in the Persona Knowledge Graph (PKG), which might not be a direct FK.

USER_REFINED_TRAIT_ACTIONS_TABLE_DDL = """
-- Helps ensure consistency for user_decision values
CREATE TYPE trait_user_decision_enum AS ENUM (
    'confirmed_asis',
    'confirmed_modified',
    'rejected',
    'user_added_confirmed',
    'superseded' -- If a trait refinement is later updated/overridden
);

-- Helps ensure consistency for trait_category values
-- This should align with the categories used in ExtractedTraitCandidateModel and PKG Trait nodes
CREATE TYPE trait_category_enum AS ENUM (
    'LinguisticStyle',
    'EmotionalResponsePattern',
    'KnowledgeDomain',
    'PhilosophicalStance',
    'CommunicationStyle',
    'BehavioralPattern',
    'Interest',
    'Skill',
    'Other'
);

CREATE TABLE IF NOT EXISTS user_refined_trait_actions (
    refinement_action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL, -- Conceptually FK to a User table
    trait_id_in_pkg UUID NOT NULL, -- Identifier of the Trait node in the PKG
    original_candidate_id UUID NULL, -- Conceptually FK to MAIPP's ExtractedTraitCandidate table

    user_decision trait_user_decision_enum NOT NULL,

    refined_trait_name VARCHAR(255) NULL,
    refined_trait_description TEXT NULL,
    refined_trait_category trait_category_enum NULL, -- Using ENUM type

    user_confidence_rating INTEGER NULL CHECK (user_confidence_rating >= 1 AND user_confidence_rating <= 5),
    customization_notes TEXT NULL,
    linked_evidence_override JSONB NULL, -- Stores an array of EvidenceSnippet Pydantic models as JSON

    action_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Example conceptual foreign key (if tables are in the same DB and appropriately set up)
    -- CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id),
    -- CONSTRAINT fk_original_candidate FOREIGN KEY (original_candidate_id) REFERENCES extracted_trait_candidates(candidate_id)
    CONSTRAINT check_modification_details CHECK (
        (user_decision = 'confirmed_modified' AND refined_trait_name IS NOT NULL) OR
        (user_decision = 'user_added_confirmed' AND refined_trait_name IS NOT NULL AND refined_trait_category IS NOT NULL) OR
        (user_decision NOT IN ('confirmed_modified', 'user_added_confirmed'))
        -- This check can be more elaborate based on which fields are mandatory for which decision.
        -- For 'confirmed_asis' or 'rejected', refined_ fields might be NULL.
    )
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_urta_user_id ON user_refined_trait_actions(user_id);
CREATE INDEX IF NOT EXISTS idx_urta_trait_id_in_pkg ON user_refined_trait_actions(trait_id_in_pkg);
CREATE INDEX IF NOT EXISTS idx_urta_original_candidate_id ON user_refined_trait_actions(original_candidate_id);
CREATE INDEX IF NOT EXISTS idx_urta_user_decision ON user_refined_trait_actions(user_decision);
CREATE INDEX IF NOT EXISTS idx_urta_action_timestamp ON user_refined_trait_actions(action_timestamp DESC);

COMMENT ON TABLE user_refined_trait_actions IS 'Logs user actions related to refining, confirming, rejecting, or adding persona traits.';
COMMENT ON COLUMN user_refined_trait_actions.trait_id_in_pkg IS 'The canonical ID of the Trait in the Persona Knowledge Graph that this action pertains to.';
COMMENT ON COLUMN user_refined_trait_actions.original_candidate_id IS 'If applicable, the ID of the AI-generated ExtractedTraitCandidate this action is based on.';
COMMENT ON COLUMN user_refined_trait_actions.user_decision IS 'The specific decision made by the user regarding the trait.';
COMMENT ON COLUMN user_refined_trait_actions.linked_evidence_override IS 'JSONB array of EvidenceSnippet objects, representing user-curated evidence.';
"""

# Note: The ENUM types trait_user_decision_enum and trait_category_enum
# should be created once in the database. The CREATE TABLE DDL assumes they exist or creates them.
# If managing with a migration tool like Alembic, ENUM creation is handled differently.
```
