# Pylantir Constitution
<!-- A Python CLI-based DICOM Modality Worklist Integration Framework -->

## Core Principles

### I. Minimalist Dependencies
All features must work with the core dependencies only: pynetdicom, pydicom, sqlalchemy, and python-redcap. New dependencies require explicit approval and must demonstrate significant value. This ensures stable, predictable behavior and easy deployment.

### II. CLI-First Design
Every feature must be accessible via CLI commands with clear inputs/outputs. Commands follow the pattern: `pylantir <command> [options]`. Core commands are: start, query-db, test-client, and test-mpps. All configuration is done via JSON files and environment variables.

### III. Healthcare Data Integrity
Data handling must be robust and traceable. All database operations must use SQLAlchemy ORM patterns. DICOM dataset conversions must be explicit and validated. REDCap synchronization must be atomic and idempotent.

### IV. Test-Driven DICOM Integration
All DICOM service handlers (C-FIND, N-CREATE, N-SET) require integration tests with pynetdicom. Tests must verify both success and failure scenarios. Mock DICOM clients/servers required for testing MWL and MPPS services.

### V. Operational Observability
Comprehensive logging required for all operations: database sync, DICOM transactions, configuration changes. Log levels must be configurable. Critical operations (REDCap sync, MPPS status changes) require audit trails.

## Technical Architecture Constraints

### Database Layer
- SQLite as primary database using SQLAlchemy ORM
- Models defined in models.py with explicit column types
- Database operations centralized in db_setup.py
- No direct SQL queries; use SQLAlchemy query interface

### DICOM Services
- MWL SCP implements C-FIND service class
- MPPS SCP implements N-CREATE and N-SET
- All DICOM handlers in mwl_server.py
- Dataset conversion in row_to_mwl_dataset function

### Integration Layer
- REDCap as primary data source
- Configurable sync intervals
- Atomic transaction handling
- Field mapping in configuration

## Development Standards

### Code Organization
1. Core modules:
   - models.py: Database schema
   - db_setup.py: Database connection
   - mwl_server.py: DICOM services
   - redcap_to_db.py: Integration logic
   - cli/run.py: Command interface

2. Required patterns:
   - Type hints for function parameters
   - Docstrings for all public functions
   - Logging for operational visibility
   - Error handling with specific exceptions

### Testing Requirements
1. Unit tests for:
   - Database models
   - Dataset conversion
   - Configuration parsing

2. Integration tests for:
   - DICOM services
   - REDCap synchronization
   - Database operations

## Governance

1. Code changes must:
   - Maintain existing CLI interface
   - Pass all integration tests
   - Not introduce new dependencies
   - Include appropriate logging
   - Update documentation

2. Configuration changes must:
   - Be backwards compatible
   - Include migration guide
   - Be documented in README

3. Security considerations:
   - No hardcoded credentials
   - Environment variables for secrets
   - Validate all DICOM connections

**Version**: 1.0.0 | **Ratified**: 2025-10-31 | **Last Amended**: 2025-10-31
