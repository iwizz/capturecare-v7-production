-- Add attachment columns to patient_notes table
-- Run this migration to support file attachments on patient notes

-- Add attachment filename column
ALTER TABLE patient_notes ADD COLUMN IF NOT EXISTS attachment_filename VARCHAR(255);

-- Add attachment path column
ALTER TABLE patient_notes ADD COLUMN IF NOT EXISTS attachment_path VARCHAR(500);

-- Add attachment type column (MIME type)
ALTER TABLE patient_notes ADD COLUMN IF NOT EXISTS attachment_type VARCHAR(50);

-- Add attachment size column (in bytes)
ALTER TABLE patient_notes ADD COLUMN IF NOT EXISTS attachment_size INTEGER;

-- Create index for faster queries on notes with attachments
CREATE INDEX IF NOT EXISTS idx_patient_notes_has_attachment 
ON patient_notes(patient_id, attachment_filename) 
WHERE attachment_filename IS NOT NULL;

-- Verify columns were added
SELECT column_name, data_type, character_maximum_length 
FROM information_schema.columns 
WHERE table_name = 'patient_notes' 
  AND column_name LIKE 'attachment%'
ORDER BY column_name;

