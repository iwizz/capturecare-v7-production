-- Fix company_assets file_type column to accommodate longer MIME types
-- Some MIME types like Word documents can be very long

-- For PostgreSQL
ALTER TABLE company_assets ALTER COLUMN file_type TYPE VARCHAR(200);

-- Note: This migration is safe to run and will automatically run on startup

