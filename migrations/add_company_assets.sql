-- Migration: Add company_assets table
-- Purpose: Store company-wide resources, documents, and links
-- Date: 2025-12-16

-- Create company_assets table
CREATE TABLE IF NOT EXISTS company_assets (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    asset_type VARCHAR(50) NOT NULL,  -- 'file', 'link', 'document'
    category VARCHAR(100),  -- 'forms', 'policies', 'training', 'resources', etc.
    
    -- For uploaded files
    file_path VARCHAR(500),
    file_name VARCHAR(255),
    file_type VARCHAR(50),
    file_size INTEGER,
    
    -- For links
    link_url TEXT,
    
    -- Metadata
    tags VARCHAR(500),
    is_pinned BOOLEAN DEFAULT FALSE,
    
    -- Audit fields
    created_by_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_company_assets_category ON company_assets(category);
CREATE INDEX IF NOT EXISTS idx_company_assets_asset_type ON company_assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_company_assets_is_pinned ON company_assets(is_pinned);
CREATE INDEX IF NOT EXISTS idx_company_assets_created_by ON company_assets(created_by_id);

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION update_company_assets_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_company_assets_timestamp ON company_assets;
CREATE TRIGGER update_company_assets_timestamp
    BEFORE UPDATE ON company_assets
    FOR EACH ROW
    EXECUTE FUNCTION update_company_assets_updated_at();

