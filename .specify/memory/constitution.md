# Pylantir Constitution
<!-- A Python CLI-based DICOM Modality Worklist Integration Framework -->

## Mission Statement

Pylantir is a Python CLI-based DICOM Modality Worklist (MWL) and Modality Performed Procedure Step (MPPS) integration framework designed to significantly reduce human-related errors in medical imaging procedures by providing automated, reliable data synchronization between REDCap clinical databases and DICOM imaging equipment.

## Core Principles

### I. Minimalist Dependencies
All features must work with the core dependencies only: `pynetdicom`, `pydicom`, `sqlalchemy`, `PyCap` (python-redcap), `uuid`, `coloredlogs`, `python-dotenv`, and `pandas`. New dependencies require explicit approval and must demonstrate significant value. This ensures stable, predictable behavior, easy deployment, and minimal attack surface.

**Rationale**: Healthcare environments require stability and predictability. Minimal dependencies reduce security vulnerabilities and deployment complexity.

### II. CLI-First Design
Every feature must be accessible via CLI commands with clear inputs/outputs. Commands follow the pattern: `pylantir <command> [options]`. Core commands are:
- `start`: Launch MWL/MPPS server with continuous REDCap synchronization
- `query-db`: Query and display worklist database contents
- `test-client`: Validate MWL C-FIND functionality
- `test-mpps`: Test MPPS N-CREATE and N-SET operations

All configuration is done via JSON files and environment variables. No GUI components allowed.

**Rationale**: CLI ensures scriptability, automation compatibility, and consistent behavior across environments.

### III. Healthcare Data Integrity
Data handling must be robust, traceable, and HIPAA-conscious. All database operations must use SQLAlchemy ORM patterns. DICOM dataset conversions must be explicit and validated. REDCap synchronization must be atomic and idempotent with rollback capabilities.

**Integrity Requirements**:
- All patient data transformations must be logged
- Database transactions must be atomic
- Data validation at every integration point
- Audit trails for all status changes

### IV. Test-Driven DICOM Integration
All DICOM service handlers (C-FIND, N-CREATE, N-SET) require comprehensive integration tests with pynetdicom. Tests must verify both success and failure scenarios. Mock DICOM clients/servers required for testing MWL and MPPS services without requiring actual medical equipment.

**Testing Standards**:
- Unit tests for all data transformations
- Integration tests for DICOM services
- End-to-end workflow validation
- Performance testing under load

### V. Operational Observability
Comprehensive logging required for all operations: database sync, DICOM transactions, configuration changes. Log levels must be configurable via environment variables. Critical operations (REDCap sync, MPPS status changes) require audit trails with timestamps and source identification.

**Logging Hierarchy**:
- ERROR: System failures, data corruption
- WARNING: Recoverable issues, configuration problems
- INFO: Normal operations, status changes
- DEBUG: Detailed execution flow (disabled in production)

## Technical Architecture Constraints

### Database Layer
**Primary Database**: SQLite using SQLAlchemy ORM for simplicity and portability
- **Schema Definition**: All models in `models.py` with explicit column types and constraints
- **Connection Management**: Centralized in `db_setup.py` with session handling
- **Query Interface**: SQLAlchemy ORM only - no raw SQL queries permitted
- **Migrations**: Schema changes must include migration scripts
- **Backup Strategy**: Database file backup before major operations

**WorklistItem Model Requirements**:
```python
# Required DICOM attributes (minimum viable dataset)
study_instance_uid, patient_name, patient_id, patient_birth_date,
patient_sex, accession_number, modality, scheduled_start_date,
scheduled_start_time, performed_procedure_step_status
```

### DICOM Services Architecture
**MWL Service Class Provider (SCP)**:
- Implements C-FIND service class for worklist queries
- Supports standard DICOM query/retrieve model
- Dataset matching based on DICOM standard query keys
- Response filtering based on calling AE title restrictions

**MPPS Service Class Provider (SCP)**:
- Implements N-CREATE for procedure step initiation
- Implements N-SET for procedure step updates
- Status tracking: SCHEDULED → IN_PROGRESS → COMPLETED/DISCONTINUED
- Maintains referential integrity between MWL and MPPS instances

**Service Handlers** (all in `mwl_server.py`):
- `handle_find_request()`: C-FIND query processing
- `handle_mpps_create()`: N-CREATE procedure step creation
- `handle_mpps_set()`: N-SET procedure step updates
- `row_to_mwl_dataset()`: Database-to-DICOM dataset conversion

### Integration Layer Architecture
**REDCap Primary Data Source**:
- API-based data extraction using PyCap library
- Configurable field mapping via `redcap2wl` configuration
- Site-specific protocol mapping support
- Incremental sync with change detection

**Synchronization Engine** (`redcap_to_db.py`):
- `sync_redcap_to_db()`: One-time synchronization
- `sync_redcap_to_db_repeatedly()`: Continuous background sync
- Configurable intervals with operation time windows
- Atomic transactions with rollback on failure
- Duplicate detection and handling

**Configuration-Driven Field Mapping**:
```json
{
  "redcap2wl": {
    "study_id": "study_id",
    "mri_instance": "session_id",
    "youth_dob_y": "patient_birth_date",
    "demo_sex": "patient_sex"
  }
}
```

## Development Standards

### Code Organization
**Core Module Structure**:
```
src/pylantir/
├── __init__.py              # Package initialization
├── models.py               # SQLAlchemy database schema
├── db_setup.py             # Database connection & session management
├── mwl_server.py           # DICOM MWL/MPPS service handlers
├── redcap_to_db.py         # REDCap synchronization engine
├── populate_db.py          # Database population utilities
├── cli/
│   ├── __init__.py
│   └── run.py              # CLI command interface & argument parsing
├── api/                    # Future API endpoints (if needed)
└── config/
    └── mwl_config.json     # Default configuration template
```

**Module Responsibilities**:
- `models.py`: WorklistItem ORM model with DICOM-compliant field definitions
- `db_setup.py`: Database engine, session factory, and connection lifecycle
- `mwl_server.py`: DICOM service event handlers and dataset conversions
- `redcap_to_db.py`: REDCap API integration and synchronization logic
- `cli/run.py`: Command-line interface, argument parsing, and workflow orchestration

### Coding Standards
**Type Safety**:
```python
from typing import Dict, List, Optional, Union
from sqlalchemy.orm import Session
from pydicom.dataset import Dataset

def row_to_mwl_dataset(row: WorklistItem) -> Dataset:
    """Convert database row to DICOM dataset with type safety."""
```

**Documentation Requirements**:
- All public functions require docstrings with Args, Returns, Raises
- Module-level docstrings explaining purpose and dependencies
- Inline comments for complex DICOM field mappings
- Configuration examples in docstrings

**Error Handling Patterns**:
```python
class PylantirError(Exception):
    """Base exception for Pylantir operations."""

class DatabaseSyncError(PylantirError):
    """Raised during REDCap synchronization failures."""

class DICOMServiceError(PylantirError):
    """Raised during DICOM service operations."""
```

**Logging Standards**:
```python
import logging
lgr = logging.getLogger(__name__)

# Required logging for all database operations
lgr.info(f"Synced {count} records from REDCap to database")
lgr.warning(f"Missing required field {field} in REDCap record {record_id}")
lgr.error(f"Database sync failed: {error}")
```

### Testing Requirements

**Unit Test Coverage** (minimum 80%):
- **Database Models**: Field validation, ORM relationships, constraints
- **Dataset Conversion**: `row_to_mwl_dataset()` with various input scenarios
- **Configuration Parsing**: JSON validation, default values, error handling
- **Field Mapping**: REDCap to worklist field transformations

**Integration Test Suite**:
- **DICOM Services**: C-FIND, N-CREATE, N-SET with pynetdicom test framework
- **REDCap Synchronization**: Mock API responses, error scenarios, data consistency
- **Database Operations**: Transaction rollback, concurrent access, data integrity
- **End-to-End Workflows**: Complete MWL query and MPPS lifecycle

**Test Infrastructure** (`tests/` directory):
```
tests/
├── conftest.py            # pytest fixtures and test configuration
├── test_methods.py        # Unit tests for core methods
├── client.py              # MWL C-FIND integration test client
├── client2.py             # Alternative test client scenarios
├── mpps_tester.py         # MPPS N-CREATE/N-SET integration tests
└── query_db.py            # Database query validation tests
```

**Performance Testing**:
- Database sync performance with large REDCap datasets (>1000 records)
- DICOM service response time under concurrent connections
- Memory usage during continuous operation
- Network timeout and reconnection handling

## Configuration Management

### Configuration File Structure
**Primary Configuration** (`mwl_config.json`):
```json
{
  "db_path": "~/Desktop/worklist.db",
  "db_echo": "False",
  "db_update_interval": 60,
  "operation_interval": {
    "start_time": [0, 0],
    "end_time": [23, 59]
  },
  "allowed_aet": ["MRI_SCANNER", "CT_SCANNER"],
  "site": "792",
  "protocol": {
    "792": "BRAIN_MRI_3T",
    "mapping": "GEHC"
  },
  "redcap2wl": {
    "study_id": "study_id",
    "instrument": "redcap_repeat_instrument",
    "session_id": "mri_instance",
    "family_id": "family_id",
    "youth_dob_y": "patient_birth_date",
    "demo_sex": "patient_sex",
    "scheduled_date": "mri_date",
    "scheduled_time": "mri_time"
  }
}
```

**Environment Variables** (`.env` file):
```bash
REDCAP_API_URL=https://redcap.institution.edu/api/
REDCAP_API_TOKEN=your_secure_token_here
DB_PATH=/path/to/worklist.db
DB_ECHO=False
DEBUG=False
```

### Version Management

**Semantic Versioning** (`pyproject.toml`):
- **MAJOR.MINOR.PATCH** (currently 0.1.3)
- **MAJOR**: Breaking API changes, CLI interface changes
- **MINOR**: New features, backwards-compatible functionality
- **PATCH**: Bug fixes, documentation updates, dependency updates

**Version Update Triggers**:
- New CLI commands → MINOR version bump
- Configuration schema changes → MINOR version bump
- DICOM service enhancements → MINOR version bump
- Breaking changes to existing interface → MAJOR version bump
- Bug fixes and patches → PATCH version bump

**Documentation Synchronization**:
- `README.md` must be updated with every version release
- Configuration examples must reflect current schema
- CLI help text must match actual implementation
- Test examples must use current version syntax

## Governance Framework

### Change Control Process

**Code Changes Must**:
1. **Maintain CLI Interface**: Backwards compatibility for all existing commands
2. **Pass Integration Tests**: Full test suite must pass before merge
3. **Dependency Approval**: No new dependencies without explicit justification
4. **Logging Integration**: All new operations must include appropriate logging
5. **Documentation Updates**: README.md and docstrings must be updated
6. **Version Bumping**: `pyproject.toml` version must be incremented appropriately

**Configuration Changes Must**:
1. **Backwards Compatibility**: Existing configurations must continue to work
2. **Migration Guide**: Clear upgrade path for configuration changes
3. **Default Values**: Sensible defaults for new configuration options
4. **Validation**: Configuration parsing must validate new fields
5. **Documentation**: README.md must document all configuration options

### Security Requirements

**Credential Management**:
- **No Hardcoded Secrets**: All credentials via environment variables
- **API Token Security**: REDCap tokens stored securely, never logged
- **File Permissions**: Database and configuration files must have appropriate permissions
- **Network Security**: DICOM connections validated, no promiscuous listening

**Data Protection**:
- **PHI Handling**: Patient data must be handled according to HIPAA guidelines
- **Audit Trails**: All data access and modifications must be logged
- **Database Encryption**: Consider encryption for sensitive databases
- **Network Encryption**: Future versions should support TLS for DICOM

### Quality Assurance

**Pre-Release Checklist**:
- [ ] All unit tests pass (minimum 80% coverage)
- [ ] Integration tests validate DICOM services
- [ ] Performance tests confirm acceptable response times
- [ ] Security scan passes (bandit, safety)
- [ ] Documentation is current and accurate
- [ ] Configuration examples work with fresh installation
- [ ] Version number updated in pyproject.toml
- [ ] CHANGELOG.md updated with release notes

**Continuous Integration Requirements**:
- Automated testing on Python 3.8, 3.9, 3.10, 3.11
- Code quality checks (black, flake8, pylint)
- Security scanning (bandit)
- Documentation building verification
- Package building and installation testing

## Future Roadmap Constraints

**Allowed Future Enhancements**:
- Web-based monitoring dashboard (separate package)
- Additional data sources beyond REDCap (with approval)
- Enhanced DICOM service capabilities (Verification, Storage)
- Performance optimizations and caching
- Database migration utilities

**Prohibited Additions**:
- GUI applications or desktop interfaces
- Heavy dependencies (web frameworks, complex libraries)
- Direct integration with imaging equipment beyond DICOM
- Patient data analytics or reporting features
- Authentication systems (use network-level security)

---

**Version**: 2.0.0 | **Ratified**: 2025-11-18 | **Last Amended**: 2025-11-18 | **Next Review**: 2026-05-18
