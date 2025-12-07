-- Add created_by_id column to appointments table for production
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS created_by_id INTEGER;
