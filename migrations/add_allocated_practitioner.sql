-- Add allocated_practitioner_id to patients table
-- This field stores the primary/default practitioner for each patient

ALTER TABLE patients 
ADD COLUMN allocated_practitioner_id INTEGER REFERENCES users(id);

-- Create index for better query performance
CREATE INDEX idx_patients_allocated_practitioner 
ON patients(allocated_practitioner_id);

-- Optional: Set a default allocated practitioner for existing patients with appointments
-- (Assign the practitioner they have the most appointments with)
UPDATE patients p
SET allocated_practitioner_id = (
    SELECT a.practitioner_id
    FROM appointments a
    WHERE a.patient_id = p.id 
      AND a.practitioner_id IS NOT NULL
    GROUP BY a.practitioner_id
    ORDER BY COUNT(*) DESC
    LIMIT 1
)
WHERE allocated_practitioner_id IS NULL
  AND EXISTS (
    SELECT 1 FROM appointments 
    WHERE patient_id = p.id 
      AND practitioner_id IS NOT NULL
  );

