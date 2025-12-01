-- Database performance optimization: Add indexes for common queries
-- Run this on Cloud SQL to improve query performance

-- Health data indexes (most queried table)
CREATE INDEX IF NOT EXISTS idx_health_data_patient_timestamp 
ON health_data(patient_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_health_data_measurement_type 
ON health_data(measurement_type);

CREATE INDEX IF NOT EXISTS idx_health_data_patient_type_timestamp 
ON health_data(patient_id, measurement_type, timestamp DESC);

-- Target ranges indexes
CREATE INDEX IF NOT EXISTS idx_target_ranges_patient_measurement 
ON target_ranges(patient_id, measurement_type);

CREATE INDEX IF NOT EXISTS idx_target_ranges_show_in_app 
ON target_ranges(show_in_patient_app) 
WHERE show_in_patient_app = TRUE;

-- Patient auth indexes (if table exists)
CREATE INDEX IF NOT EXISTS idx_patient_auth_patient_id 
ON patient_auth(patient_id);

CREATE INDEX IF NOT EXISTS idx_patient_auth_email 
ON patient_auth(email);

-- Appointments indexes
CREATE INDEX IF NOT EXISTS idx_appointments_patient_date 
ON appointments(patient_id, start_time DESC);

-- Device indexes
CREATE INDEX IF NOT EXISTS idx_devices_patient_id 
ON devices(patient_id);

