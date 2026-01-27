# Feature Specification: Calpendo Data Source Plugin

**Feature Branch**: `002-calpendo-plugin`  
**Created**: 2026-01-27  
**Status**: Draft  
**Input**: User description: "I want to use the example in example_for_calpendo.py to create a new data_source calpendo_plugin following the idea from redcap."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fetch Calpendo Bookings as Worklist Entries (Priority: P1)

System administrators configure Pylantir to fetch MRI/EEG scanner bookings from Calpendo and automatically populate the DICOM worklist. When a booking exists in Calpendo for a specific date/time with study information, it appears in the worklist for the imaging technician to use during patient scanning.

**Why this priority**: This is the core functionality enabling Calpendo integration. Without this, the plugin provides no value. This matches the existing REDCap plugin's primary purpose and maintains architectural consistency.

**Independent Test**: Can be fully tested by configuring a Calpendo data source in the config file, running the sync process, and verifying that bookings from Calpendo appear in the worklist database with correct subject ID, study name, date/time, and resource information.

**Acceptance Scenarios**:

1. **Given** a valid Calpendo configuration with API credentials, **When** the sync process runs for a date range containing bookings, **Then** all approved bookings are fetched and transformed into worklist entries with subject ID, study name, start/end times, and resource type.

2. **Given** a Calpendo booking with status "Approved" for resource "3T Diagnostic", **When** the plugin fetches entries, **Then** the worklist entry includes the correct study name (extracted from project name before parentheses), subject ID from booking title, and scan times in the correct timezone.

3. **Given** Calpendo returns multiple bookings for different resources (3T, EEG, Mock Scanner), **When** the plugin processes them, **Then** each booking is correctly mapped to a separate worklist entry with appropriate resource identifiers.

---

### User Story 2 - Filter Bookings by Resource and Status (Priority: P2)

System administrators want to sync only specific types of bookings (e.g., only 3T MRI scans, only approved bookings) to avoid cluttering the worklist with cancelled, pending, or irrelevant bookings.

**Why this priority**: Filtering capabilities improve worklist quality and reduce noise. While important for production use, basic fetching (P1) must work first. This matches the filtering logic shown in example_for_calpendo.py.

**Independent Test**: Configure the plugin with resource filter "3T Diagnostic" and status filter "Approved", run sync, and verify that only bookings matching both criteria appear in the worklist.

**Acceptance Scenarios**:

1. **Given** a plugin configuration with resource filter "3T Diagnostic", **When** the sync runs and Calpendo has bookings for both "3T Diagnostic" and "EEG", **Then** only 3T Diagnostic bookings are added to the worklist.

2. **Given** a plugin configuration with status filter "Approved", **When** Calpendo returns bookings with various statuses (Approved, Pending, Cancelled), **Then** only Approved bookings are synced.

3. **Given** configuration filters for both resource and status, **When** sync runs, **Then** only bookings matching BOTH criteria are included (AND logic, not OR).

---

### User Story 3 - Handle Booking Updates and Cancellations (Priority: P3)

When a booking in Calpendo is updated (time changed, cancelled, modified), the corresponding worklist entry should reflect the change during the next sync cycle.

**Why this priority**: Real-time accuracy improves user experience, but the MVP can function with periodic full syncs. This is an enhancement for production robustness.

**Independent Test**: Create a booking in Calpendo, sync to populate worklist, modify or cancel the booking in Calpendo, run sync again, and verify the worklist entry is updated or removed accordingly.

**Acceptance Scenarios**:

1. **Given** a synced booking that gets cancelled in Calpendo, **When** the next sync runs, **Then** the worklist entry is either marked as cancelled or removed (based on configuration).

2. **Given** a booking time is changed in Calpendo, **When** sync runs, **Then** the worklist entry reflects the updated start/end times.

3. **Given** a booking's subject ID (title) is updated in Calpendo, **When** sync occurs, **Then** the worklist entry shows the new subject ID.

---

### Edge Cases

- What happens when Calpendo API is unreachable or returns authentication errors? (System should log error, skip this sync cycle, and retry on next interval without crashing)
- How does the system handle bookings with missing required fields (e.g., no subject ID, no project/study name)? (Log warning, skip the incomplete booking, continue processing others)
- What if a booking spans multiple days? (Extract start date/time as the primary worklist date, log multi-day span for administrator awareness)
- How are timezone conversions handled when Calpendo returns UTC but worklist expects local time? (Use Mountain Time as shown in example, convert all timestamps appropriately)
- What happens with concurrent API requests if fetching booking details in parallel? (Use ThreadPoolExecutor as shown in example to safely parallelize up to 5 concurrent requests)
- How does the system handle duplicate bookings (same subject ID, study, time)? (Use existing duplicate detection logic from Pylantir database layer)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Plugin MUST implement DataSourcePlugin interface with validate_config() and fetch_entries() methods, matching the pattern established by REDCapPlugin

- **FR-002**: Plugin MUST authenticate to Calpendo API using basic authentication (username/password) retrieved from environment variables CALPENDO_API_URL, CALPENDO_USERNAME, and CALPENDO_PASSWORD

- **FR-003**: Plugin MUST fetch bookings within a configurable date range, defaulting to the sync interval period (e.g., last 60 seconds of modifications)

- **FR-004**: Plugin MUST extract the following fields from Calpendo bookings and map them to worklist fields via field_mapping configuration:
  - Subject ID (from booking title)
  - Study name (from project formattedName, extracting text before parentheses)
  - Start time (from formattedName date range, converted to Mountain Time)
  - End time (from formattedName date range, converted to Mountain Time)
  - Resource name (from resource.formattedName)
  - Booking status
  - Duration in minutes

- **FR-005**: Plugin MUST support filtering bookings by resource name (prefix match, e.g., "3T" matches "3T Diagnostic") via configuration

- **FR-006**: Plugin MUST support filtering bookings by status (exact match, e.g., "Approved") via configuration

- **FR-007**: Plugin MUST fetch detailed booking information using parallel API requests (ThreadPoolExecutor with max 5 workers) to improve performance when processing multiple bookings

- **FR-008**: Plugin MUST handle MRIScan biskit type differently from other types, fetching additional operator information when biskit_type is "MRIScan"

- **FR-009**: Plugin MUST convert all Calpendo timestamps from UTC to Mountain Time (America/Edmonton timezone) before storing in worklist

- **FR-010**: Plugin MUST log all API requests, responses, errors, and skipped bookings with appropriate log levels (INFO for normal operations, WARNING for missing fields, ERROR for API failures)

- **FR-011**: Plugin MUST raise PluginFetchError on API communication failures and PluginConfigError on invalid configuration, consistent with REDCap plugin error handling

- **FR-012**: Plugin MUST validate that required configuration includes base_url (Calpendo server URL) and resources list (array of resource names to sync)

### Key Entities *(include if feature involves data)*

- **Calpendo Booking**: Represents a scanner reservation with subject ID (title), study name (from project), start/end times, resource, status, operator (for MRI), booker, owner, duration, creation/modification timestamps

- **Worklist Entry**: DICOM worklist item containing patient/study information mapped from Calpendo booking fields via configurable field_mapping

- **Resource**: Scanner or equipment type (3T Diagnostic, EEG, Mock Scanner) with formatted name and ID

- **Project**: Study/research project in Calpendo containing formatted name (e.g., "BRISKP (Brain network models...)") from which study name is extracted

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Plugin successfully fetches bookings from Calpendo and populates worklist entries within 10 seconds for up to 50 bookings per sync cycle

- **SC-002**: All booking field mappings (subject ID, study name, times, resource) are correctly transformed with 100% accuracy (no data loss or corruption)

- **SC-003**: Plugin handles API failures gracefully without crashing the main Pylantir service, logging errors and continuing with next sync cycle

- **SC-004**: Timezone conversions from UTC to Mountain Time are accurate for all booking timestamps, verified by comparing displayed times with Calpendo web interface

- **SC-005**: Plugin configuration validation catches all missing required fields (API credentials, base URL, resources) before sync attempts, providing clear error messages

- **SC-006**: When filtering by resource and status, only matching bookings appear in worklist, with zero false positives or false negatives

- **SC-007**: Parallel API requests complete 3-5x faster than sequential requests when fetching details for 10+ bookings
