# Implementation Tasks: Calpendo Data Source Plugin

**Feature**: 002-calpendo-plugin | **Created**: 2026-01-27
**Prerequisites**: [research.md](research.md), [data-model.md](data-model.md), [contracts/calpendo-api.md](contracts/calpendo-api.md)

## Task Overview

**Total Tasks**: 25
**Estimated Effort**: 16-20 hours
**Critical Path**: T001 → T002 → T006 → T007 → T011 → T012 → T016 → T023

### Task Categories
- **Core Plugin (T001-T005)**: 5 tasks, 4-5 hours
- **API Integration (T006-T010)**: 5 tasks, 3-4 hours
- **Data Transformation (T011-T015)**: 5 tasks, 3-4 hours
- **Testing (T016-T020)**: 5 tasks, 4-5 hours
- **Documentation & Deployment (T021-T025)**: 5 tasks, 2-3 hours

---

## Category 1: Core Plugin Implementation

### T001: Create CalendoPlugin Class Scaffolding
**Priority**: P0 (Critical Path)
**Effort**: 1 hour
**Dependencies**: None

**Description**:
Create the base `CalendoPlugin` class implementing the `DataSourcePlugin` interface. Set up the plugin structure following the REDCapPlugin pattern with configuration validation, error handling, and logging.

**Implementation Steps**:
1. Create `src/pylantir/data_sources/calpendo_plugin.py`
2. Import required dependencies: `requests`, `pytz`, `re`, `hashlib`, `concurrent.futures`
3. Define `CalendoPlugin(DataSourcePlugin)` class
4. Implement `__init__(self, source_name: str, config: dict)` constructor
5. Add logger with prefix `[calpendo:{source_name}]`
6. Store config, source_name, base_url attributes

**Acceptance Criteria**:
- [X] File created at correct path in `data_sources/` directory
- [X] Class inherits from `DataSourcePlugin` ABC
- [X] Constructor accepts `source_name` and `config` parameters
- [X] Logger initialized with correct prefix format
- [X] Basic imports present (requests, pytz, re, hashlib, ThreadPoolExecutor)
- [X] No syntax errors, passes `python -m py_compile`

**Testing**:
- Unit test: Import CalendoPlugin and instantiate with minimal config
- Verify logger prefix format

---

### T002: Implement Configuration Validation
**Priority**: P0 (Critical Path)
**Effort**: 1.5 hours
**Dependencies**: T001

**Description**:
Implement the `validate_config()` method to check for required configuration fields, validate environment variables for credentials, and ensure field_mapping structure is correct.

**Implementation Steps**:
1. Implement `validate_config(self) -> None` method
2. Check required fields: `base_url`, `resources` (list), `field_mapping` (dict)
3. Validate environment variables: `CALPENDO_USERNAME`, `CALPENDO_PASSWORD`
4. Validate optional fields: `status_filter` (str), `lookback_multiplier` (int/float), `timezone` (str)
5. Validate field_mapping structure: check for `_extract` nested dicts with `pattern` and `group` keys
6. Raise `PluginConfigError` with descriptive messages for validation failures
7. Log successful validation with configuration summary

**Acceptance Criteria**:
- [X] Method raises `PluginConfigError` when `base_url` missing
- [X] Method raises `PluginConfigError` when `resources` is not a list or empty
- [X] Method raises `PluginConfigError` when environment variables missing
- [X] Method validates optional fields have correct types
- [X] Method validates `_extract` patterns have required keys (`pattern`)
- [X] Method logs INFO message on successful validation
- [X] All error messages are descriptive and actionable

**Testing**:
- Unit test: Valid config passes validation
- Unit test: Missing base_url raises PluginConfigError
- Unit test: Empty resources list raises PluginConfigError
- Unit test: Missing env vars raises PluginConfigError
- Unit test: Invalid lookback_multiplier type raises error
- Unit test: Malformed _extract pattern raises error

**Code Template**:
```python
def validate_config(self) -> None:
    """Validate plugin configuration and environment variables."""
    # Check required config fields
    if "base_url" not in self.config:
        raise PluginConfigError("Missing required field: base_url")

    if "resources" not in self.config or not isinstance(self.config["resources"], list):
        raise PluginConfigError("'resources' must be a non-empty list")

    # Check environment variables
    if not os.getenv("CALPENDO_USERNAME") or not os.getenv("CALPENDO_PASSWORD"):
        raise PluginConfigError("CALPENDO_USERNAME and CALPENDO_PASSWORD env vars required")

    # Validate field_mapping structure
    field_mapping = self.config.get("field_mapping", {})
    for target_field, mapping in field_mapping.items():
        if isinstance(mapping, dict) and "_extract" in mapping:
            # Validate extraction pattern structure
            pass

    self.lgr.info(f"Configuration validated: {len(self.config['resources'])} resources")
```

---

### T003: Implement fetch_entries() Main Method
**Priority**: P0 (Critical Path)
**Effort**: 1 hour
**Dependencies**: T001, T002

**Description**:
Implement the main `fetch_entries()` method that orchestrates the full sync workflow: calculate rolling window, fetch bookings, fetch details in parallel, transform to worklist entries, and apply change detection.

**Implementation Steps**:
1. Implement `fetch_entries(self, sync_interval: int) -> List[Dict[str, Any]]` method
2. Calculate rolling window: `start_time = now - (sync_interval * lookback_multiplier)`, `end_time = now + 24h`
3. Call `_fetch_bookings_in_window(start_time, end_time)` to get booking IDs
4. Call `_fetch_booking_details_parallel(booking_ids)` to get full booking data
5. Transform bookings using `_transform_booking_to_entry(booking)` for each booking
6. Apply change detection using `_compute_booking_hash(booking)` and filter unchanged entries
7. Return list of new/modified worklist entry dicts
8. Wrap in try/except to catch and raise `PluginFetchError` on failures

**Acceptance Criteria**:
- [X] Method signature matches DataSourcePlugin interface
- [X] Rolling window calculation uses lookback_multiplier from config
- [X] Method calls helper methods in correct sequence
- [X] Returns list of dicts with worklist fields
- [X] Logs INFO with count of fetched/filtered entries
- [X] Raises PluginFetchError on API failures
- [X] No bookings = empty list (not error)

**Testing**:
- Integration test: Mock API, verify fetch_entries returns correct count
- Unit test: Rolling window calculation with default and custom multipliers
- Integration test: API failure raises PluginFetchError

**Code Template**:
```python
def fetch_entries(self, sync_interval: int) -> List[Dict[str, Any]]:
    """Fetch and transform Calpendo bookings to worklist entries."""
    try:
        # Calculate rolling window
        lookback_multiplier = self.config.get("lookback_multiplier", 2)
        tz = pytz.timezone(self.config.get("timezone", "America/Edmonton"))
        now = datetime.now(tz)
        start_time = now - timedelta(seconds=sync_interval * lookback_multiplier)
        end_time = now + timedelta(hours=24)

        # Fetch bookings
        booking_ids = self._fetch_bookings_in_window(start_time, end_time)
        self.lgr.info(f"Found {len(booking_ids)} bookings in window")

        # Fetch details in parallel
        bookings = self._fetch_booking_details_parallel(booking_ids)

        # Transform and filter
        entries = []
        for booking in bookings:
            entry = self._transform_booking_to_entry(booking)
            if entry:  # Skip invalid bookings
                entries.append(entry)

        self.lgr.info(f"Transformed {len(entries)} valid worklist entries")
        return entries

    except Exception as e:
        self.lgr.error(f"Failed to fetch entries: {e}")
        raise PluginFetchError(f"Calpendo fetch failed: {e}") from e
```

---

### T004: Implement Error Handling Classes
**Priority**: P1
**Effort**: 0.5 hours
**Dependencies**: None

**Description**:
Create custom exception classes for plugin-specific errors following the pattern from REDCapPlugin: `PluginConfigError` for configuration issues and `PluginFetchError` for API/sync failures.

**Implementation Steps**:
1. Check if exceptions exist in `data_sources/base.py` or need to be created
2. If not present, define `PluginConfigError(Exception)` class
3. Define `PluginFetchError(Exception)` class
4. Add docstrings explaining when each exception is raised
5. Update imports in `calpendo_plugin.py`

**Acceptance Criteria**:
- [X] `PluginConfigError` defined with clear docstring
- [X] `PluginFetchError` defined with clear docstring
- [X] Both classes inherit from `Exception`
- [X] CalendoPlugin imports and uses these exceptions
- [X] Error messages include helpful context (e.g., missing field name, API endpoint)

**Testing**:
- Unit test: Raise PluginConfigError and verify exception type
- Unit test: Raise PluginFetchError with message and verify

---

### T005: Implement Logging Infrastructure
**Priority**: P1
**Effort**: 0.5 hours
**Dependencies**: T001

**Description**:
Set up structured logging throughout the plugin with appropriate log levels: DEBUG for API requests/responses, INFO for successful operations, WARNING for missing fields, ERROR for failures.

**Implementation Steps**:
1. Initialize logger in `__init__` with `logging.getLogger(__name__)`
2. Add log prefix with source name: `[calpendo:{source_name}]`
3. Add DEBUG logging for API requests (URL, query parameters)
4. Add INFO logging for successful operations (bookings fetched, entries transformed)
5. Add WARNING logging for skipped bookings (missing fields, regex failures)
6. Add ERROR logging for API failures, auth errors, exceptions

**Acceptance Criteria**:
- [X] Logger initialized with correct prefix format
- [X] All API requests logged at DEBUG level with full URL
- [X] Successful sync operations logged at INFO level
- [X] Missing required fields logged at WARNING level with booking ID
- [X] API failures logged at ERROR level with full exception details
- [X] No print statements in production code (use logging only)

**Testing**:
- Integration test: Capture log output and verify correct levels
- Unit test: Verify logger prefix format

---

## Category 2: API Integration

### T006: Implement Booking Query Construction
**Priority**: P0 (Critical Path)
**Effort**: 1 hour
**Dependencies**: T001

**Description**:
Implement the `_build_booking_query()` method to construct Calpendo WebDAV query strings with date range, resource filters, and status filters following the API syntax from contracts/calpendo-api.md.

**Implementation Steps**:
1. Implement `_build_booking_query(self, start_time: datetime, end_time: datetime) -> str` method
2. Format dates as `YYYYMMDD-HHMM` in Mountain Time
3. Build date range query: `AND/dateRange.start/GE/{start}/dateRange.start/LT/{end}`
4. Add resource filter: `OR/resource.name/EQ/{resource1}/resource.name/EQ/{resource2}`
5. Add status filter if configured: `AND/status/EQ/{status}`
6. Combine query components with proper AND/OR logic
7. Log DEBUG with constructed query string

**Acceptance Criteria**:
- [X] Method returns properly formatted query string
- [X] Date formatting is correct (YYYYMMDD-HHMM)
- [X] Resource filter uses OR logic for multiple resources
- [X] Status filter uses AND logic when present
- [X] Query matches examples in contracts/calpendo-api.md
- [X] Empty resources list returns valid query (all resources)

**Testing**:
- Unit test: Single resource, no status filter
- Unit test: Multiple resources with OR logic
- Unit test: Resources + status filter with AND logic
- Unit test: Date formatting in Mountain Time
- Unit test: Verify query string matches contract examples

**Code Template**:
```python
def _build_booking_query(self, start_time: datetime, end_time: datetime) -> str:
    """Construct Calpendo WebDAV query string."""
    # Format dates
    start_str = start_time.strftime("%Y%m%d-%H%M")
    end_str = end_time.strftime("%Y%m%d-%H%M")

    # Date range (AND)
    query_parts = [f"AND/dateRange.start/GE/{start_str}/dateRange.start/LT/{end_str}"]

    # Resource filter (OR)
    resources = self.config.get("resources", [])
    if resources:
        resource_query = "OR/" + "/".join([f"resource.name/EQ/{r}" for r in resources])
        query_parts.append(resource_query)

    # Status filter (AND)
    status_filter = self.config.get("status_filter")
    if status_filter:
        query_parts.append(f"AND/status/EQ/{status_filter}")

    query = "/".join(query_parts)
    self.lgr.debug(f"Built query: {query}")
    return query
```

---

### T007: Implement Booking Fetching
**Priority**: P0 (Critical Path)
**Effort**: 1 hour
**Dependencies**: T006

**Description**:
Implement `_fetch_bookings_in_window()` to execute the booking query and parse the response to extract booking IDs. Handle authentication, HTTP errors, and empty results.

**Implementation Steps**:
1. Implement `_fetch_bookings_in_window(self, start_time: datetime, end_time: datetime) -> List[int]` method
2. Build query using `_build_booking_query(start_time, end_time)`
3. Construct full URL: `{base_url}/webdav/q/Calpendo.Booking/{query}`
4. Create HTTP Basic Auth with username/password from env vars
5. Execute GET request with `requests.get(url, auth=auth, timeout=30)`
6. Parse JSON response and extract booking IDs from `biskits` array
7. Handle HTTP errors (401, 404, 500) with appropriate exceptions
8. Return list of booking IDs

**Acceptance Criteria**:
- [X] Method returns list of integers (booking IDs)
- [X] Authentication uses environment variables
- [X] Request has 30-second timeout
- [X] 401 error raises PluginFetchError with "authentication failed" message
- [X] 500 error raises PluginFetchError with "server error" message
- [X] Empty results return empty list (not error)
- [X] JSON parsing errors are caught and logged

**Testing**:
- Integration test: Mock API returns bookings, verify IDs extracted
- Integration test: Mock 401 error raises PluginFetchError
- Integration test: Mock empty response returns empty list
- Unit test: Verify auth header constructed correctly

**Code Template**:
```python
def _fetch_bookings_in_window(self, start_time: datetime, end_time: datetime) -> List[int]:
    """Query Calpendo for booking IDs in time window."""
    query = self._build_booking_query(start_time, end_time)
    url = f"{self.config['base_url']}/webdav/q/Calpendo.Booking/{query}"

    auth = (os.getenv("CALPENDO_USERNAME"), os.getenv("CALPENDO_PASSWORD"))

    try:
        response = requests.get(url, auth=auth, timeout=30)
        response.raise_for_status()

        data = response.json()
        booking_ids = [b["id"] for b in data.get("biskits", [])]

        self.lgr.debug(f"Fetched {len(booking_ids)} booking IDs")
        return booking_ids

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            raise PluginFetchError("Calpendo authentication failed") from e
        raise PluginFetchError(f"HTTP error: {e}") from e
    except Exception as e:
        raise PluginFetchError(f"Failed to fetch bookings: {e}") from e
```

---

### T008: Implement Booking Detail Fetching
**Priority**: P0 (Critical Path)
**Effort**: 1 hour
**Dependencies**: T007

**Description**:
Implement `_fetch_booking_details()` to retrieve full booking information for a single booking ID, including handling MRIScan biskit type for operator information.

**Implementation Steps**:
1. Implement `_fetch_booking_details(self, booking_id: int) -> dict` method
2. Fetch basic booking: GET `{base_url}/webdav/b/Calpendo.Booking/{booking_id}`
3. Parse response JSON to get booking object
4. Check if `biskitType == "MRIScan"`, if so fetch extended details
5. For MRIScan: GET `{base_url}/webdav/q/MRIScan/id/eq/{booking_id}?paths=resource.name,Operator.name`
6. Merge operator info into booking dict
7. Return complete booking dict
8. Handle 404 errors (booking not found) gracefully

**Acceptance Criteria**:
- [X] Method returns dict with booking fields
- [X] MRIScan bookings include operator information
- [X] Non-MRIScan bookings return basic details only
- [X] 404 errors return None (booking deleted/not found)
- [X] Other HTTP errors raise PluginFetchError
- [X] Timeout set to 10 seconds per request

**Testing**:
- Integration test: Mock API returns basic booking, verify fields
- Integration test: Mock MRIScan booking, verify operator fetched
- Integration test: Mock 404 error returns None
- Unit test: Verify MRIScan detection logic

**Code Template**:
```python
def _fetch_booking_details(self, booking_id: int) -> Optional[dict]:
    """Fetch detailed booking information."""
    url = f"{self.config['base_url']}/webdav/b/Calpendo.Booking/{booking_id}"
    auth = (os.getenv("CALPENDO_USERNAME"), os.getenv("CALPENDO_PASSWORD"))

    try:
        response = requests.get(url, auth=auth, timeout=10)
        if response.status_code == 404:
            self.lgr.warning(f"Booking {booking_id} not found (deleted?)")
            return None
        response.raise_for_status()

        booking = response.json()

        # Fetch operator for MRIScan
        if booking.get("biskitType") == "MRIScan":
            operator = self._fetch_mri_operator(booking_id)
            if operator:
                booking["operator"] = operator

        return booking

    except Exception as e:
        self.lgr.error(f"Failed to fetch booking {booking_id}: {e}")
        raise PluginFetchError(f"Booking detail fetch failed: {e}") from e
```

---

### T009: Implement Parallel Detail Fetching
**Priority**: P1
**Effort**: 0.5 hours
**Dependencies**: T008

**Description**:
Implement `_fetch_booking_details_parallel()` using ThreadPoolExecutor to fetch multiple booking details concurrently with a maximum of 5 workers, matching the pattern from example_for_calpendo.py.

**Implementation Steps**:
1. Implement `_fetch_booking_details_parallel(self, booking_ids: List[int]) -> List[dict]` method
2. Create ThreadPoolExecutor with max_workers=5
3. Use executor.map() to fetch all booking details in parallel
4. Filter out None results (deleted bookings)
5. Log INFO with count of successfully fetched bookings vs failures
6. Return list of booking dicts

**Acceptance Criteria**:
- [X] Uses ThreadPoolExecutor with max 5 workers
- [X] Fetches all bookings in parallel (not sequential)
- [X] None results from deleted bookings are filtered out
- [X] Returns list of valid booking dicts
- [X] Logs success/failure count
- [X] Performance: ~3x faster than sequential for 10+ bookings

**Testing**:
- Integration test: Mock 10 bookings, verify parallel execution
- Performance test: Time parallel vs sequential (should be 3-5x faster)
- Integration test: Some deleted bookings (404) are filtered out

**Code Template**:
```python
def _fetch_booking_details_parallel(self, booking_ids: List[int]) -> List[dict]:
    """Fetch booking details in parallel."""
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(self._fetch_booking_details, booking_ids))

    # Filter out None (deleted bookings)
    bookings = [b for b in results if b is not None]

    self.lgr.info(f"Fetched {len(bookings)}/{len(booking_ids)} booking details")
    return bookings
```

---

### T010: Implement MRI Operator Fetching
**Priority**: P2
**Effort**: 0.5 hours
**Dependencies**: T008

**Description**:
Implement `_fetch_mri_operator()` to retrieve operator name for MRIScan bookings using the extended query endpoint.

**Implementation Steps**:
1. Implement `_fetch_mri_operator(self, booking_id: int) -> Optional[str]` method
2. Construct URL: `{base_url}/webdav/q/MRIScan/id/eq/{booking_id}?paths=Operator.name`
3. Execute GET request with auth and timeout
4. Parse response and extract operator name from biskits array
5. Return operator name string or None if not found
6. Handle errors gracefully (log warning, return None)

**Acceptance Criteria**:
- [X] Returns operator name string when available
- [X] Returns None when operator not found
- [X] Errors don't crash booking processing (return None)
- [X] Logs WARNING when operator fetch fails

**Testing**:
- Integration test: Mock API returns operator name
- Integration test: Mock empty response returns None
- Integration test: Mock error returns None and logs warning

---

## Category 3: Data Transformation

### T011: Implement Regex Field Extraction
**Priority**: P0 (Critical Path)
**Effort**: 1.5 hours
**Dependencies**: T001

**Description**:
Implement `_extract_field_with_regex()` to apply regex patterns from field_mapping `_extract` configurations, supporting named groups and fallback to original values on failure.

**Implementation Steps**:
1. Implement `_extract_field_with_regex(self, source_value: str, extract_config: dict) -> str` method
2. Extract `pattern` and `group` from extract_config
3. Compile regex pattern with `re.compile(pattern)`
4. Execute `match = pattern.match(source_value)`
5. If match and group specified, return `match.group(group)`
6. If match and no group, return `match.group(0)` (full match)
7. If no match, log WARNING and return original source_value (fallback)
8. Handle regex compilation errors with PluginConfigError

**Acceptance Criteria**:
- [X] Extracts using specified group number
- [X] Falls back to original value on no match
- [X] Logs WARNING on extraction failure with original value
- [X] Raises PluginConfigError on invalid regex pattern
- [X] Supports group 0 (full match), 1+ (capture groups)
- [X] Handles None/empty source values gracefully

**Testing**:
- Unit test: Extract PatientID from "SUB001_John_Doe" with pattern `(\w+)_.*` group 1
- Unit test: Extract PatientName from "SUB001_John_Doe" with pattern `\w+_(.+)` group 1
- Unit test: No match returns original value
- Unit test: Invalid regex pattern raises PluginConfigError
- Unit test: Empty source value returns empty string

**Code Template**:
```python
def _extract_field_with_regex(self, source_value: str, extract_config: dict) -> str:
    """Apply regex pattern to extract field value."""
    if not source_value:
        return ""

    pattern_str = extract_config.get("pattern")
    group_num = extract_config.get("group", 0)

    try:
        pattern = re.compile(pattern_str)
        match = pattern.match(source_value)

        if match:
            return match.group(group_num)
        else:
            self.lgr.warning(f"Regex no match for '{source_value}', using original")
            return source_value

    except Exception as e:
        raise PluginConfigError(f"Invalid regex pattern '{pattern_str}': {e}") from e
```

---

### T012: Implement Timezone Conversion Utilities
**Priority**: P0 (Critical Path)
**Effort**: 1 hour
**Dependencies**: T001

**Description**:
Implement timezone conversion utilities: `_parse_formatted_name_dates()` to extract start/end times from formattedName field, and `_convert_to_utc()` to convert Mountain Time to UTC.

**Implementation Steps**:
1. Implement `_parse_formatted_name_dates(self, formatted_name: str) -> Tuple[datetime, datetime]` method
2. Extract date range from format: `"[YYYY-MM-DD HH:MM:SS.f, YYYY-MM-DD HH:MM:SS.f]"`
3. Use regex to extract start and end timestamp strings
4. Parse timestamps using `datetime.strptime()`
5. Localize to Mountain Time using `pytz.timezone("America/Edmonton").localize()`
6. Return tuple of (start_dt, end_dt)
7. Implement `_convert_to_utc(self, dt: datetime) -> datetime` method to convert to UTC

**Acceptance Criteria**:
- [X] Parses formattedName format correctly
- [X] Returns tuple of two datetime objects
- [X] Datetimes are timezone-aware (Mountain Time)
- [X] DST transitions handled correctly by pytz
- [X] Raises ValueError on invalid format with descriptive message
- [X] UTC conversion preserves absolute time

**Testing**:
- Unit test: Parse valid formattedName, verify dates
- Unit test: Parse during DST transition (Mar/Nov)
- Unit test: Invalid format raises ValueError
- Unit test: Convert MT to UTC and verify offset
- Unit test: Verify DST vs non-DST offset differences

**Code Template**:
```python
def _parse_formatted_name_dates(self, formatted_name: str) -> Tuple[datetime, datetime]:
    """Extract start/end times from formattedName field."""
    # Format: "[2026-01-27 14:00:00.0, 2026-01-27 15:30:00.0]"
    pattern = r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+), (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]"
    match = re.match(pattern, formatted_name)

    if not match:
        raise ValueError(f"Invalid formattedName format: {formatted_name}")

    tz = pytz.timezone(self.config.get("timezone", "America/Edmonton"))

    start_str, end_str = match.groups()
    start_naive = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S.%f")
    end_naive = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S.%f")

    start_dt = tz.localize(start_naive)
    end_dt = tz.localize(end_naive)

    return start_dt, end_dt

def _convert_to_utc(self, dt: datetime) -> datetime:
    """Convert timezone-aware datetime to UTC."""
    return dt.astimezone(pytz.UTC)
```

---

### T013: Implement Status and Resource Mapping
**Priority**: P1
**Effort**: 0.5 hours
**Dependencies**: T001

**Description**:
Implement `_map_status_to_dicom()` and `_map_resource_to_modality()` to convert Calpendo status values to DICOM procedure step statuses and resource names to modality codes.

**Implementation Steps**:
1. Implement `_map_status_to_dicom(self, calpendo_status: str) -> str` method
2. Define status mapping dict:
   - "Approved" → "SCHEDULED"
   - "In Progress" → "IN_PROGRESS"
   - "Completed" → "COMPLETED"
   - "Cancelled" → "DISCONTINUED"
   - "Pending" → "SCHEDULED"
3. Implement `_map_resource_to_modality(self, resource_name: str) -> str` method
4. Check config for `resource_modality_mapping` dict
5. Try exact match first, then prefix match (e.g., "3T" matches "3T Diagnostic")
6. Default to resource_name if no mapping found

**Acceptance Criteria**:
- [X] All Calpendo statuses map to valid DICOM statuses
- [X] Unknown statuses default to "SCHEDULED"
- [X] Resource mapping supports exact and prefix matching
- [X] Custom mappings from config override defaults
- [X] Case-insensitive matching

**Testing**:
- Unit test: Map all known statuses
- Unit test: Unknown status defaults to SCHEDULED
- Unit test: Resource prefix match (e.g., "3T" → "MR")
- Unit test: Custom mapping from config

**Code Template**:
```python
STATUS_MAPPING = {
    "Approved": "SCHEDULED",
    "In Progress": "IN_PROGRESS",
    "Completed": "COMPLETED",
    "Cancelled": "DISCONTINUED",
    "Pending": "SCHEDULED",
}

def _map_status_to_dicom(self, calpendo_status: str) -> str:
    """Map Calpendo status to DICOM procedure step status."""
    return STATUS_MAPPING.get(calpendo_status, "SCHEDULED")

def _map_resource_to_modality(self, resource_name: str) -> str:
    """Map resource name to modality code."""
    mapping = self.config.get("resource_modality_mapping", {})

    # Exact match
    if resource_name in mapping:
        return mapping[resource_name]

    # Prefix match
    for prefix, modality in mapping.items():
        if resource_name.startswith(prefix):
            return modality

    # Default to resource name
    return resource_name
```

---

### T014: Implement Booking to Entry Transformation
**Priority**: P0 (Critical Path)
**Effort**: 1.5 hours
**Dependencies**: T011, T012, T013

**Description**:
Implement `_transform_booking_to_entry()` to convert a Calpendo booking dict into a WorklistItem-compatible dict, applying field mappings, regex extraction, timezone conversion, and status/resource mapping.

**Implementation Steps**:
1. Implement `_transform_booking_to_entry(self, booking: dict) -> Optional[Dict[str, Any]]` method
2. Initialize empty entry dict with data_source set to source_name
3. Iterate through field_mapping config
4. For each target field, extract source value from booking (support nested keys like "project.formattedName")
5. If `_extract` present, apply regex extraction
6. Apply transformations: timezone conversion for date fields, status mapping, resource mapping
7. Validate required fields present (patient_id, scheduled_start_date, scheduled_start_time)
8. If validation fails, log WARNING and return None
9. Return complete entry dict

**Acceptance Criteria**:
- [X] Returns dict with all mapped fields
- [X] Supports nested source keys (e.g., "project.formattedName")
- [X] Applies regex extraction when configured
- [X] Converts times from MT to UTC
- [X] Maps status and resource correctly
- [X] Returns None for bookings missing required fields
- [X] Logs WARNING when skipping invalid booking

**Testing**:
- Integration test: Transform complete booking, verify all fields
- Unit test: Nested field extraction (project.formattedName)
- Unit test: Regex extraction applied correctly
- Unit test: Timezone conversion for date fields
- Integration test: Missing required field returns None

**Code Template**:
```python
def _transform_booking_to_entry(self, booking: dict) -> Optional[Dict[str, Any]]:
    """Transform Calpendo booking to worklist entry."""
    entry = {"data_source": self.source_name}
    field_mapping = self.config.get("field_mapping", {})

    for target_field, mapping_config in field_mapping.items():
        # Extract source value (support nested keys)
        if isinstance(mapping_config, dict):
            source_key = mapping_config.get("source_field")
            source_value = self._get_nested_value(booking, source_key)

            # Apply regex extraction if configured
            if "_extract" in mapping_config:
                source_value = self._extract_field_with_regex(
                    source_value, mapping_config["_extract"]
                )
        else:
            # Simple string mapping
            source_value = self._get_nested_value(booking, mapping_config)

        entry[target_field] = source_value

    # Apply transformations
    if "formattedName" in booking:
        start_dt, end_dt = self._parse_formatted_name_dates(booking["formattedName"])
        entry["scheduled_start_date"] = self._convert_to_utc(start_dt).date()
        entry["scheduled_start_time"] = self._convert_to_utc(start_dt).time()

    # Validate required fields
    required = ["patient_id", "scheduled_start_date", "scheduled_start_time"]
    for field in required:
        if not entry.get(field):
            self.lgr.warning(f"Booking {booking.get('id')} missing {field}, skipping")
            return None

    return entry
```

---

### T015: Implement Change Detection (Hashing)
**Priority**: P1
**Effort**: 0.5 hours
**Dependencies**: T014

**Description**:
Implement `_compute_booking_hash()` to generate SHA256 hash of critical booking fields for change detection, and logic to compare hashes with stored values to filter unchanged bookings.

**Implementation Steps**:
1. Implement `_compute_booking_hash(self, booking: dict) -> str` method
2. Extract critical fields: title, status, formattedName, project name, resource name
3. Create dict with these fields in sorted order
4. Serialize to JSON string
5. Compute SHA256 hash and return hex digest
6. Store hash in entry dict under `notes` field as JSON: `{"booking_hash": "abc123..."}`
7. Add logic to compare new hash with existing hash from DB (if available)

**Acceptance Criteria**:
- [X] Returns consistent hash for same booking data
- [X] Different hashes for changed bookings
- [X] Hash includes all critical fields (title, status, dates, project, resource)
- [X] Hash stored in notes field as valid JSON
- [X] Change detection filters unchanged bookings

**Testing**:
- Unit test: Same booking data produces same hash
- Unit test: Changed title produces different hash
- Unit test: Changed status produces different hash
- Unit test: Hash stored correctly in notes JSON

**Code Template**:
```python
def _compute_booking_hash(self, booking: dict) -> str:
    """Compute SHA256 hash of critical booking fields."""
    critical_fields = {
        "title": booking.get("title", ""),
        "status": booking.get("status", ""),
        "formattedName": booking.get("formattedName", ""),
        "project": booking.get("properties", {}).get("project", {}).get("formattedName", ""),
        "resource": booking.get("properties", {}).get("resource", {}).get("formattedName", ""),
    }

    json_str = json.dumps(critical_fields, sort_keys=True)
    hash_hex = hashlib.sha256(json_str.encode()).hexdigest()
    return hash_hex
```

---

## Category 4: Testing

### T016: Create Unit Tests for Configuration Validation
**Priority**: P0 (Critical Path)
**Effort**: 1 hour
**Dependencies**: T002

**Description**:
Create pytest test suite for configuration validation covering all validation rules, error cases, and valid configurations.

**Implementation Steps**:
1. Create `tests/test_calpendo_plugin.py`
2. Write test fixtures for valid/invalid configs
3. Test valid config passes validation
4. Test missing base_url raises PluginConfigError
5. Test empty resources raises PluginConfigError
6. Test missing env vars raises PluginConfigError
7. Test invalid field_mapping structure raises PluginConfigError
8. Test all edge cases from T002 acceptance criteria

**Acceptance Criteria**:
- [X] All validation error cases have tests
- [X] Tests use pytest fixtures for config data
- [X] Tests verify exact error messages
- [X] 100% coverage of validate_config() method

**Testing**:
```bash
pytest tests/test_calpendo_plugin.py::TestConfigValidation -v
```

---

### T017: Create Integration Tests with Mock API
**Priority**: P0 (Critical Path)
**Effort**: 2 hours
**Dependencies**: T003, T007, T008

**Description**:
Create integration tests using `responses` library to mock Calpendo API endpoints and test full fetch workflow.

**Implementation Steps**:
1. Create `tests/test_calpendo_integration.py`
2. Install `responses` library for HTTP mocking
3. Create fixture for mock Calpendo API responses (booking query, booking details, MRIScan operator)
4. Write test for successful full sync workflow
5. Write test for API authentication failure (401)
6. Write test for empty booking results
7. Write test for deleted booking (404 on detail fetch)
8. Write test for parallel detail fetching performance

**Acceptance Criteria**:
- [X] Mock API responses match real Calpendo response format
- [X] Full fetch workflow test covers T003 logic
- [X] Auth failure test verifies PluginFetchError raised
- [X] Empty results test returns empty list
- [X] 404 handling test filters deleted bookings
- [X] Parallel fetch test verifies ThreadPoolExecutor usage

**Testing**:
```bash
pytest tests/test_calpendo_integration.py -v
```

---

### T018: Create Unit Tests for Data Transformation
**Priority**: P1
**Effort**: 1.5 hours
**Dependencies**: T011, T012, T013, T014

**Description**:
Create comprehensive unit tests for all transformation utilities: regex extraction, timezone conversion, status/resource mapping, and full booking transformation.

**Implementation Steps**:
1. Add tests to `tests/test_calpendo_plugin.py`
2. Test regex extraction with various patterns and groups
3. Test timezone conversion with DST transitions
4. Test formattedName parsing with valid/invalid formats
5. Test status mapping for all known statuses
6. Test resource mapping with exact and prefix matches
7. Test full booking transformation with complete booking data
8. Test transformation with missing optional fields

**Acceptance Criteria**:
- [X] All extraction patterns from quickstart.md tested
- [X] DST transition dates tested (March/November)
- [X] All status mappings verified
- [X] Resource prefix matching verified
- [X] Full transformation produces valid entry dict
- [X] Missing required fields return None

**Testing**:
```bash
pytest tests/test_calpendo_plugin.py::TestTransformation -v
```

---

### T019: Create Fixtures for Mock API Responses
**Priority**: P1
**Effort**: 0.5 hours
**Dependencies**: T017

**Description**:
Create JSON fixture files with realistic mock Calpendo API responses for testing.

**Implementation Steps**:
1. Create `tests/fixtures/calpendo_responses.json`
2. Add mock booking query response with 3-5 bookings
3. Add mock booking detail response with all fields
4. Add mock MRIScan extended response with operator
5. Add mock error responses (401, 404, 500)
6. Document fixture structure in comments

**Acceptance Criteria**:
- [X] Fixtures match real Calpendo API response format from contracts/calpendo-api.md
- [X] Includes various booking types (MRIScan, EEG, etc.)
- [X] Includes edge cases (missing fields, cancelled status)
- [X] Valid JSON format

---

### T020: Create End-to-End Integration Test
**Priority**: P2
**Effort**: 1 hour
**Dependencies**: T016, T017, T018

**Description**:
Create end-to-end test that validates the full plugin workflow: configuration → query → fetch → transform → change detection → return entries.

**Implementation Steps**:
1. Add test to `tests/test_calpendo_integration.py`
2. Mock complete Calpendo API (query + details)
3. Create CalendoPlugin with full config
4. Call fetch_entries() with sync_interval
5. Verify correct bookings returned
6. Verify transformations applied correctly
7. Verify change detection works (run twice, second run filters unchanged)
8. Verify logging output includes expected messages

**Acceptance Criteria**:
- [X] Test covers full fetch_entries() workflow
- [X] Verifies rolling window calculation
- [X] Verifies parallel detail fetching
- [X] Verifies all transformations applied
- [X] Verifies change detection filters unchanged bookings
- [X] Logs include all expected INFO/WARNING/DEBUG messages

**Testing**:
```bash
pytest tests/test_calpendo_integration.py::test_end_to_end_sync -v
```

---

## Category 5: Documentation & Deployment

### T021: Create Example Configuration File
**Priority**: P1
**Effort**: 0.5 hours
**Dependencies**: T002

**Description**:
Create example configuration file with comprehensive comments explaining all options and common patterns.

**Implementation Steps**:
1. Create `src/pylantir/config/calpendo_config_example.json`
2. Include minimal config example
3. Include full config example with all optional fields
4. Add comments (via separate .md file) explaining each field
5. Include regex extraction examples from quickstart.md
6. Include multiple resource configurations

**Acceptance Criteria**:
- [X] File created at correct path
- [X] Valid JSON format
- [X] Includes minimal and full examples
- [X] All optional fields documented
- [X] Regex extraction examples included
- [X] Matches quickstart.md examples

---

### T022: Update Main Configuration Template
**Priority**: P2
**Effort**: 0.5 hours
**Dependencies**: T021

**Description**:
Update main `mwl_config.json` template to include Calpendo data source example.

**Implementation Steps**:
1. Open `src/pylantir/config/mwl_config.json`
2. Add Calpendo example to `data_sources` array (commented out)
3. Add comment explaining Calpendo configuration
4. Reference calpendo_config_example.json for full details

**Acceptance Criteria**:
- [ ] Calpendo example added to data_sources array
- [ ] Example is commented out by default
- [ ] Comment references full example file
- [ ] Valid JSON format maintained

---

### T023: Register Plugin in PLUGIN_REGISTRY
**Priority**: P0 (Critical Path)
**Effort**: 0.25 hours
**Dependencies**: T001

**Description**:
Add CalendoPlugin to the plugin registry in `data_sources/__init__.py` so it can be auto-discovered by Pylantir.

**Implementation Steps**:
1. Open `src/pylantir/data_sources/__init__.py`
2. Import CalendoPlugin: `from .calpendo_plugin import CalendoPlugin`
3. Add to PLUGIN_REGISTRY dict: `"calpendo": CalendoPlugin`
4. Verify no syntax errors

**Acceptance Criteria**:
- [X] Import statement added
- [X] Plugin registered with key "calpendo"
- [X] No import errors when loading module
- [X] Plugin discoverable by framework

---

### T024: Update README with Calpendo Example
**Priority**: P2
**Effort**: 0.5 hours
**Dependencies**: T021, T023

**Description**:
Update project README.md to document Calpendo plugin with configuration example and usage instructions.

**Implementation Steps**:
1. Open README.md
2. Add section "Calpendo Data Source Integration"
3. Include minimal configuration example
4. Document environment variables required
5. Link to quickstart.md for full documentation
6. Add troubleshooting tips

**Acceptance Criteria**:
- [X] Section added after REDCap documentation
- [X] Configuration example provided
- [X] Environment variables documented
- [X] Link to quickstart.md included
- [X] Basic troubleshooting included

---

### T025: Create Quickstart Verification Script
**Priority**: P3
**Effort**: 0.5 hours
**Dependencies**: T023

**Description**:
Create a verification script to validate Calpendo plugin installation and configuration.

**Implementation Steps**:
1. Create `scripts/verify_calpendo_setup.py`
2. Check environment variables set
3. Test API connectivity
4. Validate configuration file
5. Test plugin registration
6. Print setup status report

**Acceptance Criteria**:
- [ ] Script checks all prerequisites
- [ ] Reports missing environment variables
- [ ] Tests API authentication
- [ ] Validates config file structure
- [ ] Provides actionable error messages
- [ ] Returns exit code 0 on success, 1 on failure

---

## Task Execution Guide

### Phase 1: Foundation (Hours 0-6)
**Goal**: Core plugin structure and API integration working

**Priority Order**:
1. T001: CalendoPlugin scaffolding
2. T004: Error handling classes
3. T002: Configuration validation
4. T005: Logging infrastructure
5. T006: Query construction
6. T007: Booking fetching
7. T008: Detail fetching
8. T009: Parallel fetching
9. T023: Plugin registration

**Validation**: Can fetch bookings from Calpendo and log results

---

### Phase 2: Transformation (Hours 6-10)
**Goal**: Data transformation pipeline working

**Priority Order**:
1. T011: Regex field extraction
2. T012: Timezone utilities
3. T013: Status/resource mapping
4. T014: Booking transformation
5. T015: Change detection
6. T003: fetch_entries() orchestration

**Validation**: Can transform Calpendo bookings to worklist entries

---

### Phase 3: Testing (Hours 10-15)
**Goal**: Comprehensive test coverage

**Priority Order**:
1. T016: Config validation tests
2. T019: Mock API fixtures
3. T017: Integration tests
4. T018: Transformation tests
5. T020: End-to-end test

**Validation**: All tests pass, 80%+ coverage

---

### Phase 4: Documentation & Polish (Hours 15-18)
**Goal**: Production-ready deployment

**Priority Order**:
1. T021: Example configuration
2. T022: Update main config
3. T024: Update README
4. T010: MRI operator fetching (nice-to-have)
5. T025: Verification script

**Validation**: Ready for user deployment

---

## Success Criteria Mapping

| Success Criterion | Related Tasks | Verification Method |
|------------------|---------------|---------------------|
| SC-001: <10s for 50 bookings | T009 (parallel fetching) | Performance test |
| SC-002: 100% field mapping accuracy | T011, T012, T013, T014 | Unit tests |
| SC-003: Graceful error handling | T004, T005, T007, T008 | Integration tests |
| SC-004: Timezone accuracy | T012 | Unit tests with DST |
| SC-005: Config validation | T002 | Unit tests |
| SC-006: Filtering accuracy | T006, T007 | Integration tests |
| SC-007: 3-5x parallel speedup | T009 | Performance test |

---

## Risk Mitigation

**Risk**: Regex patterns in field_mapping too complex for users
- **Mitigation**: Provide pattern library in quickstart.md (T021), validation in config (T002)

**Risk**: Timezone conversions incorrect during DST transitions
- **Mitigation**: Comprehensive DST testing (T018), use pytz.localize() (T012)

**Risk**: API rate limiting not handled
- **Mitigation**: Parallel fetch limited to 5 workers (T009), add retry logic with backoff (T007)

**Risk**: Performance issues with large booking volumes
- **Mitigation**: Rolling window limits data (T003), change detection prevents redundant processing (T015)

---

**END OF TASK BREAKDOWN**
