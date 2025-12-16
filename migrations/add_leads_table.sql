-- Add leads table for lead management
-- This table tracks potential patients before they are converted

CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL,
    mobile VARCHAR(20),
    source VARCHAR(100),
    status VARCHAR(50) DEFAULT 'new',
    
    -- Form tracking
    form_sent_at TIMESTAMP,
    form_sent_via VARCHAR(20),
    form_completed_at TIMESTAMP,
    form_url TEXT,
    
    -- Conversion tracking
    converted_to_patient_id INTEGER REFERENCES patients(id),
    converted_at TIMESTAMP,
    
    -- Notes and history
    notes TEXT,
    notes_history TEXT,
    
    -- Audit fields
    created_by_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_created_by ON leads(created_by_id);
CREATE INDEX IF NOT EXISTS idx_leads_converted_to ON leads(converted_to_patient_id);
CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at);

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_leads_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_leads_updated_at ON leads;
CREATE TRIGGER trigger_leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW
    EXECUTE FUNCTION update_leads_updated_at();

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON leads TO Cap01;
GRANT USAGE, SELECT ON SEQUENCE leads_id_seq TO Cap01;

