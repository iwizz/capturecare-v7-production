-- Add attachment fields to patient_notes table
-- This migration adds support for file attachments to patient notes

-- Check if columns exist and add them if they don't
DO $$
BEGIN
    -- Add attachment_filename column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'patient_notes' AND column_name = 'attachment_filename'
    ) THEN
        ALTER TABLE patient_notes ADD COLUMN attachment_filename VARCHAR(255);
        RAISE NOTICE 'Added attachment_filename column';
    ELSE
        RAISE NOTICE 'attachment_filename column already exists';
    END IF;

    -- Add attachment_path column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'patient_notes' AND column_name = 'attachment_path'
    ) THEN
        ALTER TABLE patient_notes ADD COLUMN attachment_path VARCHAR(500);
        RAISE NOTICE 'Added attachment_path column';
    ELSE
        RAISE NOTICE 'attachment_path column already exists';
    END IF;

    -- Add attachment_type column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'patient_notes' AND column_name = 'attachment_type'
    ) THEN
        ALTER TABLE patient_notes ADD COLUMN attachment_type VARCHAR(50);
        RAISE NOTICE 'Added attachment_type column';
    ELSE
        RAISE NOTICE 'attachment_type column already exists';
    END IF;

    -- Add attachment_size column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'patient_notes' AND column_name = 'attachment_size'
    ) THEN
        ALTER TABLE patient_notes ADD COLUMN attachment_size INTEGER;
        RAISE NOTICE 'Added attachment_size column';
    ELSE
        RAISE NOTICE 'attachment_size column already exists';
    END IF;
END $$;

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_patient_notes_patient_id ON patient_notes(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_notes_has_attachment ON patient_notes(attachment_filename) WHERE attachment_filename IS NOT NULL;

-- Add comments for documentation
COMMENT ON COLUMN patient_notes.attachment_filename IS 'Original filename of attached file';
COMMENT ON COLUMN patient_notes.attachment_path IS 'Stored file path (relative to uploads folder)';
COMMENT ON COLUMN patient_notes.attachment_type IS 'MIME type of attachment (e.g., application/pdf, image/jpeg)';
COMMENT ON COLUMN patient_notes.attachment_size IS 'File size in bytes';

-- Display success message
DO $$
BEGIN
    RAISE NOTICE '✅ Migration completed successfully!';
    RAISE NOTICE 'Patient notes table now supports file attachments.';
END $$;

