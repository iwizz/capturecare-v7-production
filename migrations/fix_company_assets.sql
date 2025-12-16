-- Fix company_assets table - Add missing columns
-- This script is safe to run multiple times

-- Add file_name column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='company_assets' AND column_name='file_name') THEN
        ALTER TABLE company_assets ADD COLUMN file_name VARCHAR(255);
    END IF;
END $$;

-- Add file_type column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='company_assets' AND column_name='file_type') THEN
        ALTER TABLE company_assets ADD COLUMN file_type VARCHAR(50);
    END IF;
END $$;

-- Add file_size column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='company_assets' AND column_name='file_size') THEN
        ALTER TABLE company_assets ADD COLUMN file_size INTEGER;
    END IF;
END $$;

-- Add link_url column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='company_assets' AND column_name='link_url') THEN
        ALTER TABLE company_assets ADD COLUMN link_url TEXT;
    END IF;
END $$;

-- Add tags column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='company_assets' AND column_name='tags') THEN
        ALTER TABLE company_assets ADD COLUMN tags VARCHAR(500);
    END IF;
END $$;

-- Add is_pinned column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='company_assets' AND column_name='is_pinned') THEN
        ALTER TABLE company_assets ADD COLUMN is_pinned BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Create indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_company_assets_category ON company_assets(category);
CREATE INDEX IF NOT EXISTS idx_company_assets_asset_type ON company_assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_company_assets_is_pinned ON company_assets(is_pinned);
CREATE INDEX IF NOT EXISTS idx_company_assets_created_by ON company_assets(created_by_id);

