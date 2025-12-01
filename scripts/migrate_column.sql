-- Migration: Add show_in_patient_app column to target_ranges
ALTER TABLE target_ranges 
ADD COLUMN IF NOT EXISTS show_in_patient_app BOOLEAN DEFAULT TRUE;

UPDATE target_ranges 
SET show_in_patient_app = TRUE 
WHERE show_in_patient_app IS NULL;

