# Stable source record IDs

Pylantir stores each upstream record's immutable identifier in
`worklist_items.source_record_id`. Together, `data_source` and
`source_record_id` identify one worklist row. For Calpendo,
`source_record_id` is the Calpendo booking ID.

This means correcting a patient ID, patient name, time, status, or other
booking field updates the existing worklist row instead of creating a second
row. Different configured sources may use the same upstream ID because the ID
is scoped by the configured `data_sources[].name`.

## Migrating an existing SQLite database

1. Stop Pylantir. The application must not write to the database during the
   migration.
2. Identify the database path from `db_path` in the active configuration.
3. Run the migration with a backup:

   ```bash
   python3 scripts/migrate_add_source_record_id.py \
     --db-path /path/to/worklist.db \
     --backup
   ```

4. If the Calpendo field mapping historically copied booking `id` into
   `accession_number`, backfill existing rows by passing the configured source
   name. Older versions normally stored the plugin label `Calpendo`; map that
   label to the exact configured `data_sources[].name`:

   ```bash
   python3 scripts/migrate_add_source_record_id.py \
     --db-path /path/to/worklist.db \
     --backup \
     --backfill-source Calpendo=calpendo_main
   ```

   A single name such as `--backfill-source calpendo_main` means the stored and
   configured names are already identical. Repeat the option for additional
   Calpendo sources. Do not use it if `accession_number` was not the Calpendo
   booking ID. If multiple configured Calpendo sources were historically all
   stored simply as `Calpendo`, inspect and update those rows manually because
   the old database does not contain enough information to separate them.

5. Verify the schema and identities:

   ```sql
   PRAGMA table_info(worklist_items);
   SELECT id, data_source, source_record_id, accession_number, patient_id
   FROM worklist_items
   WHERE data_source = 'calpendo_main';
   ```

6. Remove any already-created stale duplicate rows after reviewing them, then
   restart Pylantir. The migration deliberately does not guess which duplicate
   is correct.

The script is safe to rerun. It adds a partial unique index over
`(data_source, source_record_id)` and rolls back if a requested backfill would
create duplicate identities. New databases receive the column and uniqueness
constraint automatically from the SQLAlchemy model.

## Important transition behavior

Rows not backfilled have a NULL `source_record_id`. If their patient ID and
name are still unchanged, the next sync finds them using the legacy match and
attaches the booking ID automatically. If those fields were already corrected
in Calpendo, Pylantir cannot reliably associate the old row; manually populate
its `source_record_id` or remove the stale row before syncing.
