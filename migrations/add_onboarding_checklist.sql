-- Migration: Add onboarding checklist table
-- Purpose: Track nurse onboarding checklist completion for patients
-- Date: 2025-12-08

CREATE TABLE IF NOT EXISTS onboarding_checklists (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL UNIQUE REFERENCES patients(id) ON DELETE CASCADE,
    completed_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    
    -- Section 1: Introductions & Background
    intro_nurse BOOLEAN DEFAULT FALSE,
    intro_name BOOLEAN DEFAULT FALSE,
    intro_enrollment_reason BOOLEAN DEFAULT FALSE,
    intro_device_experience BOOLEAN DEFAULT FALSE,
    intro_session_explanation BOOLEAN DEFAULT FALSE,
    intro_enrollment_details BOOLEAN DEFAULT FALSE,
    
    -- Section 2: Introduce the CaptureCare PRPM Program
    program_explained BOOLEAN DEFAULT FALSE,
    sessions_booked BOOLEAN DEFAULT FALSE,
    
    -- Section 3: Device & App Setup Confirmation
    device_charging BOOLEAN DEFAULT FALSE,
    app_downloaded BOOLEAN DEFAULT FALSE,
    devices_paired BOOLEAN DEFAULT FALSE,
    troubleshooting BOOLEAN DEFAULT FALSE,
    
    -- Section 4: App Navigation & Features
    nav_dashboard BOOLEAN DEFAULT FALSE,
    nav_timeline BOOLEAN DEFAULT FALSE,
    nav_devices BOOLEAN DEFAULT FALSE,
    premium_explained BOOLEAN DEFAULT FALSE,
    health_goal_set BOOLEAN DEFAULT FALSE,
    help_center_shown BOOLEAN DEFAULT FALSE,
    
    -- Section 5: Downloading & Sharing Data
    export_csv BOOLEAN DEFAULT FALSE,
    generate_report BOOLEAN DEFAULT FALSE,
    invite_family BOOLEAN DEFAULT FALSE,
    
    -- Section 6: Explain Key Health Metrics
    metrics_body_comp BOOLEAN DEFAULT FALSE,
    metrics_heart BOOLEAN DEFAULT FALSE,
    metrics_nerve BOOLEAN DEFAULT FALSE,
    metrics_sleep BOOLEAN DEFAULT FALSE,
    
    -- Section 7: Goal Setting & Medical History
    smart_goals BOOLEAN DEFAULT FALSE,
    medical_history BOOLEAN DEFAULT FALSE,
    health_concerns BOOLEAN DEFAULT FALSE,
    
    -- Section 8: Final Admin
    pre_trial_survey BOOLEAN DEFAULT FALSE,
    patient_confident BOOLEAN DEFAULT FALSE,
    questions_answered BOOLEAN DEFAULT FALSE,
    next_session_confirmed BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Notes
    notes TEXT
);

-- Create index on patient_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_onboarding_checklists_patient_id ON onboarding_checklists(patient_id);
CREATE INDEX IF NOT EXISTS idx_onboarding_checklists_completed_by ON onboarding_checklists(completed_by_id);

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_onboarding_checklist_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_onboarding_checklist_updated_at
    BEFORE UPDATE ON onboarding_checklists
    FOR EACH ROW
    EXECUTE FUNCTION update_onboarding_checklist_updated_at();
