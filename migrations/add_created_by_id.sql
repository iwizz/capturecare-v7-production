-- Migration: Add created_by_id field to appointments table
-- Date: 2025-12-05
-- Purpose: Track which user created each appointment

-- Add the created_by_id column
ALTER TABLE appointments 
ADD COLUMN IF NOT EXISTS created_by_id INTEGER;

-- Add foreign key constraint
ALTER TABLE appointments
ADD CONSTRAINT fk_appointments_created_by
FOREIGN KEY (created_by_id) REFERENCES users(id)
ON DELETE SET NULL;

-- Optional: Set existing appointments to be created by first admin user
-- You can customize this logic based on your needs
UPDATE appointments 
SET created_by_id = (
    SELECT id FROM users 
    WHERE is_admin = true 
    ORDER BY created_at ASC 
    LIMIT 1
)
WHERE created_by_id IS NULL;

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_appointments_created_by_id 
ON appointments(created_by_id);

-- Verify the migration
SELECT 
    COUNT(*) as total_appointments,
    COUNT(created_by_id) as appointments_with_creator,
    COUNT(*) - COUNT(created_by_id) as appointments_without_creator
FROM appointments;

