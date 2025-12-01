-- Direct SQL migration for show_in_patient_app column
-- Run this via: gcloud sql connect capturecare-db --user=capturecare --database=capturecare

-- Check and add column if it doesn't exist
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
        
        UPDATE target_ranges 
        SET show_in_patient_app = TRUE 
        WHERE show_in_patient_app IS NULL;
        
        RAISE NOTICE 'Column show_in_patient_app added successfully';
    ELSE
        RAISE NOTICE 'Column show_in_patient_app already exists';
    END IF;
END $$;

