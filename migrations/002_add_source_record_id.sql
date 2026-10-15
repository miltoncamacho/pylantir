-- Add stable upstream record identity to existing Pylantir databases.
-- Stop Pylantir and back up the database before running this migration.
BEGIN IMMEDIATE;

ALTER TABLE worklist_items
ADD COLUMN source_record_id VARCHAR(255) DEFAULT NULL;

CREATE UNIQUE INDEX uq_worklist_source_record
ON worklist_items(data_source, source_record_id)
WHERE source_record_id IS NOT NULL;

COMMIT;
