-- Migration: Add data_source tracking field to worklist_item table
-- Version: 001
-- Date: 2026-01-26
-- Description: Adds optional data_source column for multi-source architecture audit trails

BEGIN TRANSACTION;

-- Add data_source column with NULL default (backward compatible)
ALTER TABLE worklist_items
ADD COLUMN data_source VARCHAR(255) DEFAULT NULL;

-- Optional: Create index if source-based queries become frequent
-- CREATE INDEX idx_worklist_data_source ON worklist_items(data_source);

COMMIT;

-- Rollback script (if needed):
-- BEGIN TRANSACTION;
-- ALTER TABLE worklist_items DROP COLUMN data_source;
-- COMMIT;
