# Implementation Plan: Calpendo Data Source Plugin

**Branch**: `002-calpendo-plugin` | **Date**: 2026-01-27 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/002-calpendo-plugin/spec.md`

## Summary

Implement a Calpendo data source plugin following the established DataSourcePlugin architecture pattern from REDCapPlugin. The plugin will fetch MRI/EEG scanner bookings from Calpendo's WebDAV API using HTTP basic authentication and the `requests` library. It transforms Calpendo bookings into DICOM worklist entries with support for regex-based field extraction from composite fields (e.g., extracting PatientID and PatientName from a single Title field). Uses rolling window sync strategy (last N hours) to minimize API load while detecting changes, and marks disappeared bookings as cancelled to preserve audit history.

**Key Technical Approach**:
- HTTP requests via `requests` library (simple, no complex API client needed)
- Rolling window sync: fetch bookings modified in last `sync_interval * 2` hours
- Regex extraction patterns nested in field_mapping config for flexible field parsing
- Change detection via field hashing to avoid unnecessary DB writes
- Cancelled booking preservation for audit trail compliance

## Technical Context

**Language/Version**: Python 3.8+ (existing Pylantir constraint)  
**Primary Dependencies**: 
- `requests` (HTTP client for Calpendo API - NEW)
- `pytz` (timezone conversion UTC ↔ Mountain Time - NEW)
- `re` (regex pattern matching for field extraction - stdlib)
- `sqlalchemy` (existing - DB operations)
- `concurrent.futures.ThreadPoolExecutor` (existing - parallel API requests)

**Storage**: SQLite via SQLAlchemy ORM (existing WorklistItem model, no schema changes needed)  
**Testing**: pytest (existing framework), mock Calpendo API responses  
**Target Platform**: Linux/macOS servers running Pylantir MWL service  
**Project Type**: Single Python package with plugin architecture  
**Performance Goals**: 
- <10s sync for 50 bookings (spec SC-001)
- 3-5x speedup with parallel requests (spec SC-007)
- <200ms per booking transformation

**Constraints**:
- Must not modify existing WorklistItem schema
- Must follow DataSourcePlugin interface contract
- Environment variables only for credentials (no secrets in config files)
- Mountain Time (America/Edmonton) timezone for all timestamps

**Scale/Scope**: 
- 10-100 bookings per day per resource
- 3-5 resources (3T, EEG, Mock Scanner)
- Single Calpendo server instance

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### ✅ **Principle I: Minimalist Dependencies**
- **New Dependencies**: `requests`, `pytz`
- **Justification**: 
  - `requests`: Calpendo has simple REST/WebDAV API, no complex client needed. Widely used, stable, minimal footprint.
  - `pytz`: Required for accurate timezone conversions (UTC ↔ Mountain Time). Standard library `datetime` insufficient for historical timezone rules.
- **Approval**: Both are industry-standard, minimal attack surface, well-maintained.

### ✅ **Principle II: CLI-First Design**
- Plugin integrates with existing `pylantir start` command via `data_sources` config
- No new CLI commands required
- All configuration via JSON and environment variables
- **Status**: PASS

### ✅ **Principle III: Healthcare Data Integrity**
- All transformations logged (INFO level for success, WARNING for missing fields)
- Regex extraction failures logged with original field values
- Cancelled bookings marked (not deleted) - preserves audit trail
- Change detection prevents duplicate processing
- **Status**: PASS

### ✅ **Principle IV: Test-Driven DICOM Integration**
- Unit tests for regex extraction patterns
- Mock Calpendo API responses for integration tests
- End-to-end sync workflow validation
- Error handling tests (API failures, malformed responses)
- **Status**: PASS (tests will be created in Phase 2)

### ✅ **Principle V: Operational Observability**
- Structured logging: `[calpendo:{source_name}]` prefix for all messages
- API request/response logging (DEBUG level)
- Change detection logging (INFO when updates detected)
- Error details with booking IDs for debugging
- **Status**: PASS

**Constitution Violations**: NONE

## Project Structure

### Documentation (this feature)

```text
specs/002-calpendo-plugin/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (Calpendo API contract)
│   └── calpendo-api.md
└── tasks.md             # Phase 2 output (NOT created by this command)
```

### Source Code (repository root)

```text
src/pylantir/
├── data_sources/
│   ├── __init__.py                # Existing - PLUGIN_REGISTRY
│   ├── base.py                    # Existing - DataSourcePlugin ABC
│   ├── redcap_plugin.py           # Existing - reference implementation
│   └── calpendo_plugin.py         # NEW - this feature
├── cli/
│   └── run.py                     # Existing - add Calpendo to imports (no logic changes)
└── config/
    └── calpendo_config_example.json  # NEW - example configuration

tests/
├── test_calpendo_plugin.py        # NEW - plugin unit tests
├── test_calpendo_integration.py   # NEW - integration tests with mock API
└── fixtures/
    └── calpendo_responses.json    # NEW - mock API responses
```

**Structure Decision**: Single plugin architecture following established pattern. New plugin file `calpendo_plugin.py` implements `DataSourcePlugin` interface. No changes to core framework needed - plugin auto-discovered via PLUGIN_REGISTRY.

## Complexity Tracking

> **Not needed - no constitution violations to justify**

## Phase 0: Research & Technical Investigation

**Objective**: Resolve all technical unknowns and establish implementation patterns.

### Research Tasks

#### R001: Calpendo API Deep Dive
**Question**: Document exact API endpoints, query syntax, authentication, and response formats.

**Investigation**:
1. Analyze `example_for_calpendo.py` for API patterns:
   - Base URL structure: `{base_url}/webdav/q/Calpendo.Booking/{query}`
   - Query language: URL-encoded path segments (e.g., `AND/dateRange.start/GE/{date}`)
   - Authentication: HTTP Basic Auth (username, password)
   - Response format: JSON with `biskits` array containing booking objects

2. Test query capabilities:
   - Date range queries: `dateRange.start/GE/{start}/dateRange.start/LT/{end}`
   - Resource filtering: `OR/resource.name/EQ/{resource1}/resource.name/EQ/{resource2}`
   - Boolean operators: `AND`, `OR` for combining conditions
   - **Limitation**: No `modified` timestamp in query parameters (confirmed from example)

3. Document booking detail fetching:
   - Basic booking: `/webdav/b/Calpendo.Booking/{booking_id}`
   - Extended details: `/webdav/q/{biskit_type}/id/eq/{booking_id}?paths=field1,field2`
   - Parallel fetching: ThreadPoolExecutor pattern from example (max_workers=5)

**Output**: Document in `research.md` with example queries and response structures.

---

#### R002: Rolling Window Sync Strategy
**Question**: How to implement efficient rolling window sync without modification timestamps?

**Approach**:
1. **Window Size**: `sync_interval * 2` (e.g., 120 seconds for 60s interval)
   - Rationale: 2x safety margin catches bookings created/modified between sync cycles
   - Configurable via `lookback_multiplier` in plugin config (default: 2)

2. **Window Calculation**:
   ```python
   now = datetime.now(pytz.UTC)
   window_start = now - timedelta(seconds=sync_interval * lookback_multiplier)
   window_end = now + timedelta(days=1)  # Include future bookings for next day
   ```

3. **Change Detection Logic**:
   - Fetch all bookings in window
   - For each booking, compute hash of critical fields
   - Compare hash with existing DB record (if exists)
   - Actions:
     - New booking → INSERT
     - Changed booking → UPDATE
     - Missing from window but exists in DB with status≠cancelled → Mark as cancelled

4. **Hash Fields**:
   ```python
   critical_fields = [
       'title',  # Subject ID
       'project.formattedName',  # Study name
       'formattedName',  # Start/end times
       'status',
       'resource.formattedName'
   ]
   ```

**Output**: Algorithm pseudocode in `research.md`.

---

#### R003: Regex Field Extraction Architecture
**Question**: How to structure nested extraction patterns in field_mapping config?

**Design**:

**Config Structure** (Option A - nested in field_mapping):
```json
{
  "field_mapping": {
    "title": {
      "_extract": {
        "patient_id": {"pattern": "^([A-Z0-9]+)", "group": 1},
        "patient_name": {"pattern": " - (.+)$", "group": 1}
      }
    },
    "project.formattedName": {
      "_extract": {
        "study_description": {"pattern": "^([^(]+)", "group": 1}
      }
    },
    "formattedName": {
      "_extract": {
        "scheduled_start_date": {"pattern": "^\\[([0-9-]+)", "group": 1},
        "scheduled_start_time": {"pattern": "([0-9:]+\\.[0-9])", "group": 1}
      }
    },
    "resource.formattedName": "modality",
    "status": "performed_procedure_step_status"
  }
}
```

**Extraction Logic**:
```python
def extract_field(source_value: str, extraction_config: dict) -> str:
    """Apply regex pattern to extract substring."""
    pattern = extraction_config['pattern']
    group = extraction_config.get('group', 0)
    match = re.search(pattern, source_value)
    if match:
        return match.group(group).strip()
    else:
        logger.warning(f"Pattern '{pattern}' failed on value '{source_value}'")
        return None
```

**Fallback Strategy**:
- If `_extract` fails, use original source value
- Log warnings for failed extractions with original values
- Continue processing (don't fail entire booking)

**Output**: Code examples and config schema in `research.md`.

---

#### R004: Timezone Handling Best Practices
**Question**: How to reliably convert between UTC (Calpendo) and Mountain Time (worklist)?

**Investigation**:
1. **pytz Usage**:
   ```python
   import pytz
   mt_tz = pytz.timezone('America/Edmonton')
   utc_tz = pytz.UTC
   
   # Calpendo returns: "[2025-02-12 10:00:00.0, 2025-02-12 11:00:00.0]"
   # Parse as Mountain Time, convert to UTC for storage
   dt_str = "2025-02-12 10:00:00.0"
   dt_naive = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S.%f')
   dt_mt = mt_tz.localize(dt_naive)
   dt_utc = dt_mt.astimezone(utc_tz)
   ```

2. **Daylight Saving Time**:
   - `pytz.localize()` handles DST transitions automatically
   - Never use `replace(tzinfo=...)` - loses DST info
   - Always parse as MT, store as UTC, display as MT

3. **formattedName Parsing**:
   - Format: `"[YYYY-MM-DD HH:MM:SS.f, YYYY-MM-DD HH:MM:SS.f]"`
   - Extract start/end with regex
   - Parse both timestamps, return tuple

**Output**: Utility functions in `research.md`.

---

#### R005: Error Recovery Patterns
**Question**: How to handle API failures gracefully without crashing sync loop?

**Patterns**:
1. **Connection Errors**:
   ```python
   try:
       response = requests.get(url, auth=auth, timeout=30)
       response.raise_for_status()
   except requests.ConnectionError as e:
       raise PluginFetchError(f"Cannot connect to Calpendo: {e}")
   except requests.Timeout:
       raise PluginFetchError("Calpendo API timeout after 30s")
   except requests.HTTPError as e:
       if e.response.status_code == 401:
           raise PluginConfigError("Invalid Calpendo credentials")
       else:
           raise PluginFetchError(f"Calpendo API error: {e}")
   ```

2. **Partial Failures**:
   - If one booking detail fetch fails, log and skip that booking
   - Continue processing remaining bookings
   - Return all successfully processed entries

3. **Malformed Data**:
   - Missing required fields → log warning, skip booking
   - Regex extraction failure → use fallback (original value or None)
   - Invalid timestamps → log error, skip booking

**Output**: Error handling patterns in `research.md`.

---

### Research Deliverable: `research.md`

Document all findings with:
- Calpendo API reference (endpoints, queries, responses)
- Rolling window algorithm with pseudocode
- Regex extraction examples and config schema
- Timezone conversion utilities
- Error handling decision tree

## Phase 1: Design & Contracts

**Prerequisites**: `research.md` complete

### D001: Data Model Specification

**File**: `data-model.md`

**Entities**:

#### CalendoBooking (Source Entity)
**Purpose**: Represents a booking from Calpendo API (not a DB model, just transformation input)

**Fields**:
- `id` (int): Calpendo booking ID
- `formattedName` (str): Date range string "[start, end]"
- `title` (str): Subject identifier (may contain PatientID + PatientName)
- `status` (str): Booking status (Approved, Pending, Cancelled)
- `biskitType` (str): Booking type (MRIScan, EEGScan, etc.)
- `properties` (dict): Nested booking details
  - `resource.formattedName` (str): Scanner name (e.g., "3T Diagnostic")
  - `project.formattedName` (str): Study name with description
  - `durationInMinutes` (int): Booking duration
  - `created` (str): Creation timestamp
  - `modified` (str): Modification timestamp
  - `Operator.name` (str, optional): MRI operator name

**Transformations**:
- `formattedName` → `scheduled_start_date`, `scheduled_start_time` (via regex + timezone conversion)
- `title` → `patient_id`, `patient_name` (via regex extraction)
- `project.formattedName` → `study_description` (extract before parentheses)
- `resource.formattedName` → `modality` (direct mapping or prefix extraction)
- `status` → `performed_procedure_step_status` (map "Approved" → "SCHEDULED")

---

#### WorklistItem (Existing DB Model)
**Purpose**: DICOM worklist entry (no schema changes)

**Relevant Fields**:
- `study_instance_uid`: Generated UUID
- `patient_name`: From title extraction
- `patient_id`: From title extraction
- `patient_birth_date`: Not available from Calpendo (set to None or default)
- `patient_sex`: Not available from Calpendo (set to None or 'O')
- `accession_number`: Generated from booking ID
- `modality`: From resource mapping
- `scheduled_start_date`: From formattedName
- `scheduled_start_time`: From formattedName
- `performed_procedure_step_status`: From status mapping
- `data_source`: Set to source_name (e.g., "calpendo_3t")

**Status Mappings**:
```
Calpendo Status → DICOM Status
"Approved"      → "SCHEDULED"
"In Progress"   → "IN_PROGRESS"
"Completed"     → "COMPLETED"
"Cancelled"     → "DISCONTINUED"
"Pending"       → "SCHEDULED" (or skip if configured)
```

---

#### Change Hash (Tracking)
**Purpose**: Detect booking modifications without relying on `modified` timestamp

**Algorithm**:
```python
def compute_booking_hash(booking: dict) -> str:
    """Compute SHA256 hash of critical booking fields."""
    critical_data = {
        'title': booking.get('title'),
        'status': booking.get('status'),
        'formattedName': booking.get('formattedName'),
        'project': booking.get('properties', {}).get('project', {}).get('formattedName'),
        'resource': booking.get('properties', {}).get('resource', {}).get('formattedName')
    }
    json_str = json.dumps(critical_data, sort_keys=True)
    return hashlib.sha256(json_str.encode()).hexdigest()
```

**Storage**: Store hash in WorklistItem.notes field or create separate tracking table (decision needed)

---

### D002: API Contract Documentation

**File**: `contracts/calpendo-api.md`

**Endpoint Reference**:

#### 1. Query Bookings
```
GET {base_url}/webdav/q/Calpendo.Booking/{query}
Authorization: Basic {base64(username:password)}

Query Syntax:
AND/dateRange.start/GE/{YYYYMMDD-HHMM}/dateRange.start/LT/{YYYYMMDD-HHMM}
OR/resource.name/EQ/{resource1}/resource.name/EQ/{resource2}

Response:
{
  "biskits": [
    {
      "id": 12345,
      "formattedName": "[2025-02-12 10:00:00.0, 2025-02-12 11:00:00.0]",
      "title": "SUB001 - John Doe",
      "status": "Approved",
      "biskitType": "MRIScan"
    }
  ]
}
```

#### 2. Get Booking Details
```
GET {base_url}/webdav/b/Calpendo.Booking/{booking_id}
Authorization: Basic {base64(username:password)}

Response:
{
  "id": 12345,
  "properties": {
    "resource": {"formattedName": "3T Diagnostic"},
    "project": {"formattedName": "BRISKP (Brain network study)"},
    "durationInMinutes": 60,
    "created": "2025-02-03T20:18Z",
    "modified": "2025-02-04T10:30Z"
  }
}
```

#### 3. Get Extended Details (MRIScan only)
```
GET {base_url}/webdav/q/{biskitType}/id/eq/{booking_id}?paths=resource.name,Operator.name
Authorization: Basic {base64(username:password)}

Response:
{
  "biskits": [
    {
      "Operator.name": {"formattedName": "Jane Smith"},
      "resource.name": "3T Diagnostic"
    }
  ]
}
```

**Error Codes**:
- `401 Unauthorized`: Invalid credentials
- `404 Not Found`: Booking ID doesn't exist
- `500 Internal Server Error`: Calpendo service issue

---

### D003: Plugin Configuration Schema

**File**: `quickstart.md`

**Example Configuration**:
```json
{
  "data_sources": [
    {
      "name": "calpendo_3t",
      "type": "calpendo",
      "enabled": true,
      "sync_interval": 300,
      "operation_interval": {
        "start_time": [6, 0],
        "end_time": [20, 0]
      },
      "config": {
        "base_url": "https://sfc-calgary.calpendo.com",
        "resources": ["3T Diagnostic"],
        "status_filter": "Approved",
        "lookback_multiplier": 2,
        "timezone": "America/Edmonton"
      },
      "field_mapping": {
        "title": {
          "_extract": {
            "patient_id": {"pattern": "^([A-Z0-9]+)", "group": 1},
            "patient_name": {"pattern": " - (.+)$", "group": 1}
          }
        },
        "project.formattedName": {
          "_extract": {
            "study_description": {"pattern": "^([^(]+)", "group": 1}
          }
        },
        "formattedName": {
          "_extract": {
            "scheduled_start_date": {"pattern": "^\\[([0-9-]+)", "group": 1},
            "scheduled_start_time": {"pattern": "([0-9:]+\\.[0-9])", "group": 1}
          }
        },
        "resource.formattedName": "modality",
        "status": "performed_procedure_step_status",
        "durationInMinutes": "scheduled_procedure_step_duration"
      }
    }
  ]
}
```

**Environment Variables**:
```bash
CALPENDO_API_URL=https://sfc-calgary.calpendo.com
CALPENDO_USERNAME=your_username
CALPENDO_PASSWORD=your_password
```

**Configuration Fields**:
- `base_url`: Calpendo server URL (can override env var)
- `resources`: List of resource names to sync (e.g., ["3T Diagnostic", "EEG"])
- `status_filter`: Only sync bookings with this status (optional)
- `lookback_multiplier`: Rolling window multiplier (default: 2)
- `timezone`: Timezone for timestamp parsing (default: "America/Edmonton")

**Field Mapping Special Keys**:
- `_extract`: Nested dict with regex patterns for field extraction
  - `pattern`: Regex pattern (use `\\` for escaping in JSON)
  - `group`: Capture group number (default: 0 = full match)
- Direct string value: Simple field mapping without extraction

---

### D004: Update Agent Context

**Action**: Run `.specify/scripts/bash/update-agent-context.sh claude`

**Expected Changes**:
- Add `requests` to technology list
- Add `pytz` to technology list
- Document Calpendo plugin in project context
- Link to spec and plan files

---

## Phase 2: Implementation Tasks

**Note**: Detailed tasks will be generated by `/speckit.tasks` command (not part of this plan).

**Task Categories** (preview):

1. **T001-T005**: Core plugin implementation
   - CalendoPlugin class scaffolding
   - validate_config() implementation
   - fetch_entries() implementation
   - Regex extraction utilities
   - Timezone conversion utilities

2. **T006-T010**: API integration
   - Booking query construction
   - HTTP request handling with error recovery
   - Parallel detail fetching (ThreadPoolExecutor)
   - Response parsing and validation
   - Change detection (hashing)

3. **T011-T015**: Data transformation
   - Status mapping (Calpendo → DICOM)
   - Field extraction (regex patterns)
   - WorklistItem construction
   - Rolling window logic
   - Cancelled booking handling

4. **T016-T020**: Testing
   - Unit tests (regex extraction, timezone conversion)
   - Mock API responses fixture
   - Integration tests (full sync workflow)
   - Error handling tests
   - Performance tests (parallel fetching)

5. **T021-T025**: Documentation & deployment
   - Configuration examples
   - Quickstart guide
   - API troubleshooting guide
   - Plugin registration
   - End-to-end testing

---

## Implementation Notes

### Critical Path
1. Research Phase → API contract understanding
2. Regex extraction utilities → Required for all transformations
3. Rolling window logic → Core sync strategy
4. Change detection → Prevents unnecessary DB writes
5. Integration tests → Validates end-to-end workflow

### Risk Mitigation
- **API changes**: Document exact API version/behavior in contracts
- **Regex fragility**: Provide clear error messages, fallback to original values
- **Timezone bugs**: Extensive unit tests for DST transitions
- **Performance**: ThreadPoolExecutor limits (max_workers=5), timeouts on all requests

### Dependencies on Existing Code
- `DataSourcePlugin` interface (no changes needed)
- `PLUGIN_REGISTRY` auto-discovery (automatic)
- `sync_data_source_repeatedly()` orchestration in run.py (no changes needed)
- `WorklistItem` model (no schema changes)

### Post-Implementation
- Monitor API rate limits (Calpendo may have throttling)
- Tune `lookback_multiplier` based on booking modification patterns
- Consider adding `modified` timestamp tracking if Calpendo API updated
- Evaluate need for booking conflict detection (overlapping times)

---

## Validation Checklist

**Before proceeding to `/speckit.tasks`**:

- [ ] All NEEDS CLARIFICATION resolved in research.md
- [ ] API contract documented with example requests/responses
- [ ] Data model transformations defined with examples
- [ ] Configuration schema validated with real JSON
- [ ] Error handling patterns documented
- [ ] Constitution check re-evaluated (post-design)
- [ ] Agent context updated with new technologies

**Post-Design Constitution Re-check**:
- ✅ Minimalist Dependencies: `requests` and `pytz` approved, no additional deps
- ✅ CLI-First: No CLI changes, works with existing commands
- ✅ Data Integrity: Change detection, audit trail preservation, logging
- ✅ Testing: Test strategy defined (unit, integration, mocks)
- ✅ Observability: Structured logging with source prefixes

**Status**: READY FOR TASK BREAKDOWN
