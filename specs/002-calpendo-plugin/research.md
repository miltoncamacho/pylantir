# Research: Calpendo Data Source Plugin

**Feature**: 002-calpendo-plugin  
**Date**: 2026-01-27  
**Status**: Complete

## Overview

This document contains research findings for implementing the Calpendo data source plugin, resolving all technical unknowns identified in the implementation plan.

---

## R001: Calpendo API Deep Dive

### API Architecture

**Base Endpoint**: `{base_url}/webdav/q/Calpendo.Booking/{query}`

**Authentication**: HTTP Basic Authentication
```python
import requests
auth = (username, password)
response = requests.get(url, auth=auth)
```

### Query Language

Calpendo uses URL path-based query syntax:

**Date Range Query**:
```
AND/dateRange.start/GE/20250212-1000/dateRange.start/LT/20250212-1800
```
- `AND`: Boolean operator
- `dateRange.start`: Field to query
- `GE`: Greater than or equal
- `LT`: Less than
- Date format: `YYYYMMDD-HHMM`

**Resource Filter**:
```
OR/resource.name/EQ/3T%20Diagnostic/resource.name/EQ/EEG
```
- `OR`: Boolean operator for multiple values
- `resource.name`: Field to filter
- `EQ`: Equals
- Values: URL-encoded resource names

**Combined Query**:
```
AND/dateRange.start/GE/{start}/dateRange.start/LT/{end}/OR/resource.name/EQ/{res1}/resource.name/EQ/{res2}
```

### Response Format

**Basic Booking List**:
```json
{
  "biskits": [
    {
      "id": 12345,
      "formattedName": "[2025-02-12 10:00:00.0, 2025-02-12 11:00:00.0]",
      "title": "SUB001 - John Doe",
      "status": "Approved",
      "biskitType": "MRIScan",
      "created": "2025-02-03T20:18Z"
    }
  ]
}
```

**Detailed Booking** (`/webdav/b/Calpendo.Booking/{id}`):
```json
{
  "id": 12345,
  "formattedName": "[2025-02-12 10:00:00.0, 2025-02-12 11:00:00.0]",
  "title": "SUB001 - John Doe",
  "status": "Approved",
  "properties": {
    "resource": {
      "formattedName": "3T Diagnostic",
      "id": 789
    },
    "project": {
      "formattedName": "BRISKP (Brain network models for understanding Risk)",
      "id": 456
    },
    "booker": {"formattedName": "Dr. Smith"},
    "owner": {"formattedName": "Dr. Jones"},
    "durationInMinutes": 60,
    "created": "2025-02-03T20:18Z",
    "modified": "2025-02-04T10:30Z",
    "description": "T1 weighted scan",
    "cancelled": false,
    "cancellationReason": null
  }
}
```

**Extended Details** (MRIScan with operator):
```
GET /webdav/q/MRIScan/id/eq/12345?paths=resource.name,Operator.name,staffConformation

{
  "biskits": [
    {
      "resource.name": "3T Diagnostic",
      "Operator.name": {"formattedName": "Jane Smith", "id": 101},
      "staffConformation": "Confirmed"
    }
  ]
}
```

### API Limitations

**No Modification Timestamp Queries**:
- Cannot query by `modified` date directly
- Must fetch all bookings in date range, then detect changes locally

**No Deletion Events**:
- No API to query deleted/cancelled bookings
- Must compare current results with DB to detect disappearances

**Rate Limiting**:
- Not documented, assume conservative limits
- Use parallel requests sparingly (max 5 concurrent)

### Parallel Request Pattern

From `example_for_calpendo.py`:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

bookings = fetch_bookings(base_url, auth, start_date, end_date, resources)

with ThreadPoolExecutor(max_workers=5) as executor:
    future_to_booking = {
        executor.submit(fetch_booking_details, base_url, auth, booking['id'], booking['biskitType']): booking
        for booking in bookings['biskits']
    }
    
    for future in as_completed(future_to_booking):
        booking = future_to_booking[future]
        try:
            detailed_booking = future.result()
            # Process detailed_booking
        except Exception as e:
            logger.error(f"Error fetching details for booking {booking['id']}: {e}")
            # Continue with other bookings
```

**Decision**: Use this pattern for fetching booking details (scales to 50+ bookings efficiently).

---

## R002: Rolling Window Sync Strategy

### Algorithm

**Window Size Calculation**:
```python
from datetime import datetime, timedelta
import pytz

def calculate_sync_window(sync_interval: int, lookback_multiplier: int = 2):
    """
    Calculate the time window for fetching bookings.
    
    Args:
        sync_interval: Seconds between sync cycles (e.g., 300)
        lookback_multiplier: Safety margin multiplier (default: 2)
    
    Returns:
        (window_start, window_end): UTC datetime objects
    """
    utc = pytz.UTC
    now = datetime.now(utc)
    
    # Look back: sync_interval * multiplier
    lookback_seconds = sync_interval * lookback_multiplier
    window_start = now - timedelta(seconds=lookback_seconds)
    
    # Look ahead: next 24 hours (catch future bookings)
    window_end = now + timedelta(days=1)
    
    return window_start, window_end
```

**Rationale**:
- **Lookback**: 2x safety margin catches bookings created/modified between sync cycles
- **Lookahead**: Fetching next-day bookings prepares worklist in advance
- **Configurable**: `lookback_multiplier` allows tuning per deployment

**Example** (300s interval, 2x multiplier):
- Sync runs every 5 minutes
- Fetches bookings from 10 minutes ago to 24 hours ahead
- Catches late updates from previous cycle

### Change Detection

**Hash Computation**:
```python
import hashlib
import json

def compute_booking_hash(booking: dict) -> str:
    """
    Compute SHA256 hash of critical booking fields.
    
    Changes to these fields require DB update:
    - title (patient ID/name)
    - status (Approved, Cancelled, etc.)
    - formattedName (start/end times)
    - project (study name)
    - resource (scanner type)
    """
    properties = booking.get('properties', {})
    
    critical_data = {
        'title': booking.get('title'),
        'status': booking.get('status'),
        'formattedName': booking.get('formattedName'),
        'project': properties.get('project', {}).get('formattedName'),
        'resource': properties.get('resource', {}).get('formattedName')
    }
    
    # Sort keys for consistent hashing
    json_str = json.dumps(critical_data, sort_keys=True)
    return hashlib.sha256(json_str.encode()).hexdigest()
```

**Sync Logic Pseudocode**:
```python
def sync_bookings(window_start, window_end, existing_records):
    # 1. Fetch bookings from Calpendo in time window
    calpendo_bookings = fetch_bookings_in_window(window_start, window_end)
    
    # 2. Build set of fetched booking IDs
    fetched_ids = {b['id'] for b in calpendo_bookings}
    
    # 3. Process each fetched booking
    for booking in calpendo_bookings:
        booking_id = booking['id']
        new_hash = compute_booking_hash(booking)
        
        existing = existing_records.get(booking_id)
        
        if existing is None:
            # New booking → INSERT
            insert_booking(booking)
            logger.info(f"[calpendo] New booking {booking_id}: {booking['title']}")
        
        elif existing.hash != new_hash:
            # Changed booking → UPDATE
            update_booking(booking)
            logger.info(f"[calpendo] Updated booking {booking_id}: {booking['title']}")
        
        else:
            # Unchanged → SKIP
            logger.debug(f"[calpendo] No changes for booking {booking_id}")
    
    # 4. Handle missing bookings (cancelled or deleted)
    existing_ids = set(existing_records.keys())
    missing_ids = existing_ids - fetched_ids
    
    for booking_id in missing_ids:
        existing = existing_records[booking_id]
        
        if existing.status != 'DISCONTINUED':
            # Mark as cancelled (preserve history)
            mark_as_cancelled(booking_id)
            logger.warning(f"[calpendo] Booking {booking_id} disappeared, marking as cancelled")
```

**Storage Decision**: Store hash in `WorklistItem.notes` field as JSON:
```python
notes = {
    'calpendo_hash': 'abc123...',
    'calpendo_id': 12345,
    'last_synced': '2026-01-27T10:30:00Z'
}
worklist_item.notes = json.dumps(notes)
```

---

## R003: Regex Field Extraction Architecture

### Configuration Structure

**Nested Extraction in field_mapping**:
```json
{
  "field_mapping": {
    "title": {
      "_extract": {
        "patient_id": {
          "pattern": "^([A-Z0-9]+)",
          "group": 1
        },
        "patient_name": {
          "pattern": " - (.+)$",
          "group": 1
        }
      }
    },
    "resource.formattedName": "modality"
  }
}
```

**Interpretation**:
- If field value is **dict with `_extract` key**: Apply regex extraction
- If field value is **string**: Direct mapping (simple rename)
- `_extract` dict contains multiple target fields, each with regex config

### Extraction Implementation

```python
import re
from typing import Dict, Any, Optional

def extract_fields(source_value: str, extraction_config: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """
    Apply multiple regex patterns to extract subfields from source value.
    
    Args:
        source_value: Original field value (e.g., "SUB001 - John Doe")
        extraction_config: Dict of {target_field: {pattern, group}}
    
    Returns:
        Dict of {target_field: extracted_value}
    
    Example:
        source_value = "SUB001 - John Doe"
        extraction_config = {
            "patient_id": {"pattern": "^([A-Z0-9]+)", "group": 1},
            "patient_name": {"pattern": " - (.+)$", "group": 1}
        }
        
        Returns: {"patient_id": "SUB001", "patient_name": "John Doe"}
    """
    extracted = {}
    
    for target_field, regex_config in extraction_config.items():
        pattern = regex_config['pattern']
        group = regex_config.get('group', 0)
        
        try:
            match = re.search(pattern, source_value)
            if match:
                extracted[target_field] = match.group(group).strip()
            else:
                logger.warning(
                    f"Pattern '{pattern}' failed on '{source_value}' "
                    f"for field '{target_field}'"
                )
                extracted[target_field] = None
        
        except re.error as e:
            logger.error(f"Invalid regex pattern '{pattern}': {e}")
            extracted[target_field] = None
        
        except IndexError:
            logger.error(
                f"Capture group {group} not found in pattern '{pattern}' "
                f"(matched: {match.group(0)})"
            )
            extracted[target_field] = None
    
    return extracted
```

### Example Patterns

**Title Extraction** (`"SUB001 - John Doe"`):
```json
{
  "patient_id": {"pattern": "^([A-Z0-9]+)", "group": 1},
  "patient_name": {"pattern": " - (.+)$", "group": 1}
}
```

**Study Name** (`"BRISKP (Brain network models...)"`):
```json
{
  "study_description": {"pattern": "^([^(]+)", "group": 1}
}
```
Result: `"BRISKP "`

**Date/Time** (`"[2025-02-12 10:00:00.0, 2025-02-12 11:00:00.0]"`):
```json
{
  "start_datetime": {"pattern": "^\\[([^,]+)", "group": 1},
  "end_datetime": {"pattern": ", ([^\\]]+)", "group": 1}
}
```
Result: `"2025-02-12 10:00:00.0"`, `"2025-02-12 11:00:00.0"`

**Note**: Escape backslashes in JSON: `\\[` → `\[` in Python regex

### Fallback Strategy

**When extraction fails**:
1. **Log warning** with original value and pattern
2. **Set field to None** (or use fallback value if configured)
3. **Continue processing** other fields
4. **Skip booking** only if required field is None

**Example**:
```python
if extracted['patient_id'] is None:
    logger.error(f"Cannot extract patient_id from '{booking['title']}', skipping booking {booking['id']}")
    continue  # Skip this booking, process next one
```

---

## R004: Timezone Handling Best Practices

### pytz Usage

**Installation**:
```bash
pip install pytz
```

**Basic Conversion**:
```python
import pytz
from datetime import datetime

# Define timezones
mt_tz = pytz.timezone('America/Edmonton')  # Mountain Time
utc_tz = pytz.UTC

# Parse Calpendo timestamp (Mountain Time)
dt_str = "2025-02-12 10:00:00.0"
dt_naive = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S.%f')

# Localize to Mountain Time (handles DST correctly)
dt_mt = mt_tz.localize(dt_naive)

# Convert to UTC for storage
dt_utc = dt_mt.astimezone(utc_tz)

# Store in DB
worklist_item.scheduled_start_date = dt_utc.date()
worklist_item.scheduled_start_time = dt_utc.time()
```

### Daylight Saving Time

**Critical**: Never use `replace(tzinfo=...)`
```python
# ❌ WRONG - loses DST info
dt_naive = datetime(2025, 3, 9, 2, 30)  # During DST transition
dt_wrong = dt_naive.replace(tzinfo=mt_tz)  # Ambiguous time!

# ✅ CORRECT - pytz handles DST
dt_correct = mt_tz.localize(dt_naive, is_dst=None)  # Raises exception if ambiguous
```

**DST Transitions in Mountain Time**:
- Spring forward: 2nd Sunday in March (2:00 AM → 3:00 AM)
- Fall back: 1st Sunday in November (2:00 AM → 1:00 AM)

### formattedName Parsing

**Utility Function**:
```python
def parse_calpendo_datetime_range(formatted_name: str, timezone_str: str = 'America/Edmonton'):
    """
    Parse Calpendo formattedName into start/end datetime objects.
    
    Args:
        formatted_name: "[YYYY-MM-DD HH:MM:SS.f, YYYY-MM-DD HH:MM:SS.f]"
        timezone_str: Timezone name (default: Mountain Time)
    
    Returns:
        (start_utc, end_utc): Tuple of UTC datetime objects
    
    Raises:
        ValueError: If format is invalid
    """
    import re
    from datetime import datetime
    import pytz
    
    # Extract timestamps with regex
    match = re.match(r'\[([^,]+), ([^\]]+)\]', formatted_name)
    if not match:
        raise ValueError(f"Invalid formattedName format: {formatted_name}")
    
    start_str = match.group(1).strip()
    end_str = match.group(2).strip()
    
    # Parse datetime strings
    try:
        start_naive = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S.%f')
        end_naive = datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S.%f')
    except ValueError:
        # Try without microseconds
        start_naive = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S')
        end_naive = datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S')
    
    # Localize to configured timezone
    tz = pytz.timezone(timezone_str)
    start_local = tz.localize(start_naive)
    end_local = tz.localize(end_naive)
    
    # Convert to UTC
    utc = pytz.UTC
    start_utc = start_local.astimezone(utc)
    end_utc = end_local.astimezone(utc)
    
    return start_utc, end_utc
```

**Usage**:
```python
formatted_name = "[2025-02-12 10:00:00.0, 2025-02-12 11:00:00.0]"
start_utc, end_utc = parse_calpendo_datetime_range(formatted_name)

# Store in WorklistItem
worklist_item.scheduled_start_date = start_utc.date()
worklist_item.scheduled_start_time = start_utc.time()
```

### Date Formatting for Calpendo API

**UTC to Calpendo Query Format**:
```python
def format_calpendo_query_date(dt_utc: datetime, timezone_str: str = 'America/Edmonton'):
    """
    Convert UTC datetime to Calpendo query format (YYYYMMDD-HHMM in local time).
    
    Args:
        dt_utc: UTC datetime
        timezone_str: Target timezone for query
    
    Returns:
        String in format "YYYYMMDD-HHMM"
    """
    tz = pytz.timezone(timezone_str)
    dt_local = dt_utc.astimezone(tz)
    return dt_local.strftime('%Y%m%d-%H%M')
```

**Example**:
```python
from datetime import datetime
import pytz

now_utc = datetime.now(pytz.UTC)
query_date = format_calpendo_query_date(now_utc)
# Result: "20260127-1030" (Mountain Time)
```

---

## R005: Error Recovery Patterns

### Connection & HTTP Errors

```python
import requests
from typing import Dict, Any

def fetch_with_retry(
    url: str,
    auth: tuple,
    timeout: int = 30,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Fetch from Calpendo API with retry logic.
    
    Raises:
        PluginConfigError: Invalid credentials (401)
        PluginFetchError: Network or API errors
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, auth=auth, timeout=timeout)
            response.raise_for_status()
            return response.json()
        
        except requests.ConnectionError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Connection error (attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            else:
                raise PluginFetchError(f"Cannot connect to Calpendo after {max_retries} attempts: {e}")
        
        except requests.Timeout:
            if attempt < max_retries - 1:
                logger.warning(f"Timeout (attempt {attempt+1}/{max_retries})")
                continue
            else:
                raise PluginFetchError(f"Calpendo API timeout after {timeout}s")
        
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                raise PluginConfigError("Invalid Calpendo credentials (401 Unauthorized)")
            elif e.response.status_code == 404:
                # Not necessarily an error (booking might be deleted)
                logger.warning(f"Resource not found (404): {url}")
                return None
            elif e.response.status_code >= 500:
                if attempt < max_retries - 1:
                    logger.warning(f"Server error {e.response.status_code} (attempt {attempt+1}/{max_retries})")
                    time.sleep(5)
                    continue
                else:
                    raise PluginFetchError(f"Calpendo server error: {e}")
            else:
                raise PluginFetchError(f"Calpendo API error: {e}")
        
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}\nResponse: {response.text[:200]}")
            raise PluginFetchError(f"Calpendo returned invalid JSON: {e}")
```

### Partial Failure Handling

**Scenario**: One booking detail fetch fails, others should continue

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_all_booking_details(booking_ids, base_url, auth):
    """
    Fetch details for multiple bookings in parallel.
    
    Returns:
        List of detailed booking dicts (skips failed fetches)
    """
    detailed_bookings = []
    failed_count = 0
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_id = {
            executor.submit(fetch_booking_detail, base_url, auth, bid): bid
            for bid in booking_ids
        }
        
        for future in as_completed(future_to_id):
            booking_id = future_to_id[future]
            try:
                detailed = future.result()
                if detailed is not None:
                    detailed_bookings.append(detailed)
            except Exception as e:
                logger.error(f"Failed to fetch booking {booking_id}: {e}")
                failed_count += 1
                # Continue with other bookings
    
    if failed_count > 0:
        logger.warning(f"Failed to fetch {failed_count} booking details, continuing with {len(detailed_bookings)} successful fetches")
    
    return detailed_bookings
```

### Malformed Data Handling

**Decision Tree**:

```
Booking Processing
├─ Missing required field (patient_id)?
│  ├─ Yes → Log ERROR, skip booking
│  └─ No → Continue
│
├─ Regex extraction failed?
│  ├─ Yes → Log WARNING, use None or fallback
│  └─ No → Continue
│
├─ Invalid timestamp format?
│  ├─ Yes → Log ERROR, skip booking
│  └─ No → Continue
│
└─ Status not in mapping?
   ├─ Yes → Log WARNING, use default (SCHEDULED)
   └─ No → Continue
```

**Implementation**:
```python
def transform_booking_to_worklist(booking: dict, field_mapping: dict) -> Optional[WorklistItem]:
    """
    Transform Calpendo booking to WorklistItem.
    
    Returns:
        WorklistItem or None (if critical errors)
    """
    try:
        # Extract patient_id (required)
        patient_id = extract_field(booking['title'], field_mapping['title']['_extract']['patient_id'])
        if not patient_id:
            logger.error(f"Cannot extract patient_id from '{booking['title']}', skipping booking {booking['id']}")
            return None
        
        # Extract start/end times (required)
        try:
            start_utc, end_utc = parse_calpendo_datetime_range(booking['formattedName'])
        except ValueError as e:
            logger.error(f"Invalid timestamp format in booking {booking['id']}: {e}")
            return None
        
        # Extract optional fields (use defaults if missing)
        patient_name = extract_field(booking['title'], field_mapping['title']['_extract']['patient_name'])
        if not patient_name:
            logger.warning(f"Could not extract patient_name from '{booking['title']}', using patient_id")
            patient_name = patient_id
        
        # Map status (use default if unknown)
        status = booking.get('status', 'Unknown')
        dicom_status = STATUS_MAPPING.get(status, 'SCHEDULED')
        if status not in STATUS_MAPPING:
            logger.warning(f"Unknown status '{status}' for booking {booking['id']}, defaulting to SCHEDULED")
        
        # Create WorklistItem
        return WorklistItem(
            patient_id=patient_id,
            patient_name=patient_name,
            scheduled_start_date=start_utc.date(),
            scheduled_start_time=start_utc.time(),
            performed_procedure_step_status=dicom_status,
            # ... other fields
        )
    
    except Exception as e:
        logger.error(f"Unexpected error transforming booking {booking.get('id', 'unknown')}: {e}")
        return None
```

---

## Decisions Summary

| Decision Point | Choice | Rationale |
|----------------|--------|-----------|
| **HTTP Client** | `requests` library | Simple, stable, no complex client needed |
| **Sync Strategy** | Rolling window (last N hours) | API lacks modification timestamp queries |
| **Window Size** | `sync_interval * lookback_multiplier` | Configurable safety margin (default 2x) |
| **Change Detection** | SHA256 hash of critical fields | Efficient comparison without storing full booking |
| **Hash Storage** | JSON in `WorklistItem.notes` | No schema changes, flexible metadata |
| **Missing Bookings** | Mark as cancelled (preserve history) | Audit trail compliance |
| **Regex Extraction** | Nested in field_mapping with `_extract` key | Plugin-specific config, flexible patterns |
| **Timezone Library** | `pytz` | Correct DST handling, industry standard |
| **Parallel Requests** | ThreadPoolExecutor (max 5 workers) | Balance performance vs API load |
| **Partial Failures** | Skip failed bookings, log and continue | Resilience over strict consistency |
| **Required Fields** | patient_id, start/end times | Skip booking if extraction fails |
| **Optional Fields** | patient_name, study description | Use fallback values if extraction fails |

---

## Next Steps

1. ✅ Research complete
2. → Proceed to Phase 1: Design & Contracts
3. Create `data-model.md` with entity transformations
4. Create `contracts/calpendo-api.md` with API reference
5. Create `quickstart.md` with configuration examples
6. Update agent context with new dependencies
