-- Add show_in_patient_app column to target_ranges table
-- Run this against your Cloud SQL database

-- Check if column exists, if not add it
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'target_ranges' 
        AND column_name = 'show_in_patient_app'
    ) THEN
        ALTER TABLE target_ranges 
        ADD COLUMN show_in_patient_app BOOLEAN DEFAULT TRUE;
        
        -- Set all existing rows to True
        UPDATE target_ranges 
        SET show_in_patient_app = TRUE 
        WHERE show_in_patient_app IS NULL;
    END IF;
END $$;

