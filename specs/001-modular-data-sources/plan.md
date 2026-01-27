# Implementation Plan: Modular Data Source Architecture

**Branch**: `001-modular-data-sources` | **Date**: 2026-01-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-modular-data-sources/spec.md`

## Summary

Refactor the existing REDCap synchronization code into a plugin-based architecture that allows multiple data sources to populate the DICOM worklist database. **Phase 1 scope**: Establish the plugin interface and refactor REDCap as the first plugin implementation, enabling future data sources without code changes. All sources will populate the same SQLite database using the existing `WorklistItem` model.

**Key Design Principle**: Extract the REDCap-specific logic from `redcap_to_db.py` into a reusable plugin pattern while maintaining 100% backward compatibility with existing configurations.

## Technical Context

**Language/Version**: Python 3.8+ (existing Pylantir constraint)
**Primary Dependencies**: `pynetdicom`, `pydicom`, `sqlalchemy`, `PyCap`, `uuid`, `coloredlogs`, `python-dotenv`, `pandas` (existing only - NO new dependencies)
**Storage**: SQLite using SQLAlchemy ORM (existing `models.WorklistItem`)
**Testing**: pytest with pynetdicom test framework (existing test infrastructure)
**Target Platform**: Linux/macOS server CLI (existing)
**Project Type**: Single CLI project (existing structure)
**Performance Goals**: Maintain existing memory efficiency (50-100x improvement from pandas removal), support sync intervals from 60-300 seconds
**Constraints**: No new dependencies, backward compatible with existing configs, maintain <200MB memory usage during sync
**Scale/Scope**: Initial scope handles REDCap refactoring only; architecture supports 3-5 concurrent data sources in future phases

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Minimalist Dependencies ✅
- **Status**: PASS
- **Rationale**: No new dependencies required. Plugin system uses Python stdlib only (ABC from `abc` module, `importlib` for discovery). REDCap plugin uses existing `PyCap` dependency.

### II. CLI-First Design ✅
- **Status**: PASS
- **Rationale**: All configuration via JSON file (no GUI). Existing CLI commands (`pylantir start`) remain unchanged. New `data_sources` configuration section is optional; legacy `redcap2wl` continues working.

### III. Healthcare Data Integrity ✅
- **Status**: PASS
- **Rationale**: Maintains existing SQLAlchemy transaction patterns. Adds optional `data_source` tracking field to `WorklistItem` for audit trails. All database operations remain atomic and idempotent with rollback capabilities.

### IV. Test-Driven DICOM Integration ✅
- **Status**: PASS
- **Rationale**: Requires unit tests for plugin interface, REDCap plugin implementation, and configuration parsing. Integration tests verify backward compatibility and multi-source sync orchestration.

### V. Operational Observability ✅
- **Status**: PASS
- **Rationale**: Enhances logging with per-source identification. Existing log levels (ERROR, WARNING, INFO, DEBUG) maintained. Source tracking in database enables audit trail analysis.

## Project Structure

### Documentation (this feature)

```text
specs/001-modular-data-sources/
├── plan.md              # This file
├── research.md          # Phase 0: Technical decisions and patterns
├── data-model.md        # Phase 1: Plugin interface and config schema
├── quickstart.md        # Phase 1: Migration guide for users
└── contracts/           # Phase 1: Plugin interface definition
    └── plugin-interface.py
```

### Source Code (repository root)

```text
src/pylantir/
├── models.py                      # [MODIFY] Add optional data_source field
├── db_setup.py                    # [UNCHANGED] Database connection
├── mwl_server.py                  # [UNCHANGED] DICOM services
├── cli/
│   └── run.py                     # [MODIFY] Multi-source orchestration
├── data_sources/                  # [NEW] Plugin directory
│   ├── __init__.py                # [NEW] Plugin registry and discovery
│   ├── base.py                    # [NEW] DataSourcePlugin ABC
│   └── redcap_plugin.py           # [NEW] Refactored from redcap_to_db.py
└── redcap_to_db.py                # [DEPRECATED] Legacy compatibility wrapper

tests/
├── test_plugin_interface.py      # [NEW] Unit tests for base plugin
├── test_redcap_plugin.py          # [NEW] Unit tests for REDCap plugin
├── test_multi_source_config.py    # [NEW] Config parsing tests
└── test_backward_compat.py        # [NEW] Legacy config validation

config/
└── mwl_config.json                # [MODIFY] Add example multi-source config
```

**Structure Decision**: Single CLI project with new `data_sources/` subdirectory for plugin implementations. Existing `redcap_to_db.py` becomes legacy wrapper calling REDCap plugin for backward compatibility.

## Complexity Tracking

> No violations - all Constitution checks passed.

---

## Phase 0: Research & Technical Decisions

**Status**: COMPLETED (documented below)

### Research Tasks

#### R1: Plugin Discovery Pattern
**Decision**: Manual registration via dictionary in `data_sources/__init__.py`
**Rationale**:
- Simpler than filesystem scanning or `importlib` magic
- Explicit registration prevents accidental plugin loading
- Easy to understand and debug for custom plugins
- No performance overhead from dynamic discovery

**Alternatives Considered**:
- Filesystem scanning: Too complex, requires error handling for malformed plugins
- Entry points (setuptools): Adds packaging complexity, overkill for this use case

**Implementation**:
```python
# data_sources/__init__.py
from .base import DataSourcePlugin
from .redcap_plugin import REDCapPlugin

PLUGIN_REGISTRY = {
    "redcap": REDCapPlugin,
}

def get_plugin(source_type: str) -> DataSourcePlugin:
    if source_type not in PLUGIN_REGISTRY:
        raise ValueError(f"Unknown data source type: {source_type}")
    return PLUGIN_REGISTRY[source_type]
```

#### R2: Backward Compatibility Strategy
**Decision**: Legacy config auto-conversion in `run.py`
**Rationale**:
- Detects absence of `data_sources` key
- Converts legacy `redcap2wl`, `site`, `protocol` to new format
- Warns user about deprecated config but continues working
- Single point of conversion logic (DRY principle)

**Alternatives Considered**:
- Dual config parsers: Increases maintenance burden
- Require manual migration: Violates Constitution principle II (user friction)

**Implementation**:
```python
def load_config(config_path):
    config = json.load(open(config_path))

    # Auto-convert legacy config
    if "data_sources" not in config and "redcap2wl" in config:
        lgr.warning("Legacy configuration detected. Consider migrating to 'data_sources' format.")
        config["data_sources"] = [{
            "name": "redcap_legacy",
            "type": "redcap",
            "enabled": True,
            "sync_interval": config.get("db_update_interval", 60),
            "operation_interval": config.get("operation_interval", {"start_time": [0,0], "end_time": [23,59]}),
            "config": {
                "site_id": config.get("site"),
                "protocol": config.get("protocol", {}),
            },
            "field_mapping": config.get("redcap2wl", {})
        }]

    return config
```

#### R3: Thread Management for Multi-Source Sync
**Decision**: ThreadPoolExecutor with one thread per source
**Rationale**:
- Existing code already uses ThreadPoolExecutor (in `run.py`)
- Each source gets independent thread with isolated failure domain
- Python GIL acceptable for I/O-bound sync operations
- Simple shutdown via executor context manager

**Alternatives Considered**:
- asyncio: Requires rewriting existing sync code, increases complexity
- multiprocessing: Overkill for I/O-bound operations, complicates database connection sharing

**Implementation Pattern**:
```python
with ThreadPoolExecutor(max_workers=len(data_sources)) as executor:
    futures = []
    for source_config in data_sources:
        if source_config.get("enabled", True):
            plugin = get_plugin(source_config["type"])()
            future = executor.submit(
                plugin.sync_repeatedly,
                config=source_config,
                stop_event=STOP_EVENT
            )
            futures.append(future)

    # Main thread runs MWL server
    run_mwl_server(...)
```

#### R4: Memory Efficiency with Multiple Sources
**Decision**: Per-source cleanup using existing `cleanup_memory_and_connections()` pattern
**Rationale**:
- Existing code already has excellent memory management (pandas removal)
- Each plugin calls cleanup after its sync cycle
- No shared state between plugins prevents memory leaks
- GC collection after each source sync prevents accumulation

**Implementation**: Each plugin's `fetch_entries()` method must call `gc.collect()` before returning, following existing pattern in `redcap_to_db.py` lines 86-88.

#### R5: Database Field for Source Tracking
**Decision**: Add optional `data_source: String` column to `WorklistItem`
**Rationale**:
- Enables audit trail without breaking existing queries
- Nullable field maintains backward compatibility
- Simple string identifier (source name from config)
- No foreign key complexity (no separate SourceMeta table needed for MVP)

**Alternatives Considered**:
- Separate audit table: Overengineering for initial scope
- JSON metadata field: Less queryable, harder to index

**Migration**: Schema additive change only (ALTER TABLE ADD COLUMN with DEFAULT NULL)

---

## Phase 1: Design & Contracts

### Data Model

**File**: [data-model.md](data-model.md)

#### Entity: DataSourcePlugin (Abstract Base Class)

**Purpose**: Defines the contract that all data source implementations must follow.

**Abstract Methods**:
```python
@abstractmethod
def validate_config(self, config: dict) -> tuple[bool, str]:
    """
    Validate source-specific configuration parameters.

    Args:
        config: Dictionary from data_sources[].config in JSON

    Returns:
        (is_valid, error_message) where error_message is empty string if valid

    Raises:
        None - must return validation result, not raise exceptions
    """
    pass

@abstractmethod
def fetch_entries(self, field_mapping: dict, interval: float) -> list[dict]:
    """
    Fetch worklist entries from the data source.

    Args:
        field_mapping: Dictionary mapping source fields to WorklistItem fields
        interval: Seconds since last sync (for incremental fetching)

    Returns:
        List of dictionaries with keys matching WorklistItem field names

    Raises:
        Exception: Any errors are logged by caller, plugin should not catch
    """
    pass

@abstractmethod
def get_source_name(self) -> str:
    """Return human-readable source type identifier (e.g., 'REDCap', 'CSV')."""
    pass
```

**Concrete Methods** (with default implementations):
```python
def supports_incremental_sync(self) -> bool:
    """Override to return True if source supports fetching only changed records."""
    return False

def cleanup(self) -> None:
    """Override to perform cleanup after sync (close connections, free memory)."""
    pass
```

#### Entity: WorklistItem (Modified)

**New Field**:
```python
data_source = Column(String, nullable=True, default=None)
```

**Purpose**: Track which data source populated each entry for audit trails and debugging.

**Migration**: Additive only - existing entries will have `NULL` value, which is acceptable.

#### Entity: DataSourceConfig (Configuration Schema)

**JSON Structure**:
```json
{
  "data_sources": [
    {
      "name": "unique_source_identifier",
      "type": "redcap",  // Must match key in PLUGIN_REGISTRY
      "enabled": true,
      "sync_interval": 60,
      "operation_interval": {
        "start_time": [0, 0],
        "end_time": [23, 59]
      },
      "config": {
        // Plugin-specific configuration
        // For REDCap: site_id, protocol, api_url_env, api_token_env
      },
      "field_mapping": {
        // Maps source fields to WorklistItem fields
        // Same format as existing redcap2wl
      }
    }
  ]
}
```

**Validation Rules**:
- `name`: Required, unique across all sources in config
- `type`: Required, must exist in `PLUGIN_REGISTRY`
- `enabled`: Optional, defaults to `true`
- `sync_interval`: Optional, defaults to 60 seconds
- `operation_interval`: Optional, defaults to 24/7
- `config`: Required, validated by plugin's `validate_config()` method
- `field_mapping`: Required, must contain mappings for required WorklistItem fields

### API Contracts

**File**: [contracts/plugin-interface.py](contracts/plugin-interface.py)

**Note**: This is not a REST/GraphQL API but a Python interface contract.

```python
"""
Data Source Plugin Interface Contract

This module defines the abstract base class that all Pylantir data source
plugins must implement. It serves as the contract between the core sync
orchestration logic and plugin implementations.

Version: 1.0.0
Stability: Stable (no breaking changes allowed without major version bump)
"""

from abc import ABC, abstractmethod
from typing import Tuple, List, Dict, Optional
import logging

lgr = logging.getLogger(__name__)


class DataSourcePlugin(ABC):
    """
    Abstract base class for all data source plugins.

    Plugins provide the interface between external data sources (REDCap, CSV,
    databases, APIs) and Pylantir's worklist database. Each plugin is responsible
    for fetching, validating, and transforming data from its specific source into
    the standardized WorklistItem format.

    Thread Safety: Plugins must be thread-safe as multiple instances may run
    concurrently when multiple sources are configured.

    Memory Management: Plugins must follow Pylantir's memory efficiency patterns,
    including explicit garbage collection and avoiding pandas DataFrames when
    possible (use list[dict] instead).
    """

    def __init__(self):
        """Initialize the plugin. Override to set up source-specific state."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def validate_config(self, config: Dict) -> Tuple[bool, str]:
        """
        Validate plugin-specific configuration before sync starts.

        Called once during Pylantir startup before any sync operations. Must
        check all required configuration keys, validate formats, and verify
        connectivity if applicable.

        Args:
            config: Dictionary from data_sources[].config in JSON configuration

        Returns:
            (is_valid, error_message) tuple where:
                - is_valid: True if config is valid, False otherwise
                - error_message: Human-readable error description (empty if valid)

        Example:
            >>> plugin.validate_config({"api_token": "abc123"})
            (True, "")
            >>> plugin.validate_config({})
            (False, "Missing required key: api_token")
        """
        pass

    @abstractmethod
    def fetch_entries(
        self,
        field_mapping: Dict[str, str],
        interval: float
    ) -> List[Dict]:
        """
        Fetch worklist entries from the data source.

        Called repeatedly according to sync_interval. Must return data in a
        standardized format where keys are WorklistItem field names (after
        applying field_mapping).

        Args:
            field_mapping: Maps source field names to WorklistItem field names
                          Example: {"source_patient_id": "patient_id"}
            interval: Seconds since last sync. Plugins supporting incremental
                     sync should only fetch records modified in this window.

        Returns:
            List of dictionaries where each dict represents one worklist entry.
            Keys must be WorklistItem field names (patient_id, patient_name, etc.)

        Raises:
            Any exceptions are caught by orchestration layer and logged. Plugins
            should not catch their own exceptions unless performing cleanup.

        Example:
            >>> entries = plugin.fetch_entries(
            ...     field_mapping={"pid": "patient_id", "dob": "patient_birth_date"},
            ...     interval=60.0
            ... )
            >>> entries
            [
                {"patient_id": "12345", "patient_birth_date": "19900101", ...},
                {"patient_id": "67890", "patient_birth_date": "19850615", ...}
            ]
        """
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """
        Return human-readable source type identifier.

        Used for logging and database source tracking. Should be concise and
        descriptive (e.g., "REDCap", "CSV", "PostgreSQL").

        Returns:
            String identifier for this source type

        Example:
            >>> plugin.get_source_name()
            "REDCap"
        """
        pass

    def supports_incremental_sync(self) -> bool:
        """
        Indicate whether this plugin supports incremental synchronization.

        Incremental sync means the plugin can efficiently fetch only records
        that changed since the last sync, using the interval parameter in
        fetch_entries().

        Default: False (full sync every interval)
        Override: Return True if plugin implements incremental logic

        Returns:
            True if plugin supports incremental sync, False otherwise
        """
        return False

    def cleanup(self) -> None:
        """
        Perform cleanup after each sync cycle.

        Called after fetch_entries() completes (success or failure). Use for
        closing connections, freeing memory, or other resource cleanup.

        Default: No-op
        Override: Implement source-specific cleanup logic

        Example:
            def cleanup(self):
                if hasattr(self, '_connection'):
                    self._connection.close()
                gc.collect()
        """
        pass


class PluginError(Exception):
    """Base exception for plugin-related errors."""
    pass


class PluginConfigError(PluginError):
    """Raised when plugin configuration is invalid."""
    pass


class PluginFetchError(PluginError):
    """Raised when plugin fails to fetch data from source."""
    pass
```

### Migration Guide

**File**: [quickstart.md](quickstart.md)

```markdown
# Quick Start: Migrating to Multi-Source Configuration

## For Existing REDCap Users

Your existing configuration will continue working without changes. However, we recommend migrating to the new `data_sources` format for better flexibility.

### Current Configuration (Still Supported)

\`\`\`json
{
  "db_update_interval": 60,
  "site": "792",
  "protocol": {"792": "BRAIN_MRI_3T"},
  "redcap2wl": {
    "study_id": "study_id",
    "mri_instance": "session_id"
  }
}
\`\`\`

### New Configuration (Recommended)

\`\`\`json
{
  "data_sources": [
    {
      "name": "main_redcap",
      "type": "redcap",
      "enabled": true,
      "sync_interval": 60,
      "operation_interval": {
        "start_time": [0, 0],
        "end_time": [23, 59]
      },
      "config": {
        "site_id": "792",
        "protocol": {"792": "BRAIN_MRI_3T"}
      },
      "field_mapping": {
        "study_id": "study_id",
        "mri_instance": "session_id",
        "youth_dob_y": "patient_birth_date",
        "demo_sex": "patient_sex"
      }
    }
  ]
}
\`\`\`

### Migration Steps

1. **Backup your current config**: `cp mwl_config.json mwl_config.json.backup`
2. **Update config file** with `data_sources` array format (see above)
3. **Test configuration**: `pylantir start` (watch for validation errors)
4. **Verify sync**: `pylantir query-db` to confirm entries are populated

### Environment Variables

No changes required. REDCap plugin still uses:
- `REDCAP_API_URL`
- `REDCAP_API_TOKEN`

## For Future Multi-Source Setups

Ready to add additional data sources? The architecture is now in place. See [Phase 2 documentation] for implementing custom plugins.
```

---

## Phase 2: Implementation Checklist

**Note**: This section outlines implementation order. Actual task breakdown will be created by `/speckit.tasks` command.

### Stage 1: Plugin Foundation (P1 - REDCap Refactoring)

**Files to Create**:
1. `src/pylantir/data_sources/__init__.py` - Plugin registry
2. `src/pylantir/data_sources/base.py` - DataSourcePlugin ABC
3. `src/pylantir/data_sources/redcap_plugin.py` - REDCap implementation

**Files to Modify**:
1. `src/pylantir/models.py` - Add `data_source` field to WorklistItem
2. `src/pylantir/cli/run.py` - Multi-source orchestration + legacy config conversion
3. `src/pylantir/redcap_to_db.py` - Convert to legacy wrapper (calls redcap_plugin)

**Tests to Create**:
1. `tests/test_plugin_interface.py` - Validate ABC contract
2. `tests/test_redcap_plugin.py` - Unit tests for REDCap plugin
3. `tests/test_backward_compat.py` - Verify legacy configs still work

**Success Criteria**:
- Existing REDCap configs work without modification ✓
- New data_sources format works for single REDCap source ✓
- Legacy warning logged when old format detected ✓
- All existing tests pass ✓

### Stage 2: Multi-Source Orchestration (P2 - Future Phase)

**Note**: Not implemented in initial scope per user request. Architecture is ready.

**Future Files**:
- `src/pylantir/data_sources/csv_plugin.py`
- `src/pylantir/data_sources/json_plugin.py`
- `tests/test_multi_source_sync.py`

### Stage 3: Documentation & Examples (P1)

**Files to Create/Update**:
1. `README.md` - Add migration guide section
2. `config/mwl_config_multi_source_example.json` - Example multi-source config
3. `specs/001-modular-data-sources/quickstart.md` - This document

---

## Testing Strategy

### Unit Tests

**test_plugin_interface.py**:
- Verify ABC cannot be instantiated directly
- Verify subclass must implement all abstract methods
- Verify default implementations (supports_incremental_sync, cleanup)

**test_redcap_plugin.py**:
- Mock PyCap Project to avoid REDCap dependency
- Test validate_config() with valid/invalid configs
- Test fetch_entries() data transformation
- Test memory cleanup after fetch
- Test error handling for API failures

**test_backward_compat.py**:
- Load legacy config, verify auto-conversion
- Verify converted config has correct structure
- Verify warning is logged
- Verify sync works with converted config

### Integration Tests

**test_multi_source_config.py**:
- Parse config with multiple sources
- Verify each source gets separate thread
- Verify all sources sync to same database
- Verify source tracking field is populated

**test_source_isolation.py**:
- Simulate one source failing
- Verify other sources continue syncing
- Verify error is logged with source name
- Verify partial data is committed

### Performance Tests

**test_memory_efficiency.py**:
- Baseline: Single REDCap source memory usage
- Test: Verify memory stays constant across sync cycles
- Test: Verify cleanup reduces memory after each cycle
- Ensure 50-100x improvement vs pandas is maintained

---

## Rollout Plan

### Phase 1: REDCap Refactoring (This Implementation)

**Timeline**: 1-2 weeks
**Scope**: FR-001 through FR-009, FR-013, FR-014, FR-015
**Deliverables**:
- Plugin interface (base.py)
- REDCap plugin (redcap_plugin.py)
- Multi-source orchestration (run.py)
- Backward compatibility (auto-conversion)
- Unit + integration tests
- Migration guide (quickstart.md)

**Risks**:
- Breaking existing deployments → Mitigated by auto-conversion + extensive backward compat tests
- Memory regression → Mitigated by following existing cleanup patterns
- Thread safety issues → Mitigated by isolated plugin state, no shared globals

### Phase 2: Additional Sources (Future)

**Timeline**: TBD
**Scope**: FR-010 (CSV, JSON plugins), FR-011 (documentation)
**Prerequisites**: Phase 1 complete, user validation of architecture

### Phase 3: Advanced Features (Future)

**Scope**: FR-004 (auto-discovery), FR-012 (duplicate detection), conflict resolution
**Prerequisites**: Phase 2 complete, real-world multi-source usage data

---

## Open Questions

None - all decisions finalized in Phase 0 research.

## Appendix: File Mapping Reference

| Spec Requirement | Implementation File | Status |
|-----------------|-------------------|--------|
| FR-001: Multi-source config | `cli/run.py` | To implement |
| FR-002: Backward compat | `cli/run.py` (auto-convert) | To implement |
| FR-003: Plugin interface | `data_sources/base.py` | To implement |
| FR-005: Concurrent sync | `cli/run.py` (ThreadPoolExecutor) | To implement |
| FR-006: Source tracking | `models.py` (data_source field) | To implement |
| FR-007: Failure isolation | `cli/run.py` (try/except per thread) | To implement |
| FR-008: Config validation | `data_sources/base.py` + `cli/run.py` | To implement |
| FR-009: Per-source intervals | Each plugin's sync loop | To implement |
| FR-013: Field mapping | Each plugin's fetch_entries() | To implement |
| FR-014: Memory efficiency | Each plugin's cleanup() | To implement |
| FR-015: Clean shutdown | `cli/run.py` (STOP_EVENT) | Existing |

---

**Plan Status**: ✅ Complete - Ready for `/speckit.tasks` to generate implementation tasks
