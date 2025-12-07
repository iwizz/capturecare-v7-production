-- Migration: Add company-wide office hours support
-- Description: Adds is_company_wide column to availability_patterns for company office hours

-- Add is_company_wide column to availability_patterns
ALTER TABLE availability_patterns 
ADD COLUMN IF NOT EXISTS is_company_wide BOOLEAN DEFAULT FALSE NOT NULL;

-- Make user_id nullable for company-wide patterns
ALTER TABLE availability_patterns 
ALTER COLUMN user_id DROP NOT NULL;

-- Create index for faster company-wide pattern lookups
CREATE INDEX IF NOT EXISTS idx_availability_patterns_company_wide 
ON availability_patterns(is_company_wide, is_active);

-- Create index for weekday lookups
CREATE INDEX IF NOT EXISTS idx_availability_patterns_weekdays 
ON availability_patterns(weekdays, is_active) 
WHERE is_company_wide = TRUE;

-- Add comment
COMMENT ON COLUMN availability_patterns.is_company_wide IS 'Indicates if this pattern applies to the entire practice (office hours)';
