# Data Model: Modular Data Source Architecture

**Feature**: 001-modular-data-sources
**Date**: 2026-01-26

## Overview

This document defines the data structures and relationships for the plugin-based data source architecture. The design focuses on minimal changes to existing database schema while adding source tracking capabilities.

---

## Core Entities

### 1. DataSourcePlugin (Abstract Base Class)

**Purpose**: Defines the contract for all data source implementations.

**Type**: Python ABC (Abstract Base Class)

**Attributes**:
- `logger: Logger` - Instance-specific logger for this plugin

**Abstract Methods**:

| Method | Parameters | Returns | Purpose |
|--------|-----------|---------|---------|
| `validate_config()` | `config: Dict` | `Tuple[bool, str]` | Validate plugin-specific configuration |
| `fetch_entries()` | `field_mapping: Dict`, `interval: float` | `List[Dict]` | Fetch worklist entries from source |
| `get_source_name()` | None | `str` | Return human-readable source identifier |

**Concrete Methods** (with defaults):

| Method | Parameters | Returns | Default | Purpose |
|--------|-----------|---------|---------|---------|
| `supports_incremental_sync()` | None | `bool` | `False` | Indicate if incremental sync supported |
| `cleanup()` | None | `None` | No-op | Cleanup after sync cycle |

**Validation Rules**:
- Subclasses MUST implement all abstract methods
- `validate_config()` MUST NOT raise exceptions (return tuple instead)
- `fetch_entries()` MUST return list of dicts with WorklistItem field names as keys
- `get_source_name()` MUST return non-empty string

**State Transitions**: Not applicable (stateless interface)

**Example Implementation**:
```python
class REDCapPlugin(DataSourcePlugin):
    def validate_config(self, config: dict) -> tuple[bool, str]:
        if "site_id" not in config:
            return (False, "Missing required config key: site_id")
        return (True, "")

    def fetch_entries(self, field_mapping: dict, interval: float) -> list[dict]:
        # Fetch from REDCap, transform, return
        return [{"patient_id": "...", "patient_name": "..."}]

    def get_source_name(self) -> str:
        return "REDCap"
```

---

### 2. WorklistItem (Extended)

**Purpose**: SQLAlchemy ORM model representing a DICOM worklist entry.

**Type**: Database entity (SQLite table)

**Existing Fields** (unchanged):
- `id: Integer` (Primary Key)
- `study_instance_uid: String`
- `patient_name: String`
- `patient_id: String`
- `patient_birth_date: String`
- `patient_sex: String`
- `accession_number: String`
- `modality: String`
- `scheduled_start_date: String`
- `scheduled_start_time: String`
- `performed_procedure_step_status: String`

**New Fields**:

| Field | Type | Nullable | Default | Index | Purpose |
|-------|------|----------|---------|-------|---------|
| `data_source` | String | Yes | NULL | No | Track which data source populated this entry |

**Validation Rules**:
- `data_source` is optional (NULL allowed for backward compatibility)
- When populated, should match `name` from data source configuration
- Length limit: 255 characters (reasonable for source names)

**Schema Migration**:
```sql
ALTER TABLE worklist_item ADD COLUMN data_source VARCHAR(255) DEFAULT NULL;
```

**Relationships**: None (simple tracking field, no foreign keys)

**Example**:
```python
# Entry from REDCap source
entry1 = WorklistItem(
    patient_id="sub_12345_ses_1",
    patient_name="cpip-id-12345^fa-99",
    data_source="main_redcap"  # New field
)

# Legacy entry (before multi-source)
entry2 = WorklistItem(
    patient_id="sub_67890_ses_1",
    patient_name="cpip-id-67890^fa-88",
    data_source=None  # NULL for legacy entries
)
```

---

### 3. DataSourceConfig (Configuration Schema)

**Purpose**: JSON configuration structure for defining data sources.

**Type**: JSON schema (validated at runtime)

**Structure**:

```json
{
  "data_sources": [
    {
      "name": "string (required, unique)",
      "type": "string (required, must exist in PLUGIN_REGISTRY)",
      "enabled": "boolean (optional, default: true)",
      "sync_interval": "number (optional, default: 60, seconds)",
      "operation_interval": {
        "start_time": "[number, number] (optional, default: [0, 0])",
        "end_time": "[number, number] (optional, default: [23, 59])"
      },
      "config": {
        "...": "object (required, plugin-specific keys)"
      },
      "field_mapping": {
        "source_field": "worklist_field (required)"
      }
    }
  ]
}
```

**Field Definitions**:

| Field | Type | Required | Default | Validation |
|-------|------|----------|---------|------------|
| `name` | String | Yes | N/A | Unique across all sources, 1-255 chars |
| `type` | String | Yes | N/A | Must exist in PLUGIN_REGISTRY |
| `enabled` | Boolean | No | `true` | N/A |
| `sync_interval` | Number | No | `60` | >= 1 second |
| `operation_interval.start_time` | Array[2] | No | `[0, 0]` | Valid 24h time |
| `operation_interval.end_time` | Array[2] | No | `[23, 59]` | Valid 24h time, >= start_time |
| `config` | Object | Yes | N/A | Validated by plugin.validate_config() |
| `field_mapping` | Object | Yes | N/A | Must map to valid WorklistItem fields |

**Validation Rules**:
1. At least one data source must be present in array
2. All `name` values must be unique
3. All `type` values must match registered plugins
4. `operation_interval` start must be before end
5. `field_mapping` must include all required WorklistItem fields

**Example - REDCap Source**:
```json
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
        "demo_sex": "patient_sex",
        "mri_date": "scheduled_start_date",
        "mri_time": "scheduled_start_time"
      }
    }
  ]
}
```

**Example - Legacy Config (Auto-Converted)**:
```json
{
  "db_update_interval": 60,
  "site": "792",
  "protocol": {"792": "BRAIN_MRI_3T"},
  "redcap2wl": {
    "study_id": "study_id",
    "mri_instance": "session_id"
  }
}
```

Automatically converted to:
```json
{
  "data_sources": [
    {
      "name": "redcap_legacy",
      "type": "redcap",
      "enabled": true,
      "sync_interval": 60,
      "config": {
        "site_id": "792",
        "protocol": {"792": "BRAIN_MRI_3T"}
      },
      "field_mapping": {
        "study_id": "study_id",
        "mri_instance": "session_id"
      }
    }
  ]
}
```

---

### 4. PluginRegistry (Runtime)

**Purpose**: Maps source type names to plugin classes.

**Type**: Python dictionary (runtime singleton)

**Structure**:
```python
PLUGIN_REGISTRY: Dict[str, Type[DataSourcePlugin]] = {
    "redcap": REDCapPlugin,
    # Future plugins added here
}
```

**Operations**:

| Operation | Input | Output | Purpose |
|-----------|-------|--------|---------|
| `register_plugin()` | `type_name: str`, `plugin_class: Type` | None | Add plugin to registry |
| `get_plugin()` | `type_name: str` | `Type[DataSourcePlugin]` | Retrieve plugin class |
| `list_plugins()` | None | `List[str]` | Get all registered type names |

**Validation Rules**:
- Plugin type names must be lowercase alphanumeric with underscores only
- Plugin classes must inherit from DataSourcePlugin
- Cannot override built-in plugins (redcap, csv, json reserved)

**Example**:
```python
from pylantir.data_sources import PLUGIN_REGISTRY, get_plugin

# Get plugin class
RedCapClass = get_plugin("redcap")

# Instantiate
plugin = RedCapClass()

# Validate config
is_valid, error = plugin.validate_config({"site_id": "792"})
```

---

## Data Flow Diagram

```
User Config (JSON)
    │
    ├─ Legacy Format (redcap2wl) ──────────┐
    │                                       │
    └─ New Format (data_sources[]) ────────┤
                                            ▼
                                   load_config() in run.py
                                            │
                                    [Auto-convert if legacy]
                                            │
                                            ▼
                                   Parse data_sources[]
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    ▼                                               ▼
            Source Config 1                                 Source Config N
                    │                                               │
                    ▼                                               ▼
            get_plugin("type")                              get_plugin("type")
                    │                                               │
                    ▼                                               ▼
            REDCapPlugin()                                  CustomPlugin()
                    │                                               │
            validate_config() ✓                            validate_config() ✓
                    │                                               │
        ┌───────────┴──────────────────────────────────────────────┴────────┐
        │                   ThreadPoolExecutor                               │
        │   ┌────────────────────┐              ┌────────────────────┐      │
        │   │ Thread 1           │              │ Thread N           │      │
        │   │ fetch_entries() ───┼─────┐        │ fetch_entries() ───┼───┐  │
        │   │ cleanup()          │     │        │ cleanup()          │   │  │
        │   └────────────────────┘     │        └────────────────────┘   │  │
        └──────────────────────────────┼────────────────────────────────┼──┘
                                       ▼                                ▼
                                List[Dict]                         List[Dict]
                                       │                                │
                                       └────────────┬───────────────────┘
                                                    ▼
                                        Transform to WorklistItem
                                        (apply field_mapping)
                                                    │
                                                    ▼
                                        Add data_source field
                                                    │
                                                    ▼
                                        SQLAlchemy Session
                                                    │
                                                    ▼
                                        Commit to worklist.db
                                                    │
                                                    ▼
                                        DICOM MWL Server
                                        (serve via C-FIND)
```

---

## Field Mapping Reference

### Required WorklistItem Fields

These fields MUST be present in field_mapping for each data source:

| WorklistItem Field | Type | Example Source Field (REDCap) |
|-------------------|------|-------------------------------|
| `patient_id` | String | Computed from study_id + session_id |
| `patient_name` | String | Computed from study_id + family_id |
| `patient_birth_date` | String (YYYYMMDD) | youth_dob_y |
| `patient_sex` | String (M/F/O) | demo_sex |
| `modality` | String | Fixed to "MR" |
| `scheduled_start_date` | String (YYYYMMDD) | mri_date |
| `scheduled_start_time` | String (HHMMSS) | mri_time |

### Optional WorklistItem Fields

| WorklistItem Field | Type | Example |
|-------------------|------|---------|
| `accession_number` | String | Unique visit identifier |
| `study_instance_uid` | String | Auto-generated UID |
| `performed_procedure_step_status` | String | Default: "SCHEDULED" |

---

## Database Schema Changes

### Migration Script

**File**: `migrations/001_add_data_source_field.sql`

```sql
-- Add data_source tracking field to worklist_item table
-- This is an additive change, fully backward compatible

BEGIN TRANSACTION;

-- Add column with NULL default
ALTER TABLE worklist_item
ADD COLUMN data_source VARCHAR(255) DEFAULT NULL;

-- No index needed initially (few queries filter by source)
-- Can add index later if needed:
-- CREATE INDEX idx_worklist_data_source ON worklist_item(data_source);

COMMIT;
```

**Rollback Script**:
```sql
-- Rollback data_source field addition
-- Warning: This will drop the column and lose source tracking data

BEGIN TRANSACTION;

ALTER TABLE worklist_item
DROP COLUMN data_source;

COMMIT;
```

### Impact Analysis

**Backward Compatibility**: ✅ Full
- Existing code that doesn't set `data_source` will use NULL (default)
- Existing queries without `data_source` filter continue working
- No required foreign keys or constraints

**Performance Impact**: ✅ Negligible
- Single VARCHAR(255) field adds ~8 bytes per row
- NULL values compressed efficiently in SQLite
- No index initially, so no query overhead

**Data Integrity**: ✅ Maintained
- NULL is valid value (represents legacy/unknown source)
- No foreign key constraints to maintain
- Optional field doesn't break existing validation

---

## Configuration Examples

### Single REDCap Source (Recommended Format)

```json
{
  "data_sources": [
    {
      "name": "main_redcap",
      "type": "redcap",
      "enabled": true,
      "sync_interval": 60,
      "operation_interval": {
        "start_time": [8, 0],
        "end_time": [18, 0]
      },
      "config": {
        "site_id": "792",
        "protocol": {
          "792": "BRAIN_MRI_3T"
        }
      },
      "field_mapping": {
        "study_id": "study_id",
        "mri_instance": "session_id",
        "family_id": "family_id",
        "youth_dob_y": "patient_birth_date",
        "demo_sex": "patient_sex",
        "mri_date": "scheduled_start_date",
        "mri_time": "scheduled_start_time"
      }
    }
  ],

  "db_path": "~/Desktop/worklist.db",
  "allowed_aet": ["MRI_SCANNER"]
}
```

### Multiple Sources (Future Example)

```json
{
  "data_sources": [
    {
      "name": "site_a_redcap",
      "type": "redcap",
      "enabled": true,
      "sync_interval": 60,
      "config": {...},
      "field_mapping": {...}
    },
    {
      "name": "site_b_csv",
      "type": "csv",
      "enabled": true,
      "sync_interval": 300,
      "config": {
        "file_path": "/data/site_b_schedule.csv"
      },
      "field_mapping": {...}
    }
  ]
}
```

---

## Validation Reference

### Config Validation Flow

1. **Parse JSON** → Check syntax errors
2. **Check top-level keys** → Ensure `data_sources` exists OR legacy keys present
3. **Auto-convert legacy** → If `redcap2wl` present, convert to `data_sources` format
4. **Validate each source**:
   - `name` is unique
   - `type` exists in PLUGIN_REGISTRY
   - `sync_interval` >= 1
   - `operation_interval` times are valid
5. **Call plugin.validate_config()** → Plugin-specific validation
6. **Check field_mapping** → All required WorklistItem fields mapped

### Error Messages

| Validation Failure | Error Message |
|-------------------|---------------|
| Missing `data_sources` | "Configuration must include 'data_sources' array or legacy 'redcap2wl' mapping" |
| Duplicate source name | "Duplicate data source name: '{name}'" |
| Unknown plugin type | "Unknown data source type: '{type}'. Available: {available_types}" |
| Invalid sync interval | "sync_interval must be >= 1 second, got: {value}" |
| Invalid time range | "operation_interval end_time must be after start_time" |
| Plugin config invalid | "Data source '{name}' configuration invalid: {plugin_error}" |
| Missing field mapping | "Field mapping missing required WorklistItem field: '{field}'" |

---

## Summary

**Core Changes**:
1. ✅ Add `data_source` field to `WorklistItem` (nullable, backward compatible)
2. ✅ Define `DataSourcePlugin` ABC with 3 required methods + 2 optional
3. ✅ Define `DataSourceConfig` JSON schema with validation rules
4. ✅ Create `PLUGIN_REGISTRY` for plugin discovery

**Zero Breaking Changes**:
- Database: Additive field only (NULL default)
- Configuration: Legacy format auto-converted
- Code: Existing sync logic wrapped in REDCap plugin

**Ready For**:
- Phase 1 implementation (REDCap refactoring)
- Future Phase 2 (additional source plugins)
- Phase 3 (advanced features like auto-discovery)
