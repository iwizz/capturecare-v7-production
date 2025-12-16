-- Add attachment fields to patient_notes table
-- Run this migration to add file attachment support to patient notes

-- Add attachment filename column
ALTER TABLE patient_notes ADD COLUMN IF NOT EXISTS attachment_filename VARCHAR(255);

-- Add attachment path column
ALTER TABLE patient_notes ADD COLUMN IF NOT EXISTS attachment_path VARCHAR(500);

-- Add attachment type column (MIME type)
ALTER TABLE patient_notes ADD COLUMN IF NOT EXISTS attachment_type VARCHAR(50);

-- Add attachment size column (in bytes)
ALTER TABLE patient_notes ADD COLUMN IF NOT EXISTS attachment_size INTEGER;

-- Create index on patient_id for faster queries
CREATE INDEX IF NOT EXISTS idx_patient_notes_patient_id ON patient_notes(patient_id);

-- Create index on attachment columns for filtering
CREATE INDEX IF NOT EXISTS idx_patient_notes_has_attachment ON patient_notes(attachment_filename) WHERE attachment_filename IS NOT NULL;

COMMENT ON COLUMN patient_notes.attachment_filename IS 'Original filename of attached file';
COMMENT ON COLUMN patient_notes.attachment_path IS 'Stored file path (relative to uploads folder)';
COMMENT ON COLUMN patient_notes.attachment_type IS 'MIME type of attachment (e.g., application/pdf, image/jpeg)';
COMMENT ON COLUMN patient_notes.attachment_size IS 'File size in bytes';

