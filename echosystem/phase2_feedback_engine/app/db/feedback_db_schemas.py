# echosystem/phase2_feedback_engine/app/db/feedback_db_schemas.py
# Conceptual DDL for feedback_events table (PostgreSQL)
FEEDBACK_EVENTS_TABLE_DDL = """
CREATE TYPE feedback_type_enum AS ENUM (
    'rating_positive',
    'rating_negative',
    'correction_text',
    'style_too_formal',
    'style_too_casual',
    'style_tone_off',
    'factual_error',
    'custom_feedback'
);

CREATE TYPE feedback_processing_status_enum AS ENUM (
    'pending',
    'processed',
    'error'
);

CREATE TABLE IF NOT EXISTS feedback_events (
    feedback_event_id UUID PRIMARY KEY,
    persona_id UUID NOT NULL,
    interaction_id UUID NOT NULL,
    output_id UUID NULL,

    feedback_type feedback_type_enum NOT NULL,
    user_provided_text TEXT NULL,
    user_rating_value INTEGER NULL CHECK (user_rating_value >= 1 AND user_rating_value <= 5),
    feedback_context JSONB NULL,

    received_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processing_status feedback_processing_status_enum NOT NULL DEFAULT 'pending',
    processed_timestamp TIMESTAMPTZ NULL, -- Added for tracking when it's processed
    error_message TEXT NULL
    -- Optional: FOREIGN KEY (persona_id) REFERENCES personas_table(persona_id)
    -- Optional: Consider indexing on persona_id, feedback_type, processing_status, received_timestamp
);

CREATE INDEX IF NOT EXISTS idx_feedback_events_persona_id ON feedback_events(persona_id);
CREATE INDEX IF NOT EXISTS idx_feedback_events_type ON feedback_events(feedback_type);
CREATE INDEX IF NOT EXISTS idx_feedback_events_status ON feedback_events(processing_status);
CREATE INDEX IF NOT EXISTS idx_feedback_events_received_ts ON feedback_events(received_timestamp);

-- Note: Running this DDL multiple times might result in errors if types already exist.
-- In a migration tool, you'd use `CREATE TYPE IF NOT EXISTS ...` or handle this more robustly.
-- For PostgreSQL, `CREATE TYPE ... AS ENUM` does not support `IF NOT EXISTS` directly.
-- You might need to check for type existence in a DO block or use a migration framework.
"""
