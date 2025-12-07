-- Fix: Reset all sequences to match the current max IDs in tables
-- This fixes the "duplicate key value" error when inserting new records

-- Fix availability_patterns sequence
SELECT setval('availability_patterns_id_seq', COALESCE((SELECT MAX(id) FROM availability_patterns), 0) + 1, false);

-- Fix availability_exceptions sequence (preventive)
SELECT setval('availability_exceptions_id_seq', COALESCE((SELECT MAX(id) FROM availability_exceptions), 0) + 1, false);

-- Fix appointments sequence (preventive)
SELECT setval('appointments_id_seq', COALESCE((SELECT MAX(id) FROM appointments), 0) + 1, false);

-- Fix patients sequence (preventive)
SELECT setval('patients_id_seq', COALESCE((SELECT MAX(id) FROM patients), 0) + 1, false);

-- Fix users sequence (preventive)
SELECT setval('users_id_seq', COALESCE((SELECT MAX(id) FROM users), 0) + 1, false);

-- Verify sequences are now correct
SELECT 'availability_patterns', last_value FROM availability_patterns_id_seq;
SELECT 'availability_exceptions', last_value FROM availability_exceptions_id_seq;
SELECT 'appointments', last_value FROM appointments_id_seq;
SELECT 'patients', last_value FROM patients_id_seq;
SELECT 'users', last_value FROM users_id_seq;
