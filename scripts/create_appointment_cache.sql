-- Create a materialized view/cache table for appointments indexed by date
-- This will dramatically speed up calendar queries

-- Create the cache table
CREATE TABLE IF NOT EXISTS appointment_date_cache (
    id SERIAL PRIMARY KEY,
    appointment_id INTEGER NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    patient_id INTEGER NOT NULL,
    practitioner_id INTEGER,
    status VARCHAR(50) DEFAULT 'scheduled',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(appointment_id, date)
);

-- Create indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_appointment_cache_date ON appointment_date_cache(date);
CREATE INDEX IF NOT EXISTS idx_appointment_cache_practitioner ON appointment_date_cache(practitioner_id);
CREATE INDEX IF NOT EXISTS idx_appointment_cache_patient ON appointment_date_cache(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointment_cache_status ON appointment_date_cache(status);
CREATE INDEX IF NOT EXISTS idx_appointment_cache_date_range ON appointment_date_cache(date, start_time, end_time);

-- Create function to populate cache for a date range
CREATE OR REPLACE FUNCTION refresh_appointment_cache(start_date DATE, end_date DATE)
RETURNS void AS $$
BEGIN
    -- Delete existing entries in range
    DELETE FROM appointment_date_cache 
    WHERE date >= start_date AND date <= end_date;
    
    -- Insert appointments that fall in this date range
    INSERT INTO appointment_date_cache (
        appointment_id, date, start_time, end_time, 
        patient_id, practitioner_id, status
    )
    SELECT 
        a.id,
        DATE(a.start_time) as date,
        a.start_time,
        a.end_time,
        a.patient_id,
        a.practitioner_id,
        a.status
    FROM appointments a
    WHERE DATE(a.start_time) >= start_date 
      AND DATE(a.start_time) <= end_date
      AND a.status != 'cancelled'
    ON CONFLICT (appointment_id, date) DO UPDATE SET
        start_time = EXCLUDED.start_time,
        end_time = EXCLUDED.end_time,
        status = EXCLUDED.status;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update cache when appointments change
CREATE OR REPLACE FUNCTION update_appointment_cache()
RETURNS TRIGGER AS $$
BEGIN
    -- Delete old cache entries for this appointment
    DELETE FROM appointment_date_cache WHERE appointment_id = COALESCE(OLD.id, NEW.id);
    
    -- Insert new cache entry if appointment is active
    IF NEW.status != 'cancelled' THEN
        INSERT INTO appointment_date_cache (
            appointment_id, date, start_time, end_time,
            patient_id, practitioner_id, status
        )
        VALUES (
            NEW.id,
            DATE(NEW.start_time),
            NEW.start_time,
            NEW.end_time,
            NEW.patient_id,
            NEW.practitioner_id,
            NEW.status
        )
        ON CONFLICT (appointment_id, date) DO UPDATE SET
            start_time = EXCLUDED.start_time,
            end_time = EXCLUDED.end_time,
            status = EXCLUDED.status;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers
DROP TRIGGER IF EXISTS trigger_appointment_cache_insert ON appointments;
CREATE TRIGGER trigger_appointment_cache_insert
    AFTER INSERT ON appointments
    FOR EACH ROW
    EXECUTE FUNCTION update_appointment_cache();

DROP TRIGGER IF EXISTS trigger_appointment_cache_update ON appointments;
CREATE TRIGGER trigger_appointment_cache_update
    AFTER UPDATE ON appointments
    FOR EACH ROW
    EXECUTE FUNCTION update_appointment_cache();

DROP TRIGGER IF EXISTS trigger_appointment_cache_delete ON appointments;
CREATE TRIGGER trigger_appointment_cache_delete
    AFTER DELETE ON appointments
    FOR EACH ROW
    EXECUTE FUNCTION update_appointment_cache();

-- Initial population for current and next 3 months
SELECT refresh_appointment_cache(
    CURRENT_DATE - INTERVAL '1 month',
    CURRENT_DATE + INTERVAL '3 months'
);

