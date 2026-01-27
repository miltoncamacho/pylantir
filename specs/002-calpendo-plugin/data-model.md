# Data Model: Calpendo Data Source Plugin

**Feature**: 002-calpendo-plugin  
**Date**: 2026-01-27  
**Purpose**: Define data entities, transformations, and mappings between Calpendo bookings and DICOM worklist items

---

## Entity Overview

```
Calpendo Booking (API Response)
         ↓
   Transformation Layer
   (regex, timezone, mapping)
         ↓
   WorklistItem (Database)
```

---

## Source Entity: Calpendo Booking

**Source**: Calpendo API `/webdav/b/Calpendo.Booking/{id}`  
**Format**: JSON response  
**Lifecycle**: Fetched during sync, transformed, discarded (not persisted)

### Core Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `id` | int | `12345` | Unique booking identifier |
| `formattedName` | str | `"[2025-02-12 10:00:00.0, 2025-02-12 11:00:00.0]"` | Date/time range (Mountain Time) |
| `title` | str | `"SUB001 - John Doe"` | Subject identifier (composite field) |
| `status` | str | `"Approved"` | Booking status |
| `biskitType` | str | `"MRIScan"` | Booking type |
| `created` | str | `"2025-02-03T20:18Z"` | Creation timestamp (UTC) |
| `properties` | dict | (see below) | Nested booking details |

### Nested Properties

| Field Path | Type | Example | Description |
|------------|------|---------|-------------|
| `properties.resource.formattedName` | str | `"3T Diagnostic"` | Scanner/equipment name |
| `properties.resource.id` | int | `789` | Resource ID |
| `properties.project.formattedName` | str | `"BRISKP (Brain network models...)"` | Study name with description |
| `properties.project.id` | int | `456` | Project ID |
| `properties.booker.formattedName` | str | `"Dr. Smith"` | Person who created booking |
| `properties.owner.formattedName` | str | `"Dr. Jones"` | Booking owner |
| `properties.durationInMinutes` | int | `60` | Booking duration |
| `properties.modified` | str | `"2025-02-04T10:30Z"` | Last modification timestamp |
| `properties.description` | str | `"T1 weighted scan"` | Optional booking notes |
| `properties.cancelled` | bool | `false` | Cancellation flag |
| `properties.cancellationReason` | str | `null` | Reason for cancellation |
| `properties.Operator.name` (MRI only) | str | `"Jane Smith"` | MRI operator name |

---

## Transformation Layer

### 1. Regex Field Extraction

**Purpose**: Extract multiple subfields from composite Calpendo fields

#### Title Extraction
**Input**: `"SUB001 - John Doe"`  
**Pattern Config**:
```json
{
  "title": {
    "_extract": {
      "patient_id": {"pattern": "^([A-Z0-9]+)", "group": 1},
      "patient_name": {"pattern": " - (.+)$", "group": 1}
    }
  }
}
```
**Output**:
- `patient_id`: `"SUB001"`
- `patient_name`: `"John Doe"`

**Edge Cases**:
- Missing separator: `"SUB001"` → `patient_id="SUB001"`, `patient_name=None` (fallback to patient_id)
- Extra hyphens: `"SUB001 - Jane Doe-Smith"` → `patient_name="Jane Doe-Smith"` (greedy match)

#### Study Name Extraction
**Input**: `"BRISKP (Brain network models for understanding Risk)"`  
**Pattern Config**:
```json
{
  "project.formattedName": {
    "_extract": {
      "study_description": {"pattern": "^([^(]+)", "group": 1}
    }
  }
}
```
**Output**:
- `study_description`: `"BRISKP "` (note trailing space, stripped during processing)

#### DateTime Range Extraction
**Input**: `"[2025-02-12 10:00:00.0, 2025-02-12 11:00:00.0]"`  
**Pattern Config**:
```json
{
  "formattedName": {
    "_extract": {
      "start_datetime": {"pattern": "^\\[([^,]+)", "group": 1},
      "end_datetime": {"pattern": ", ([^\\]]+)", "group": 1}
    }
  }
}
```
**Output**:
- `start_datetime`: `"2025-02-12 10:00:00.0"`
- `end_datetime`: `"2025-02-12 11:00:00.0"`

**Post-processing**: Parse strings to datetime objects, convert timezone

---

### 2. Timezone Conversion

**Flow**:
```
Calpendo formattedName (Mountain Time string)
    ↓ parse with datetime.strptime()
Naive datetime object
    ↓ pytz.localize(mt_tz)
Timezone-aware datetime (Mountain Time)
    ↓ .astimezone(pytz.UTC)
UTC datetime
    ↓ .date(), .time()
WorklistItem.scheduled_start_date, scheduled_start_time
```

**Example**:
```python
# Input
formatted_name = "[2025-02-12 10:00:00.0, 2025-02-12 11:00:00.0]"

# Extraction
start_str = "2025-02-12 10:00:00.0"

# Parse
dt_naive = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S.%f')
# → datetime(2025, 2, 12, 10, 0, 0, 0)

# Localize to Mountain Time
mt_tz = pytz.timezone('America/Edmonton')
dt_mt = mt_tz.localize(dt_naive)
# → datetime(2025, 2, 12, 10, 0, 0, tzinfo=<DstTzInfo 'America/Edmonton' MST-1 day, 17:00:00 STD>)

# Convert to UTC
dt_utc = dt_mt.astimezone(pytz.UTC)
# → datetime(2025, 2, 12, 17, 0, 0, tzinfo=<UTC>)

# Store
scheduled_start_date = dt_utc.date()  # 2025-02-12
scheduled_start_time = dt_utc.time()  # 17:00:00
```

**DST Handling**:
- Spring forward (Mar 9, 2025, 2:00 AM → 3:00 AM): pytz raises AmbiguousTimeError for 2:00-3:00 AM
- Fall back (Nov 2, 2025, 2:00 AM → 1:00 AM): pytz raises NonExistentTimeError for 1:00-2:00 AM
- **Mitigation**: Bookings unlikely during 2:00-3:00 AM transition window; log error and skip if encountered

---

### 3. Status Mapping

**Calpendo → DICOM Status**:

| Calpendo Status | DICOM Status | Notes |
|-----------------|--------------|-------|
| `"Approved"` | `"SCHEDULED"` | Ready for imaging |
| `"In Progress"` | `"IN_PROGRESS"` | Currently scanning |
| `"Completed"` | `"COMPLETED"` | Scan finished |
| `"Cancelled"` | `"DISCONTINUED"` | Booking cancelled |
| `"Pending"` | `"SCHEDULED"` | Default for unconfirmed bookings |
| `(unknown)` | `"SCHEDULED"` | Fallback for unmapped statuses |

**Implementation**:
```python
STATUS_MAPPING = {
    'Approved': 'SCHEDULED',
    'In Progress': 'IN_PROGRESS',
    'Completed': 'COMPLETED',
    'Cancelled': 'DISCONTINUED',
    'Pending': 'SCHEDULED'
}

def map_status(calpendo_status: str) -> str:
    dicom_status = STATUS_MAPPING.get(calpendo_status, 'SCHEDULED')
    if calpendo_status not in STATUS_MAPPING:
        logger.warning(f"Unknown Calpendo status '{calpendo_status}', defaulting to SCHEDULED")
    return dicom_status
```

---

### 4. Resource/Modality Mapping

**Examples**:

| Calpendo Resource | DICOM Modality | Mapping Strategy |
|-------------------|----------------|------------------|
| `"3T Diagnostic"` | `"MR"` | Prefix match on "3T" → MR |
| `"EEG"` | `"EEG"` | Direct match |
| `"Mock Scanner"` | `"OT"` (Other) | Default fallback |

**Configuration**:
```json
{
  "resource_modality_mapping": {
    "3T": "MR",
    "EEG": "EEG",
    "Mock": "OT"
  }
}
```

**Algorithm**:
```python
def map_resource_to_modality(resource_name: str, mapping: dict) -> str:
    """Prefix match for resource → modality mapping."""
    for prefix, modality in mapping.items():
        if resource_name.startswith(prefix):
            return modality
    return 'OT'  # Default: Other
```

---

## Target Entity: WorklistItem

**Storage**: SQLite database via SQLAlchemy ORM  
**Schema**: Existing model (no changes)  
**Lifecycle**: INSERT (new booking), UPDATE (changed booking), soft-delete (mark as DISCONTINUED)

### Field Mappings

| WorklistItem Field | Source | Transformation | Example Value |
|-------------------|--------|----------------|---------------|
| `study_instance_uid` | Generated | `uuid.uuid4()` | `"1.2.840.113619.2.55.3..."` |
| `patient_name` | `title` | Regex extract → DICOM name format | `"Doe^John"` |
| `patient_id` | `title` | Regex extract | `"SUB001"` |
| `patient_birth_date` | N/A | Not available, set to `None` | `None` |
| `patient_sex` | N/A | Not available, default to `'O'` (Other) | `'O'` |
| `accession_number` | `id` | Prefix + booking ID | `"CAL12345"` |
| `modality` | `resource.formattedName` | Resource mapping | `"MR"` |
| `scheduled_start_date` | `formattedName` | Extract + timezone convert | `date(2025, 2, 12)` |
| `scheduled_start_time` | `formattedName` | Extract + timezone convert | `time(17, 0, 0)` |
| `performed_procedure_step_status` | `status` | Status mapping | `"SCHEDULED"` |
| `scheduled_procedure_step_description` | `project.formattedName` | Regex extract (study name) | `"BRISKP"` |
| `data_source` | Config | Source name from config | `"calpendo_3t"` |
| `notes` | Computed | JSON metadata | `{"calpendo_hash": "abc...", "calpendo_id": 12345}` |

**DICOM Name Format**:
```python
# Calpendo: "John Doe"
# DICOM: "Doe^John"
def format_dicom_name(patient_name: str) -> str:
    """Convert 'First Last' to DICOM 'Last^First' format."""
    parts = patient_name.split(' ', 1)
    if len(parts) == 2:
        return f"{parts[1]}^{parts[0]}"
    else:
        return patient_name  # No space, return as-is
```

---

## Change Detection

### Hash Computation

**Purpose**: Detect changes without relying on Calpendo's `modified` timestamp

**Algorithm**:
```python
import hashlib
import json

def compute_booking_hash(booking: dict) -> str:
    """
    Compute SHA256 hash of critical fields.
    
    Changes to these fields trigger DB update:
    - title (patient info)
    - status
    - formattedName (times)
    - project (study)
    - resource (scanner)
    """
    properties = booking.get('properties', {})
    
    critical_data = {
        'title': booking.get('title'),
        'status': booking.get('status'),
        'formattedName': booking.get('formattedName'),
        'project': properties.get('project', {}).get('formattedName'),
        'resource': properties.get('resource', {}).get('formattedName')
    }
    
    json_str = json.dumps(critical_data, sort_keys=True)
    return hashlib.sha256(json_str.encode()).hexdigest()
```

**Storage** (in `WorklistItem.notes`):
```json
{
  "calpendo_hash": "a3f5b2...",
  "calpendo_id": 12345,
  "last_synced": "2026-01-27T17:00:00Z",
  "original_title": "SUB001 - John Doe"
}
```

### Sync States

| State | Condition | Action |
|-------|-----------|--------|
| **New** | Booking ID not in DB | INSERT new WorklistItem |
| **Changed** | Hash differs from stored hash | UPDATE WorklistItem fields |
| **Unchanged** | Hash matches stored hash | SKIP (no DB write) |
| **Missing** | In DB but not in fetch results | UPDATE status to `DISCONTINUED` |

**Cancelled Booking Handling**:
```python
# Booking exists in DB but not returned from Calpendo
if existing_item and existing_item.performed_procedure_step_status != 'DISCONTINUED':
    existing_item.performed_procedure_step_status = 'DISCONTINUED'
    notes = json.loads(existing_item.notes or '{}')
    notes['cancelled_at'] = datetime.now(pytz.UTC).isoformat()
    notes['cancellation_reason'] = 'Booking removed from Calpendo'
    existing_item.notes = json.dumps(notes)
    logger.warning(f"Marked booking {calpendo_id} as DISCONTINUED (disappeared from Calpendo)")
```

---

## Validation Rules

### Required Fields (cannot be None)

- `patient_id`: Extracted from `title`
- `scheduled_start_date`: Extracted from `formattedName`
- `scheduled_start_time`: Extracted from `formattedName`

**Validation**:
```python
if not patient_id:
    logger.error(f"Missing patient_id for booking {booking_id}, skipping")
    return None

if not scheduled_start_date or not scheduled_start_time:
    logger.error(f"Missing start date/time for booking {booking_id}, skipping")
    return None
```

### Optional Fields (fallback allowed)

- `patient_name`: Fallback to `patient_id` if extraction fails
- `study_description`: Fallback to empty string
- `modality`: Fallback to `'OT'` (Other)
- `patient_birth_date`: Always `None` (not available from Calpendo)
- `patient_sex`: Always `'O'` (Other, not available)

---

## Example Transformation

### Input (Calpendo API Response)

```json
{
  "id": 12345,
  "formattedName": "[2025-02-12 10:00:00.0, 2025-02-12 11:00:00.0]",
  "title": "SUB001 - John Doe",
  "status": "Approved",
  "biskitType": "MRIScan",
  "properties": {
    "resource": {"formattedName": "3T Diagnostic", "id": 789},
    "project": {"formattedName": "BRISKP (Brain network models)", "id": 456},
    "durationInMinutes": 60,
    "created": "2025-02-03T20:18Z",
    "modified": "2025-02-04T10:30Z"
  }
}
```

### Configuration

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
    }
  },
  "resource_modality_mapping": {
    "3T": "MR"
  }
}
```

### Output (WorklistItem)

```python
WorklistItem(
    study_instance_uid="1.2.840.113619.2.55.3.12345.1234567890",
    patient_name="Doe^John",  # DICOM format
    patient_id="SUB001",
    patient_birth_date=None,
    patient_sex="O",
    accession_number="CAL12345",
    modality="MR",
    scheduled_start_date=date(2025, 2, 12),  # UTC date
    scheduled_start_time=time(17, 0, 0),     # UTC time (10:00 MT → 17:00 UTC)
    performed_procedure_step_status="SCHEDULED",
    scheduled_procedure_step_description="BRISKP",
    data_source="calpendo_3t",
    notes='{"calpendo_hash": "a3f5b2...", "calpendo_id": 12345, ...}'
)
```

**Timezone Conversion Detail**:
- Calpendo: `2025-02-12 10:00:00.0` (Mountain Time)
- Localized: `2025-02-12 10:00:00 MST` (UTC-7)
- Converted: `2025-02-12 17:00:00 UTC`
- Stored: `date(2025, 2, 12)` + `time(17, 0, 0)`

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     Calpendo API                                │
│  GET /webdav/q/Calpendo.Booking/AND/dateRange.start/...        │
└─────────────────────┬───────────────────────────────────────────┘
                      │ JSON response
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                 CalendoPlugin.fetch_entries()                   │
│                                                                 │
│  1. Query bookings in rolling window                           │
│  2. Parallel fetch booking details (ThreadPoolExecutor)        │
│  3. For each booking:                                          │
│     a. Extract fields via regex                                │
│     b. Convert timezones (MT → UTC)                            │
│     c. Map status (Calpendo → DICOM)                           │
│     d. Compute hash                                            │
│  4. Compare with existing DB records                           │
│  5. Return list of WorklistItem objects                        │
└─────────────────────┬───────────────────────────────────────────┘
                      │ List[WorklistItem]
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│            sync_data_source_repeatedly() (run.py)               │
│                                                                 │
│  For each WorklistItem:                                        │
│    - Check if exists in DB (by accession_number)               │
│    - INSERT if new                                             │
│    - UPDATE if hash changed                                    │
│    - SKIP if unchanged                                         │
│  Mark missing bookings as DISCONTINUED                         │
└─────────────────────┬───────────────────────────────────────────┘
                      │ DB operations
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SQLite Database                               │
│                    (WorklistItem table)                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Summary

**Entities**:
1. **CalendoBooking** (transient): API response, transformed and discarded
2. **WorklistItem** (persistent): Database record, DICOM-compliant

**Transformations**:
1. **Regex extraction**: Composite fields → subfields
2. **Timezone conversion**: Mountain Time → UTC
3. **Status mapping**: Calpendo statuses → DICOM statuses
4. **Resource mapping**: Scanner names → DICOM modalities

**Change Detection**:
- SHA256 hash of critical fields
- Stored in WorklistItem.notes as JSON
- Enables update detection without relying on Calpendo's `modified` timestamp

**Validation**:
- Required: patient_id, scheduled_start_date/time
- Optional with fallbacks: patient_name, study_description, modality
- Not available: patient_birth_date, patient_sex (defaults used)
