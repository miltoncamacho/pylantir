# Feature Specification: Modular Data Source Architecture

**Feature Branch**: `001-modular-data-sources`
**Created**: 2026-01-26
**Status**: Draft
**Input**: User description: "Modularize data source architecture to support multiple configurable sources beyond REDCap"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure Single Non-REDCap Data Source (Priority: P1)

A Pylantir administrator wants to use a different data source (e.g., Calpendo scheduling system, CSV files, or custom database) instead of REDCap to populate the worklist database. They need to specify this source in the configuration file and have Pylantir automatically sync from it.

**Why this priority**: This is the foundational capability that enables source modularity. Without this, the system remains locked to REDCap only.

**Independent Test**: Can be fully tested by configuring a new data source (e.g., CSV file source), starting Pylantir, and verifying that worklist entries are populated from that source instead of REDCap.

**Acceptance Scenarios**:

1. **Given** a configuration file specifying a CSV file as the data source, **When** Pylantir starts, **Then** the worklist database is populated with entries from the CSV file
2. **Given** a configuration file specifying a custom database connector, **When** the sync interval elapses, **Then** new entries are fetched from the custom database and added to the worklist
3. **Given** an invalid data source configuration, **When** Pylantir starts, **Then** a clear error message is displayed indicating which configuration parameter is invalid

---

### User Story 2 - Configure Multiple Data Sources Simultaneously (Priority: P2)

A Pylantir administrator managing a multi-site imaging facility wants to aggregate worklist entries from multiple sources simultaneously (e.g., REDCap for Site A, Calpendo for Site B, and a CSV file for Site C). They need to configure all sources in one configuration file and have Pylantir merge entries from all sources.

**Why this priority**: Enables enterprise use cases where different departments or sites use different scheduling systems, all feeding into one unified DICOM worklist.

**Independent Test**: Can be tested by configuring three different data sources (REDCap, CSV, and mock API), starting Pylantir, and verifying that worklist entries from all three sources appear in the database with proper source attribution.

**Acceptance Scenarios**:

1. **Given** a configuration file specifying three different data sources, **When** Pylantir starts, **Then** entries from all three sources are present in the worklist database
2. **Given** multiple data sources with overlapping patient IDs, **When** synchronization occurs, **Then** duplicate detection prevents data conflicts and logs which source was used
3. **Given** one data source fails while others succeed, **When** sync occurs, **Then** successful sources populate the database while failed source is logged without halting the entire sync process

---

### User Story 3 - Create Custom Data Source Plugin (Priority: P3)

A developer wants to create a new data source plugin for their institution's proprietary scheduling system. They need clear documentation and a simple interface to implement, following a standardized pattern that Pylantir can automatically discover and use.

**Why this priority**: Extensibility ensures long-term viability as new scheduling systems emerge. This builds on P1 and P2 capabilities.

**Independent Test**: Can be tested by creating a minimal plugin implementation (10-20 lines of code) following the interface specification, configuring it in the config file, and verifying Pylantir successfully syncs from it.

**Acceptance Scenarios**:

1. **Given** a developer creates a plugin implementing the required base interface, **When** they place it in the designated plugin directory, **Then** Pylantir automatically discovers and registers it as an available data source
2. **Given** a custom plugin with required methods (fetch_entries, validate_config), **When** configured in config file, **Then** Pylantir uses it exactly like built-in sources without code modification
3. **Given** a plugin that raises an exception during fetch, **When** sync occurs, **Then** the error is caught, logged with plugin name and traceback, and other sources continue syncing

---

### Edge Cases

- What happens when a data source is temporarily unavailable (network timeout, API down)?
- How does the system handle schema differences between data sources (different field names, data types)?
- What happens when two data sources provide conflicting data for the same patient ID?
- How does the system behave when a configured data source type doesn't exist or has invalid configuration?
- What happens when a data source returns malformed or incomplete data?
- How are sync intervals handled when multiple sources have different update frequencies?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support configuration of one or more data sources via the JSON configuration file
- **FR-002**: System MUST maintain backward compatibility with existing REDCap-only configurations
- **FR-003**: System MUST provide a base plugin interface/abstract class that all data source plugins implement
- **FR-004**: System MUST automatically discover and register data source plugins placed in a designated directory
- **FR-005**: System MUST sync from all configured data sources concurrently or in parallel when multiple sources are specified
- **FR-006**: System MUST log the source of each worklist entry to enable troubleshooting and audit trails
- **FR-007**: System MUST handle individual data source failures gracefully without stopping other sources from syncing
- **FR-008**: System MUST validate data source configurations at startup and report clear errors for invalid configurations
- **FR-009**: System MUST support per-source sync intervals and operation windows
- **FR-010**: System MUST provide built-in plugins for common sources: REDCap, CSV files, and JSON files
- **FR-011**: System MUST document the required interface for creating custom data source plugins
- **FR-012**: System MUST prevent duplicate worklist entries when multiple sources provide the same patient data
- **FR-013**: System MUST map data source fields to worklist database fields using configurable field mappings per source
- **FR-014**: System MUST maintain memory efficiency when syncing from multiple sources (follow existing memory optimization patterns)
- **FR-015**: System MUST support clean shutdown of all data source sync threads when Pylantir stops

### Key Entities

- **DataSource**: Represents a configured data source with type, configuration parameters, field mapping, sync interval, and operation window. Each source is independent and can be enabled/disabled.
- **DataSourcePlugin**: An abstract interface/class defining the contract for data source implementations. Includes methods for: validate_config(), fetch_entries(), get_source_name(), supports_incremental_sync().
- **SourcedWorklistEntry**: Extension of existing WorklistItem that tracks which data source populated each entry, enabling audit trails and conflict resolution.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Pylantir administrators can configure a non-REDCap data source and successfully sync worklist entries in under 5 minutes of configuration work
- **SC-002**: System successfully syncs from three concurrent data sources without data loss or corruption
- **SC-003**: Developers can create and deploy a custom data source plugin with fewer than 50 lines of code following the documented interface
- **SC-004**: System maintains existing memory efficiency metrics (50-100x improvement from pandas removal) when syncing multiple sources
- **SC-005**: When one of three configured data sources fails, the other two continue syncing with 100% success rate
- **SC-006**: Configuration errors are detected within 2 seconds of startup with error messages that precisely identify the problematic parameter
- **SC-007**: Existing REDCap-only configurations continue working without modification (zero breaking changes)

## Scope & Boundaries

### In Scope

- Creating abstract base class for data source plugins
- Refactoring existing REDCap sync into a plugin implementation
- Building plugin discovery and registration mechanism
- Implementing CSV and JSON file data source plugins
- Adding multi-source configuration support to config file schema
- Creating concurrent/parallel sync orchestration
- Adding source tracking to database entries
- Documenting plugin development guide

### Out of Scope

- GUI-based data source configuration (CLI and config file only, per Pylantir Constitution)
- Real-time sync (scheduled/interval-based only)
- Data transformation engine beyond simple field mapping
- Built-in plugins for commercial systems beyond REDCap (users create custom plugins)
- Database schema migration tooling (simple additive changes only)
- Conflict resolution UI (automatic resolution with logging only)

## Assumptions

- Data sources will provide tabular data that can be mapped to worklist fields (structured data assumption)
- Network connectivity for remote data sources is handled at infrastructure level (no retry logic required initially)
- Field mapping per source follows the same pattern as existing redcap2wl mapping
- Plugin files will be Python modules (.py files) placed in a designated directory
- Sync intervals are specified in seconds (consistent with current implementation)
- Each data source returns data in list-of-dictionaries format (standardized internal format)
- Database connection pooling and session management follows existing patterns

## Configuration Schema Changes

### Current Configuration (REDCap Only)
```json
{
  "db_update_interval": 60,
  "redcap2wl": {
    "study_id": "study_id",
    "mri_instance": "session_id"
  }
}
```

### Proposed Configuration (Multi-Source)
```json
{
  "data_sources": [
    {
      "name": "site_a_redcap",
      "type": "redcap",
      "enabled": true,
      "sync_interval": 60,
      "operation_interval": {
        "start_time": [0, 0],
        "end_time": [23, 59]
      },
      "config": {
        "api_url_env": "REDCAP_API_URL",
        "api_token_env": "REDCAP_API_TOKEN",
        "site_id": "792",
        "protocol": {"792": "BRAIN_MRI_3T"}
      },
      "field_mapping": {
        "study_id": "study_id",
        "mri_instance": "session_id",
        "youth_dob_y": "patient_birth_date",
        "demo_sex": "patient_sex"
      }
    },
    {
      "name": "site_b_csv",
      "type": "csv",
      "enabled": true,
      "sync_interval": 300,
      "config": {
        "file_path": "/data/worklist_imports/site_b.csv",
        "watch_for_changes": true
      },
      "field_mapping": {
        "patient_id": "patient_id",
        "dob": "patient_birth_date",
        "sex": "patient_sex",
        "scan_date": "scheduled_start_date"
      }
    }
  ],

  "legacy_mode": false
}
```

### Backward Compatibility
If `data_sources` key is not present but legacy `redcap2wl` exists, automatically convert to single REDCap source configuration.

## Plugin Interface Specification

### Required Abstract Base Class
```python
class DataSourcePlugin(ABC):
    """Base class for all data source plugins."""

    @abstractmethod
    def validate_config(self, config: dict) -> tuple[bool, str]:
        """Validate source-specific configuration.
        Returns: (is_valid, error_message)
        """
        pass

    @abstractmethod
    def fetch_entries(self, field_mapping: dict, interval: float) -> list[dict]:
        """Fetch entries from data source.
        Returns: List of dictionaries with mapped fields.
        """
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Return human-readable source type name."""
        pass

    def supports_incremental_sync(self) -> bool:
        """Whether source supports fetching only changed records."""
        return False

    def cleanup(self) -> None:
        """Optional cleanup method called on shutdown."""
        pass
```

## Dependencies & Constraints

### Technical Dependencies
- No new external dependencies for core plugin system
- CSV plugin: Use Python stdlib `csv` module
- JSON plugin: Use Python stdlib `json` module
- REDCap plugin: Existing `redcap` (PyCap) dependency

### Pylantir Constitution Compliance
- **Minimalist Dependencies**: Plugin system uses only stdlib, no new dependencies (✓)
- **CLI-First Design**: All configuration via JSON file, no GUI (✓)
- **Healthcare Data Integrity**: Source tracking adds audit trail, maintains atomic transactions (✓)
- **Test-Driven DICOM Integration**: Requires unit tests for plugin system and integration tests for multi-source sync (✓)
- **Operational Observability**: Source tracking and per-source logging enhance observability (✓)

## Open Questions

None at this time. All design decisions have reasonable defaults based on existing architecture and industry standards.

## Related Documentation

- [Pylantir Constitution](/.specify/memory/constitution.md) - Architecture constraints and principles
- [redcap_to_db.py](/src/pylantir/redcap_to_db.py) - Current REDCap sync implementation to be refactored
- [run.py](/src/pylantir/cli/run.py) - CLI entry point where multi-source orchestration will be added
- [models.py](/src/pylantir/models.py) - Database schema that may need source tracking field addition
